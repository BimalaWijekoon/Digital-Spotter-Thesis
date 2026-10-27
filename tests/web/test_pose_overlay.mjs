import assert from "node:assert/strict";
import test from "node:test";

import {
  PoseCanvasOverlay,
  containedVideoRect,
  coveredVideoRect,
  projectLandmark,
} from "../../src/digital_spotter/web/static/pose-overlay.mjs";


function fakeCanvasContext() {
  return {
    arcs: [],
    clears: [],
    lines: [],
    current: null,
    transforms: [],
    beginPath() { this.current = {}; },
    moveTo(x, y) { this.current.from = { x, y }; },
    lineTo(x, y) { this.current.to = { x, y }; },
    stroke() {
      if (this.current?.from && this.current?.to) {
        this.lines.push(this.current);
      }
    },
    arc(x, y, radius) { this.arcs.push({ x, y, radius }); },
    fill() {},
    clearRect(x, y, width, height) { this.clears.push({ x, y, width, height }); },
    setTransform(...values) { this.transforms.push(values); },
    strokeStyle: "",
    fillStyle: "",
    lineCap: "",
    lineWidth: 0,
  };
}


function fakeCanvas(context) {
  return {
    width: 0,
    height: 0,
    style: {},
    getContext(kind) {
      assert.equal(kind, "2d");
      return context;
    },
  };
}


function fakeVideo() {
  return {
    videoWidth: 1280,
    videoHeight: 720,
    getBoundingClientRect() {
      return { width: 1000, height: 1000 };
    },
  };
}


function matchedPose(quality = "good") {
  return {
    status: "matched",
    deltaUs: 4_000,
    pose: {
      image_width: 640,
      image_height: 360,
      quality,
      landmarks: [
        { x: 0, y: 0, z: 0, visibility: 0.9 },
        { x: 1, y: 1, z: 0, visibility: 0.8 },
        { x: 0.5, y: 0.5, z: 0, visibility: 0.1 },
      ],
    },
  };
}


test("computes the visible object-fit contain rectangle", () => {
  assert.deepEqual(containedVideoRect(1000, 1000, 1280, 720), {
    x: 0,
    y: 218.75,
    width: 1000,
    height: 562.5,
  });
  assert.deepEqual(containedVideoRect(1000, 500, 500, 1000), {
    x: 375,
    y: 0,
    width: 250,
    height: 500,
  });
});


test("projects normalized landmarks into the contained video region", () => {
  const rect = containedVideoRect(1000, 1000, 1280, 720);
  assert.deepEqual(projectLandmark({ x: 0.5, y: 0.5 }, rect), { x: 500, y: 500 });
  assert.deepEqual(projectLandmark({ x: 0, y: 0 }, rect), { x: 0, y: 218.75 });
});


test("draws visible joints and connections with device-pixel-ratio scaling", () => {
  const context = fakeCanvasContext();
  const canvas = fakeCanvas(context);
  const states = [];
  const overlay = new PoseCanvasOverlay({
    videoElement: fakeVideo(),
    canvasElement: canvas,
    connections: [[0, 1], [1, 2]],
    minimumVisibility: 0.5,
    devicePixelRatio: () => 2,
    onState: (state) => states.push(state),
  });

  const result = overlay.render(matchedPose());

  assert.deepEqual(result, { status: "rendered", visibleLandmarks: 2 });
  assert.equal(canvas.width, 2000);
  assert.equal(canvas.height, 2000);
  assert.equal(canvas.style.width, "1000px");
  assert.equal(canvas.style.height, "1000px");
  assert.deepEqual(context.transforms.at(-1), [2, 0, 0, 2, 0, 0]);
  assert.deepEqual(context.lines, [{
    from: { x: 0, y: 218.75 },
    to: { x: 1000, y: 781.25 },
  }]);
  assert.deepEqual(context.arcs, [
    { x: 0, y: 218.75, radius: 4 },
    { x: 1000, y: 781.25, radius: 4 },
  ]);
  assert.deepEqual(states.at(-1), {
    state: "rendered",
    reason: null,
    deltaUs: 4_000,
  });
});


test("clears instead of drawing missing, stale, simulated, or degraded pose", () => {
  for (const match of [
    { status: "pose_unavailable", pose: null, deltaUs: null },
    { status: "pose_stale", pose: null, deltaUs: 90_000 },
    matchedPose("simulated"),
    matchedPose("vision_degraded"),
  ]) {
    const context = fakeCanvasContext();
    const overlay = new PoseCanvasOverlay({
      videoElement: fakeVideo(),
      canvasElement: fakeCanvas(context),
      connections: [[0, 1]],
      devicePixelRatio: () => 1,
    });

    const result = overlay.render(match);

    assert.equal(result.status, "cleared");
    assert.equal(context.arcs.length, 0);
    assert.equal(context.lines.length, 0);
    assert.equal(context.clears.length, 1);
  }
});

test('diagnostic guide mirrors cover-cropped video without approving degraded pose', () => {
  assert.deepEqual(coveredVideoRect(1000, 1000, 1280, 720), {
    x: -388.8888888888889, y: 0, width: 1777.7777777777778, height: 1000,
  });
  const context = fakeCanvasContext();
  const overlay = new PoseCanvasOverlay({ videoElement: fakeVideo(),
    canvasElement: fakeCanvas(context), fit: 'cover', mirrored: true,
    connections: [[0, 1]], minimumVisibility: .15 });
  const result = overlay.renderDiagnostic(matchedPose('vision_degraded').pose, { ageMs: 100 });
  assert.equal(result.status, 'diagnostic');
  assert.equal(result.frameAligned, false);
  assert.equal(result.visibleLandmarks, 2);
  assert.ok(context.arcs[0].x > 1000, 'left image landmark mirrors outside the cropped right edge');
  assert.equal(overlay.render(matchedPose('vision_degraded')).status, 'cleared');
  assert.equal(overlay.renderDiagnostic(matchedPose().pose, { ageMs: 501 }).status, 'cleared');
  assert.equal(overlay.renderDiagnostic(matchedPose('simulated').pose, { ageMs: 1 }).status, 'cleared');
});
