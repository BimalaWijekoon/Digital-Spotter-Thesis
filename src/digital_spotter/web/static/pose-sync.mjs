/** Clock mapping and bounded pose lookup for browser-side video overlays. */

function finiteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}


function requireExchangeNumber(value, name) {
  if (!finiteNumber(value) || value < 0) {
    throw new TypeError(`invalid clock exchange ${name}`);
  }
}


export class BrowserPiClockMapper {
  constructor({ maxSamples = 8, maxAgeMs = 5_000,
    nowMs = () => globalThis.performance.now() } = {}) {
    if (!Number.isInteger(maxSamples) || maxSamples < 1 || maxSamples > 64) {
      throw new RangeError("maxSamples must be an integer between 1 and 64");
    }
    if (!finiteNumber(maxAgeMs) || maxAgeMs <= 0 || maxAgeMs > 60_000
      || typeof nowMs !== 'function') {
      throw new RangeError("clock age limit and clock source must be valid");
    }
    this.maxSamples = maxSamples;
    this.maxAgeMs = maxAgeMs;
    this.nowMs = nowMs;
    this.samples = [];
  }

  get sampleCount() {
    return this.samples.length;
  }

  get isSynchronized() {
    return this.#bestSample() !== null;
  }

  get bestRoundTripUs() {
    return this.#bestSample()?.roundTripUs ?? null;
  }

  observe({
    clientSentMs,
    clientReceivedMs,
    serverReceivedMonotonicUs,
    serverSentMonotonicUs,
  }) {
    requireExchangeNumber(clientSentMs, "clientSentMs");
    requireExchangeNumber(clientReceivedMs, "clientReceivedMs");
    requireExchangeNumber(serverReceivedMonotonicUs, "serverReceivedMonotonicUs");
    requireExchangeNumber(serverSentMonotonicUs, "serverSentMonotonicUs");

    const clientSentUs = clientSentMs * 1_000;
    const clientReceivedUs = clientReceivedMs * 1_000;
    const serverProcessingUs = serverSentMonotonicUs - serverReceivedMonotonicUs;
    const roundTripUs = clientReceivedUs - clientSentUs - serverProcessingUs;

    if (
      clientReceivedUs < clientSentUs
      || serverProcessingUs < 0
      || roundTripUs < 0
    ) {
      throw new RangeError("invalid clock exchange timestamp order");
    }

    const offsetUs = (
      (serverReceivedMonotonicUs - clientSentUs)
      + (serverSentMonotonicUs - clientReceivedUs)
    ) / 2;
    const sample = { roundTripUs, offsetUs, receivedMs: clientReceivedMs };
    this.samples.push(sample);
    if (this.samples.length > this.maxSamples) {
      this.samples.shift();
    }
    return { roundTripUs, offsetUs };
  }

  clear() {
    this.samples.length = 0;
  }

  toServerMonotonicUs(browserPerformanceMs) {
    requireExchangeNumber(browserPerformanceMs, "browserPerformanceMs");
    const best = this.#bestSample();
    if (!best) {
      throw new Error("browser-to-Pi clock is not synchronized");
    }
    return (browserPerformanceMs * 1_000) + best.offsetUs;
  }

  #bestSample() {
    const now = this.nowMs();
    if (!finiteNumber(now) || now < 0) return null;
    return this.samples.filter((sample) => now - sample.receivedMs <= this.maxAgeMs
      && now >= sample.receivedMs).reduce(
      (best, sample) => best === null || sample.roundTripUs < best.roundTripUs ? sample : best,
      null,
    );
  }
}


