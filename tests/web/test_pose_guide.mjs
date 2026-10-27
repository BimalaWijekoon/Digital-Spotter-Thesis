import assert from 'node:assert/strict';
import test from 'node:test';
import { PoseGuideClient, parsePoseGuide } from '../../src/digital_spotter/web/static/ui-preview/pose-guide.mjs';

const sample = () => ({ version: 'research_pose_latest_v1', state: 'detected',
  frame_aligned: false, age_ms: 100, pose: { quality: 'vision_degraded',
    image_width: 640, image_height: 360,
    landmarks: Array.from({ length: 33 }, () => ({ x: .5, y: .5, z: 0, visibility: .3 })) } });

test('guide accepts bounded real detections but rejects stale, missing and simulated data', () => {
  assert.equal(parsePoseGuide(sample()).pose.landmarks.length, 33);
  const stale = sample(); stale.age_ms = 501;
  assert.equal(parsePoseGuide(stale), null);
  const simulated = sample(); simulated.pose.quality = 'simulated';
  assert.equal(parsePoseGuide(simulated), null);
  const short = sample(); short.pose.landmarks.pop();
  assert.equal(parsePoseGuide(short), null);
  const unknownAge = sample(); unknownAge.age_ms = null;
  assert.equal(parsePoseGuide(unknownAge), null);
  assert.equal(parsePoseGuide({ state: 'not_found' }), null);
});

test('network-delayed pose is cleared, with no polling while video is hidden', async () => {
  let clock = 0, active = true, calls = 0, shown;
  const client = new PoseGuideClient({ isActive: () => active,
    now: () => clock, onPose: value => { shown = value; },
    fetchFn: async () => { calls++; clock += 450;
      return { ok: true, json: async () => sample() }; } });
  await client.poll();
  assert.equal(shown, null);
  active = false;
  await client.poll();
  assert.equal(calls, 1);
});

test('in-flight network request cannot keep an expired skeleton visible', async () => {
  let clock = 0, shown, release;
  const client = new PoseGuideClient({ now: () => clock, onPose: value => { shown = value; },
    fetchFn: async () => new Promise(resolve => { release = resolve; }) });
  client.expiresAt = 400;
  const pending = client.poll();
  clock = 600;
  await client.poll();
  assert.equal(shown, null);
  release({ ok: false });
  await pending;
});
