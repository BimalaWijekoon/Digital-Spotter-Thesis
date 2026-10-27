import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { getReviewClip, reviewClipTime } from '../../src/digital_spotter/web/static/ui-preview/demo-review-clips.mjs';

test('all four supplied scenes are intact offline GLBs with shared body and equipment timelines', async () => {
  for (const exercise of ['squat', 'deadlift']) for (const form of ['correct', 'incorrect']) {
    const definition = getReviewClip(exercise, form);
    assert.ok(definition, `Missing ${exercise}/${form} review clip`);
    const bytes = await readFile(definition.url);
    assert.equal(createHash('sha256').update(bytes).digest('hex'), definition.sha256);
    assert.equal(bytes.readUInt32LE(0), 0x46546c67);
    assert.equal(bytes.readUInt32LE(4), 2);
    assert.equal(bytes.readUInt32LE(8), bytes.length);
    const gltf = JSON.parse(bytes.subarray(20, 20 + bytes.readUInt32LE(12)).toString());
    assert.deepEqual(gltf.extensionsRequired ?? [], []);
    assert.ok(gltf.buffers.every(buffer => buffer.uri === undefined));
    // The new character has embedded textures; external image URIs remain forbidden.
    assert.ok(gltf.images.length > 0);
    for (const image of gltf.images) {
      assert.equal(image.uri, undefined);
      assert.equal(image.mimeType, 'image/png');
      assert.ok(Number.isInteger(image.bufferView) && gltf.bufferViews[image.bufferView]);
    }
    assert.equal(gltf.animations.length, 1);
    const clip = gltf.animations[0];
    assert.equal(clip.name, definition.animation);
    for (const name of ['hand_l', 'hand_r', 'barbell']) {
      const index = gltf.nodes.findIndex(node => node.name?.toLowerCase() === name);
      assert.ok(index >= 0 && clip.channels.some(channel => channel.target.node === index));
      assert.ok(gltf.skins[0].joints.includes(index));
    }
  }
});

test('each incorrect scenario uses its own authored clip, not a relabelled correct scene', () => {
  assert.equal(getReviewClip('squat', 'incorrect').animation, 'Squat_ExcessiveForwardLean');
  assert.equal(getReviewClip('deadlift', 'incorrect').animation, 'Deadlift_SpinalRounding');
  for (const exercise of ['squat', 'deadlift']) {
    assert.notEqual(getReviewClip(exercise, 'correct').url.href, getReviewClip(exercise, 'incorrect').url.href);
    assert.notEqual(getReviewClip(exercise, 'correct').sha256, getReviewClip(exercise, 'incorrect').sha256);
  }
  assert.equal(reviewClipTime(0, 5.3), 0);
  assert.equal(reviewClipTime(.5, 5.3), 2.65);
  assert.equal(reviewClipTime(1, 5.3), 5.3);
  assert.throws(() => reviewClipTime(NaN, 5.3), /Invalid review playback/);
});