function validatePoseSample(sample) {
  const validQualities = new Set([
    'good',
    'vision_degraded',
    'imu_degraded',
    'unsynchronized',
    'unavailable',
    'simulated',
  ]);
  const validLandmarks = Array.isArray(sample?.landmarks)
    && sample.landmarks.length <= 64
    && sample.landmarks.every((landmark) => (
      landmark !== null
      && typeof landmark === 'object'
      && finiteNumber(landmark.x)
      && finiteNumber(landmark.y)
      && finiteNumber(landmark.z)
      && finiteNumber(landmark.visibility)
      && landmark.visibility >= 0
      && landmark.visibility <= 1
    ));
  const validAngles = sample?.angles !== null
    && typeof sample?.angles === 'object'
    && !Array.isArray(sample.angles)
    && Object.keys(sample.angles).length <= 64
    && Object.values(sample.angles).every(finiteNumber);
  if (
    sample === null
    || typeof sample !== 'object'
    || sample.schema_version !== 1
    || sample.message_type !== 'pose_sample'
    || typeof sample.event_id !== 'string'
    || sample.event_id.length === 0
    || sample.event_id.length > 64
    || !Number.isSafeInteger(sample.frame_sequence)
    || sample.frame_sequence < 0
    || !Number.isSafeInteger(sample.captured_monotonic_us)
    || sample.captured_monotonic_us < 0
    || !Number.isInteger(sample.image_width)
    || sample.image_width < 1
    || sample.image_width > 8192
    || !Number.isInteger(sample.image_height)
    || sample.image_height < 1
    || sample.image_height > 8192
    || !Number.isInteger(sample.landmark_schema_version)
    || sample.landmark_schema_version < 0
    || sample.landmark_schema_version > 0xFFFF
    || !validLandmarks
    || !validAngles
    || !finiteNumber(sample.pose_confidence)
    || sample.pose_confidence < 0
    || sample.pose_confidence > 1
    || !validQualities.has(sample.quality)
    || !Number.isSafeInteger(sample.processing_latency_us)
    || sample.processing_latency_us < 0
    || !Number.isInteger(sample.frames_dropped_since_previous)
    || sample.frames_dropped_since_previous < 0
    || sample.frames_dropped_since_previous > 0xFFFFFFFF
    || typeof sample.is_simulated !== 'boolean'
    || sample.is_simulated !== (sample.quality === 'simulated')
  ) {
    throw new TypeError("invalid browser pose sample");
  }
}


export class PoseTimeline {
  constructor({ capacity = 120, maxMatchDeltaMs = 80 } = {}) {
    if (!Number.isInteger(capacity) || capacity < 1 || capacity > 1_000) {
      throw new RangeError("capacity must be an integer between 1 and 1000");
    }
    if (!finiteNumber(maxMatchDeltaMs) || maxMatchDeltaMs < 0 || maxMatchDeltaMs > 5_000) {
      throw new RangeError("maxMatchDeltaMs must be between 0 and 5000");
    }
    this.capacity = capacity;
    this.maxMatchDeltaUs = maxMatchDeltaMs * 1_000;
    this.samples = [];
  }

  get size() {
    return this.samples.length;
  }

  add(sample) {
    validatePoseSample(sample);
    const duplicateIndex = this.samples.findIndex((item) => item.event_id === sample.event_id);
    if (duplicateIndex >= 0) {
      this.samples.splice(duplicateIndex, 1);
    }
    this.samples.push(sample);
    this.samples.sort((left, right) => left.captured_monotonic_us - right.captured_monotonic_us);
    if (this.samples.length > this.capacity) {
      this.samples.splice(0, this.samples.length - this.capacity);
    }
  }

  clear() {
    this.samples.length = 0;
  }

  match(serverCaptureUs) {
    if (!finiteNumber(serverCaptureUs) || serverCaptureUs < 0) {
      throw new TypeError("server capture time must be a finite non-negative number");
    }
    if (this.samples.length === 0) {
      return { status: "pose_unavailable", pose: null, deltaUs: null };
    }

    let nearest = this.samples[0];
    let nearestDeltaUs = Math.abs(nearest.captured_monotonic_us - serverCaptureUs);
    for (let index = 1; index < this.samples.length; index += 1) {
      const candidate = this.samples[index];
      const deltaUs = Math.abs(candidate.captured_monotonic_us - serverCaptureUs);
      if (deltaUs < nearestDeltaUs) {
        nearest = candidate;
        nearestDeltaUs = deltaUs;
      }
    }

    if (nearestDeltaUs > this.maxMatchDeltaUs) {
      return { status: "pose_stale", pose: null, deltaUs: nearestDeltaUs };
    }
    return { status: "matched", pose: nearest, deltaUs: nearestDeltaUs };
  }
}


export function matchVideoFrame({ metadata, clockMapper, timeline }) {
  if (!finiteNumber(metadata?.captureTime) || metadata.captureTime < 0) {
    return {
      status: "frame_capture_time_unavailable",
      pose: null,
      deltaUs: null,
    };
  }
  if (!clockMapper?.isSynchronized) {
    return { status: "clock_unsynchronized", pose: null, deltaUs: null };
  }

  const serverCaptureUs = clockMapper.toServerMonotonicUs(metadata.captureTime);
  return timeline.match(serverCaptureUs);
}
