import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { DemoPlayback, sampleDemoPose } from '../../src/digital_spotter/web/static/ui-preview/demo-motion.mjs';

test('squat and deadlift scenarios produce finite distinct 3D poses', () => {
  const standing = sampleDemoPose('squat', 'correct', 0);
  const bottom = sampleDemoPose('squat', 'correct', .5);
  const incorrect = sampleDemoPose('squat', 'incorrect', .5);
  const setup = sampleDemoPose('deadlift', 'correct', 0);
  const lockout = sampleDemoPose('deadlift', 'correct', .5);
  assert.ok(bottom.hipL[1] < standing.hipL[1]);
  assert.ok(setup.hipL[1] < lockout.hipL[1]);
  assert.ok(incorrect.shoulderL[2] > bottom.shoulderL[2]);
  for (const pose of [standing, bottom, incorrect, setup, lockout]) {
    for (const point of Object.values(pose)) {
      assert.equal(point.length, 3);
      assert.ok(point.every(Number.isFinite));
    }
  }
});

test('playback pauses without advancing and stops after three repetitions', () => {
  const player = new DemoPlayback();
  player.start(1000);
  assert.equal(player.tick(2500).elapsedMs, 1500);
  player.pause(2500);
  assert.equal(player.tick(10000).elapsedMs, 1500);
  player.start(10000);
  assert.equal(player.tick(11500).elapsedMs, 3000);
  const completed = player.tick(30000);
  assert.equal(completed.state, 'complete');
  assert.equal(completed.completedReps, 3);
  player.reset();
  assert.equal(player.snapshot().state, 'idle');
  assert.equal(player.snapshot().completedReps, 0);
});

test('demo is a third dashboard tab with scenario rather than prediction selection', async () => {
  const root = new URL('../../src/digital_spotter/web/static/ui-preview/', import.meta.url);
  const html = await readFile(new URL('index.html', root), 'utf8');
  assert.match(html, /id="demo-tab"[^>]*role="tab"[^>]*aria-controls="demo-view"/);
  assert.match(html, /id="demo-view"[^>]*role="tabpanel"[^>]*hidden/);
  assert.match(html, /id="demo-exercise"/);
  assert.match(html, /id="demo-form"/);
  assert.match(html, /id="demo-canvas"/);
  const controller = await readFile(new URL('demo-page.mjs', root), 'utf8');
  assert.match(controller, /DemoInferenceClient/);
  assert.doesNotMatch(controller, /predicted_class\s*[:=](?!=)|\.command\(|\/api\/workout\/command/);
});
