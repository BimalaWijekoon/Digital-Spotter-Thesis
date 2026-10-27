import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import { POSE_GUIDE_STYLE } from '../../src/digital_spotter/web/static/pose-overlay.mjs';
import { POSE_CONNECTIONS } from '../../src/digital_spotter/web/static/ui-preview/pose-connections.mjs';
import {
  DEMO_POSE_REQUIRED_BONES,
  drawDemoPoseGuide,
} from '../../src/digital_spotter/web/static/ui-preview/demo-pose-guide.mjs';

function glbNodeNames(buffer) {
  assert.equal(buffer.toString('ascii', 0, 4), 'glTF');
  const jsonLength = buffer.readUInt32LE(12);
  const jsonType = buffer.toString('ascii', 16, 20);
  assert.equal(jsonType, 'JSON');
  const document = JSON.parse(buffer.toString('utf8', 20, 20 + jsonLength).trimEnd());
  return new Set(document.nodes.map(node => node.name).filter(Boolean));
}

function fakeContext() {
  return {
    arcs: [], lines: [], current: null,
    beginPath() { this.current = {}; },
    moveTo(x, y) { this.current.from = { x, y }; },
    lineTo(x, y) { this.current.to = { x, y }; },
    stroke() { if (this.current?.from && this.current?.to) this.lines.push(this.current); },
    arc(x, y, radius) { this.arcs.push({ x, y, radius }); },
    fill() {}, clearRect() {}, setTransform() {},
    strokeStyle: '', fillStyle: '', lineWidth: 0, lineCap: '',
  };
}

test('all four review scenes contain the bones required for the simulated pose guide', async () => {
  const directory = new URL('../../src/digital_spotter/web/static/vendor/exercise-scenarios-character-r1/', import.meta.url);
  for (const file of ['squat_correct.glb', 'squat_forward_lean.glb',
    'deadlift_correct.glb', 'deadlift_spinal_rounding.glb']) {
    const names = glbNodeNames(await readFile(new URL(file, directory)));
    assert.deepEqual(DEMO_POSE_REQUIRED_BONES.filter(name => !names.has(name)), [], file);
  }
});

test('demo guide draws the same 33-point cyan skeleton style as the live pose guide', () => {
  const context = fakeContext();
  const canvas = {
    width: 0, height: 0, style: {},
    getBoundingClientRect: () => ({ width: 400, height: 600 }),
    getContext: kind => { assert.equal(kind, '2d'); return context; },
  };
  const landmarks = Array.from({ length: 33 }, (_, index) => ({
    x: .2 + (index % 6) * .1,
    y: .1 + Math.floor(index / 6) * .13,
    visibility: 1,
  }));
  const result = drawDemoPoseGuide(canvas, landmarks, { devicePixelRatio: 1 });
  assert.deepEqual(result, { status: 'rendered', visibleLandmarks: 33 });
  assert.equal(context.arcs.length, 33);
  assert.equal(context.lines.length, POSE_CONNECTIONS.length);
  assert.equal(context.strokeStyle, POSE_GUIDE_STYLE.strokeStyle);
  assert.equal(context.fillStyle, POSE_GUIDE_STYLE.fillStyle);
  assert.equal(context.lineWidth, POSE_GUIDE_STYLE.lineWidth);
  assert.ok(context.arcs.every(point => point.radius === POSE_GUIDE_STYLE.radius));
});

test('demo page identifies its pose overlay as simulated rather than detected', async () => {
  const root = new URL('../../src/digital_spotter/web/static/ui-preview/', import.meta.url);
  const html = await readFile(new URL('index.html', root), 'utf8');
  assert.match(html, /id="demo-pose-guide-canvas"/);
  assert.match(html, /id="demo-pose-guide-status"[^>]*>Simulated pose guide</);
});
