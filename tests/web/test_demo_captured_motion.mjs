import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { sampleCapturedSquat } from '../../src/digital_spotter/web/static/ui-preview/demo-captured-motion.mjs';

test('captured squat loops smoothly; incorrect overlay adds lean without becoming model input', async () => {
  const clip = JSON.parse(await readFile(new URL('../../src/digital_spotter/web/static/vendor/cmu-squat/squat.json', import.meta.url)));
  assert.equal(clip.render_only, true);
  assert.equal(clip.classifier_features, false);
  const start = sampleCapturedSquat(clip, 'correct', 0), end = sampleCapturedSquat(clip, 'correct', 1);
  assert.deepEqual(start.hipL, end.hipL);
  const frames = Array.from({ length: 31 }, (_, i) => sampleCapturedSquat(clip, 'correct', i / 30));
  const bottom = frames.reduce((a, b) => a.hipL[1] < b.hipL[1] ? a : b);
  assert.ok(bottom.hipL[1] < start.hipL[1] - .3);
  const bottomProgress = frames.indexOf(bottom) / 30;
  const incorrect = sampleCapturedSquat(clip, 'incorrect', bottomProgress);
  assert.ok(incorrect.captureSpine[2][2] > bottom.captureSpine[2][2]);
  assert.ok(frames.every(frame => frame.captureSpine.every(v => v.every(Number.isFinite))));
});
