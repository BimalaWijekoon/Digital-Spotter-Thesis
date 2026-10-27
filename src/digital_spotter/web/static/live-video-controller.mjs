/**
 * Isolated orchestration for direct WHEP video plus timestamp-matched pose.
 *
 * Transport for pose/clock messages is intentionally outside this module. The
 * eventual authenticated API can deliver validated messages without changing
 * the video, matching, or drawing implementation.
 */

import {
  BrowserPiClockMapper,
  PoseTimeline,
  matchVideoFrame,
} from "./pose-sync.mjs";


function validRequestId(value) {
  return typeof value === 'string'
    && value.length >= 1
    && value.length <= 64
    && /^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(value);
}


function finiteNonNegative(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}


export class LiveVideoController {
  constructor({
    videoElement,
    player,
    overlay,
    clockMapper = new BrowserPiClockMapper(),
    poseTimeline = new PoseTimeline(),
    performanceNow = () => globalThis.performance.now(),
    maximumPendingClockRequests = 8,
  }) {
    if (
      !videoElement
      || typeof videoElement.requestVideoFrameCallback !== 'function'
      || typeof videoElement.cancelVideoFrameCallback !== 'function'
    ) {
      throw new TypeError("videoElement must support requestVideoFrameCallback");
    }
    if (!player || typeof player.start !== 'function' || typeof player.stop !== 'function') {
      throw new TypeError("player with start() and stop() is required");
    }
    if (!overlay || typeof overlay.render !== 'function' || typeof overlay.clear !== 'function') {
      throw new TypeError("overlay with render() and clear() is required");
    }
    if (
      !Number.isInteger(maximumPendingClockRequests)
      || maximumPendingClockRequests < 1
      || maximumPendingClockRequests > 64
    ) {
      throw new RangeError("maximumPendingClockRequests must be between 1 and 64");
    }

    this.videoElement = videoElement;
    this.player = player;
    this.overlay = overlay;
    this.clockMapper = clockMapper;
    this.poseTimeline = poseTimeline;
    this.performanceNow = performanceNow;
    this.maximumPendingClockRequests = maximumPendingClockRequests;
    this.pendingClockRequests = new Map();
    this.frameCallbackHandle = null;
    this.running = false;
  }

  async start(options) {
    if (this.running) {
      throw new Error("live video controller is already running");
    }
    await this.player.start(options);
    this.running = true;
    this.#scheduleFrame();
  }

  stop() {
    this.running = false;
    if (this.frameCallbackHandle !== null) {
      this.videoElement.cancelVideoFrameCallback(this.frameCallbackHandle);
      this.frameCallbackHandle = null;
    }
    this.resetTelemetry("controller_stopped");
    this.player.stop();
  }

  resetTelemetry(reason = "telemetry_unavailable") {
    this.pendingClockRequests.clear();
    this.clockMapper.clear();
    this.poseTimeline.clear();
    this.overlay.clear(reason);
  }

  acceptPoseSample(sample) {
    this.poseTimeline.add(sample);
  }

  createClockSyncRequest(requestId) {
    if (!validRequestId(requestId)) {
      throw new TypeError("invalid clock request id");
    }
    if (this.pendingClockRequests.has(requestId)) {
      throw new Error("clock request id is already pending");
    }
    if (this.pendingClockRequests.size >= this.maximumPendingClockRequests) {
      throw new Error("too many pending clock requests");
    }
    const clientSentMs = this.performanceNow();
    if (!finiteNonNegative(clientSentMs)) {
      throw new Error("browser performance clock is unavailable");
    }
    this.pendingClockRequests.set(requestId, clientSentMs);
    return {
      schema_version: 1,
      message_type: "clock_sync_request",
      request_id: requestId,
      client_sent_ms: clientSentMs,
    };
  }

  acceptClockSyncResponse(response) {
    if (
      response?.schema_version !== 1
      || response?.message_type !== 'clock_sync_response'
      || !validRequestId(response?.request_id)
      || !finiteNonNegative(response?.client_sent_ms)
      || !Number.isSafeInteger(response?.server_received_monotonic_us)
      || response.server_received_monotonic_us < 0
      || !Number.isSafeInteger(response?.server_sent_monotonic_us)
      || response.server_sent_monotonic_us < 0
    ) {
      throw new TypeError("invalid clock response");
    }

    const clientSentMs = this.pendingClockRequests.get(response.request_id);
    if (clientSentMs === undefined) {
      throw new Error("unsolicited clock response");
    }
    if (response.client_sent_ms !== clientSentMs) {
      throw new Error("clock response client timestamp mismatch");
    }

    const clientReceivedMs = this.performanceNow();
    if (!finiteNonNegative(clientReceivedMs)) {
      throw new Error("browser performance clock is unavailable");
    }
    this.pendingClockRequests.delete(response.request_id);
    return this.clockMapper.observe({
      clientSentMs,
      clientReceivedMs,
      serverReceivedMonotonicUs: response.server_received_monotonic_us,
      serverSentMonotonicUs: response.server_sent_monotonic_us,
    });
  }

  #scheduleFrame() {
    if (!this.running) {
      return;
    }
    this.frameCallbackHandle = this.videoElement.requestVideoFrameCallback(
      (_now, metadata) => {
        this.frameCallbackHandle = null;
        if (!this.running) {
          return;
        }
        const match = matchVideoFrame({
          metadata,
          clockMapper: this.clockMapper,
          timeline: this.poseTimeline,
        });
        this.overlay.render(match);
        this.#scheduleFrame();
      },
    );
  }
}
