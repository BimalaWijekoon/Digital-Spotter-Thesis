import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import * as THREE from '../../src/digital_spotter/web/static/vendor/three-r180/three.module.min.js';
import { createHumanRig } from '../../src/digital_spotter/web/static/ui-preview/demo-human-rig.mjs';
import { sampleDemoPose } from '../../src/digital_spotter/web/static/ui-preview/demo-motion.mjs';
import { sampleCapturedSquat } from '../../src/digital_spotter/web/static/ui-preview/demo-captured-motion.mjs';

test('actual bundled human skeleton bends without stretching bones or losing planted feet', async () => {
  const binary = await readFile(new URL('../../src/digital_spotter/web/static/vendor/quaternius-human/character.glb', import.meta.url));
  const gltf = JSON.parse(binary.subarray(20, 20 + binary.readUInt32LE(12)).toString());
  assert.equal(gltf.images?.length ?? 0, 0);
  assert.ok(gltf.buffers.every(buffer => !buffer.uri)); // No hidden remote asset requests.
  const nodes = gltf.nodes.map(node => {
    const item = new THREE.Bone(); item.name = node.name;
    if (node.translation) item.position.fromArray(node.translation);
    if (node.rotation) item.quaternion.fromArray(node.rotation);
    if (node.scale) item.scale.fromArray(node.scale);
    return item;
  });
  gltf.nodes.forEach((node, index) => node.children?.forEach(child => nodes[index].add(nodes[child])));
  const scene = new THREE.Group();
  gltf.scenes[gltf.scene ?? 0].nodes.forEach(index => scene.add(nodes[index]));
  const lengths = nodes.map(node => node.position.length());
  const rig = createHumanRig(scene);
  const captured = JSON.parse(await readFile(new URL('../../src/digital_spotter/web/static/vendor/cmu-squat/squat.json', import.meta.url)));
  for (const exercise of ['squat', 'deadlift']) {
    const config = { exercise, form: 'incorrect' };
    const pose = exercise === 'squat' ? sampleCapturedSquat(captured, config.form, .5) : sampleDemoPose(exercise, config.form, .5);
    const bar = rig.update(pose, config);
    assert.ok(bar.toArray().every(Number.isFinite));
    for (const node of nodes) assert.ok(node.quaternion.toArray().every(Number.isFinite));
    for (const side of ['l', 'r']) {
      const foot = scene.getObjectByName(`foot_${side}`).getWorldPosition(new THREE.Vector3());
      assert.ok(Math.abs(foot.y - rig.footHeight) < .003, `foot ${side} remains planted`);
    }
  }
  nodes.forEach((node, index) => {
    if (node.name !== 'pelvis') assert.ok(Math.abs(node.position.length() - lengths[index]) < 1e-6);
  });
});
