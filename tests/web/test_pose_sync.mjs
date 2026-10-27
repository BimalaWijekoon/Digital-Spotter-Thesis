import assert from "node:assert/strict";
import test from "node:test";

import {
  BrowserPiClockMapper,
  PoseTimeline,
  matchVideoFrame,
} from "../../src/digital_spotter/web/static/pose-sync.mjs";


function pose(frameSequence, capturedMonotonicUs, quality = "good") {
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
    quality,
    processing_latency_us: 2_000,
    frames_dropped_since_previous: 0,
    is_simulated: false,
  };
}


test("maps the browser performance clock using the lowest-RTT exchange", () => {
  const mapper = new BrowserPiClockMapper({ maxSamples: 4, nowMs: () => 2_101 });
  const first = mapper.observe({
    clientSentMs: 1_000,
    clientReceivedMs: 1_021,
    serverReceivedMonotonicUs: 6_010_000,
    serverSentMonotonicUs: 6_011_000,
  });
  const slower = mapper.observe({
    clientSentMs: 2_000,
    clientReceivedMs: 2_101,
    serverReceivedMonotonicUs: 7_050_000,
    serverSentMonotonicUs: 7_051_000,
  });

  assert.deepEqual(first, { roundTripUs: 20_000, offsetUs: 5_000_000 });
  assert.equal(slower.roundTripUs, 100_000);
  assert.equal(mapper.sampleCount, 2);
  assert.equal(mapper.bestRoundTripUs, 20_000);
  assert.equal(mapper.toServerMonotonicUs(1_500), 6_500_000);
});


test("expires stale clock exchanges instead of reusing an old offset", () => {
  let nowMs = 1_021;
  const mapper = new BrowserPiClockMapper({
    maxAgeMs: 5_000,
    nowMs: () => nowMs,
  });
  mapper.observe({
    clientSentMs: 1_000,
    clientReceivedMs: 1_021,
    serverReceivedMonotonicUs: 6_010_000,
    serverSentMonotonicUs: 6_011_000,
  });
  assert.equal(mapper.isSynchronized, true);
  nowMs = 6_022;
  assert.equal(mapper.isSynchronized, false);
  assert.throws(() => mapper.toServerMonotonicUs(nowMs), /not synchronized/);
});


test("rejects invalid exchanges and use before synchronization", () => {
  const mapper = new BrowserPiClockMapper();

  assert.throws(() => mapper.toServerMonotonicUs(1), /not synchronized/);
  assert.throws(
    () => mapper.observe({
      clientSentMs: 10,
      clientReceivedMs: 9,
      serverReceivedMonotonicUs: 1_000,
      serverSentMonotonicUs: 2_000,
    }),
    /clock exchange/,
  );
  assert.throws(
    () => mapper.observe({
      clientSentMs: 10,
      clientReceivedMs: 11,
      serverReceivedMonotonicUs: 3_000,
      serverSentMonotonicUs: 5_000,
    }),
    /clock exchange/,
  );
});


test("keeps a bounded, ordered pose timeline and finds the nearest sample", () => {
  const timeline = new PoseTimeline({ capacity: 3, maxMatchDeltaMs: 30 });
  timeline.add(pose(1, 1_000_000));
  timeline.add(pose(3, 1_040_000));
  timeline.add(pose(2, 1_020_000));

  assert.equal(timeline.size, 3);
  assert.deepEqual(timeline.match(1_024_000), {
    status: "matched",
    pose: pose(2, 1_020_000),
    deltaUs: 4_000,
  });

  timeline.add(pose(4, 1_060_000));
  assert.equal(timeline.size, 3);
  assert.deepEqual(timeline.match(989_000), {
    status: "pose_stale",
    pose: null,
    deltaUs: 31_000,
  });
});


test("replaces a duplicate event instead of growing the timeline", () => {
  const timeline = new PoseTimeline({ capacity: 3 });
  timeline.add(pose(1, 1_000_000, "vision_degraded"));
  timeline.add(pose(1, 1_001_000, "good"));

  assert.equal(timeline.size, 1);
  assert.equal(timeline.match(1_001_000).pose.quality, "good");
});


test("rejects a pose whose simulated marker contradicts its quality", () => {
  const timeline = new PoseTimeline();
  const inconsistent = pose(1, 1_000_000, "good");
  inconsistent.is_simulated = true;

  assert.throws(() => timeline.add(inconsistent), /invalid browser pose sample/);
});


test("matches video only from captureTime and reports every unavailable layer", () => {
  const mapper = new BrowserPiClockMapper({ nowMs: () => 1_021 });
  const timeline = new PoseTimeline({ maxMatchDeltaMs: 40 });

  assert.deepEqual(matchVideoFrame({ metadata: {}, clockMapper: mapper, timeline }), {
    status: "frame_capture_time_unavailable",
    pose: null,
    deltaUs: null,
  });
  assert.deepEqual(
    matchVideoFrame({ metadata: { captureTime: 100 }, clockMapper: mapper, timeline }),
    { status: "clock_unsynchronized", pose: null, deltaUs: null },
  );

  mapper.observe({
    clientSentMs: 1_000,
    clientReceivedMs: 1_021,
    serverReceivedMonotonicUs: 6_010_000,
    serverSentMonotonicUs: 6_011_000,
  });
  assert.deepEqual(
    matchVideoFrame({ metadata: { captureTime: 100 }, clockMapper: mapper, timeline }),
    { status: "pose_unavailable", pose: null, deltaUs: null },
  );

  timeline.add(pose(7, 5_100_000));
  assert.deepEqual(
    matchVideoFrame({ metadata: { captureTime: 100 }, clockMapper: mapper, timeline }),
    { status: "matched", pose: pose(7, 5_100_000), deltaUs: 0 },
  );
});
