import assert from "node:assert/strict";
import test from "node:test";

import { LiveVideoController } from "../../src/digital_spotter/web/static/live-video-controller.mjs";
import { BrowserPiClockMapper } from "../../src/digital_spotter/web/static/pose-sync.mjs";


function pose(frameSequence, capturedMonotonicUs) {
  return {
    schema_version: 1,
    message_type: "pose_sample",
    event_id: `event-${frameSequence}`,
    frame_sequence: frameSequence,
    captured_monotonic_us: capturedMonotonicUs,
    image_width: 640,
    image_height: 360,
    landmark_schema_version: 1,
    landmarks: [],
    angles: {},
    pose_confidence: 0.9,
    quality: "good",
    processing_latency_us: 2_000,
    frames_dropped_since_previous: 0,
    is_simulated: false,
  };
}


function harness() {
  const callbacks = new Map();
  const cancelled = [];
  let nextHandle = 1;
  const video = {
    requestVideoFrameCallback(callback) {
      const handle = nextHandle;
      nextHandle += 1;
      callbacks.set(handle, callback);
      return handle;
    },
    cancelVideoFrameCallback(handle) {
      cancelled.push(handle);
      callbacks.delete(handle);
    },
  };
  const player = {
    starts: [],
    stops: 0,
    async start(options) { this.starts.push(options); },
    stop() { this.stops += 1; },
  };
  const overlay = {
    renders: [],
    clears: [],
    render(match) { this.renders.push(match); },
    clear(reason) { this.clears.push(reason); },
  };
  let nowMs = 1_000;
  const controller = new LiveVideoController({
    videoElement: video,
    player,
    overlay,
    performanceNow: () => nowMs,
    clockMapper: new BrowserPiClockMapper({ nowMs: () => nowMs }),
  });
  return {
    callbacks,
    cancelled,
    controller,
    overlay,
    player,
    setNow(value) { nowMs = value; },
  };
}


test("coordinates WHEP playback, clock sync, pose matching, and decoded frames", async () => {
  const h = harness();
  await h.controller.start({
    whepUrl: "https://spotter.local/picamera2/whep",
    accessToken: "short-lived-token",
  });

  assert.deepEqual(h.player.starts, [{
    whepUrl: "https://spotter.local/picamera2/whep",
    accessToken: "short-lived-token",
  }]);
  assert.equal(h.callbacks.size, 1);

  const request = h.controller.createClockSyncRequest("sync-1");
  assert.deepEqual(request, {
    schema_version: 1,
    message_type: "clock_sync_request",
    request_id: "sync-1",
    client_sent_ms: 1_000,
  });

  h.setNow(1_021);
  const clockSample = h.controller.acceptClockSyncResponse({
    schema_version: 1,
    message_type: "clock_sync_response",
    request_id: "sync-1",
    client_sent_ms: 1_000,
    server_received_monotonic_us: 6_010_000,
    server_sent_monotonic_us: 6_011_000,
  });
  assert.deepEqual(clockSample, { roundTripUs: 20_000, offsetUs: 5_000_000 });

  h.controller.acceptPoseSample(pose(7, 5_100_000));
  const firstCallback = [...h.callbacks.values()][0];
  h.callbacks.clear();
  firstCallback(0, { captureTime: 100 });

  assert.deepEqual(h.overlay.renders.at(-1), {
    status: "matched",
    pose: pose(7, 5_100_000),
    deltaUs: 0,
  });
  assert.equal(h.callbacks.size, 1);
});


test("passes explicit unavailable timing state to the overlay", async () => {
  const h = harness();
  await h.controller.start({ whepUrl: "http://spotter.local/picamera2/whep" });
  const callback = [...h.callbacks.values()][0];
  h.callbacks.clear();

  callback(0, {});

  assert.deepEqual(h.overlay.renders.at(-1), {
    status: "frame_capture_time_unavailable",
    pose: null,
    deltaUs: null,
  });
});


test("rejects unsolicited or modified clock responses", () => {
  const h = harness();
  h.controller.createClockSyncRequest("sync-1");

  assert.throws(
    () => h.controller.acceptClockSyncResponse({
      schema_version: 1,
      message_type: "clock_sync_response",
      request_id: "unknown",
      client_sent_ms: 1_000,
      server_received_monotonic_us: 6_010_000,
      server_sent_monotonic_us: 6_011_000,
    }),
    /unsolicited clock response/,
  );
  assert.throws(
    () => h.controller.acceptClockSyncResponse({
      schema_version: 1,
      message_type: "clock_sync_response",
      request_id: "sync-1",
      client_sent_ms: 999,
      server_received_monotonic_us: 6_010_000,
      server_sent_monotonic_us: 6_011_000,
    }),
    /client timestamp mismatch/,
  );
});


test("stop cancels frame work, clears state, and closes the reader", async () => {
  const h = harness();
  await h.controller.start({ whepUrl: "http://spotter.local/picamera2/whep" });
  const activeHandle = [...h.callbacks.keys()][0];

  h.controller.stop();

  assert.deepEqual(h.cancelled, [activeHandle]);
  assert.deepEqual(h.overlay.clears, ["controller_stopped"]);
  assert.equal(h.player.stops, 1);
  assert.equal(h.controller.running, false);
});
