/** Bake one public CMU capture into a small rendering-only motion clip.
 * ASF/AMC interpretation adapted from OpenGym3D pipeline/motion.py (MIT).
 * Copyright (c) 2026 SylvesterAssiamahGK; original license stored with clip.
 * This does not create classifier features or alter any model/training data.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as T from '../src/digital_spotter/web/static/vendor/three-r180/three.module.min.js';

const [asfPath, amcPath, output, startArg = '30', endArg = '34.5'] = process.argv.slice(2);
if (!asfPath || !amcPath || !output) throw Error('Usage: node scripts/build_demo_squat_motion.mjs skeleton.asf capture.amc NEW-output.json [start_s end_s]');
const [asf, amc] = await Promise.all([readFile(asfPath, 'utf8'), readFile(amcPath, 'utf8')]);
const scale = .0254 / Number(asf.match(/length\s+([\d.]+)/)?.[1] ?? .45);
const rotation = values => new T.Matrix4().makeRotationFromEuler(new T.Euler(...values.map(T.MathUtils.degToRad), 'ZYX'));
const bones = new Map(), parents = new Map();
const expression = /begin\s+id\s+\d+\s+name\s+(\S+)\s+direction\s+([-\d.e ]+?)\s+length\s+([\d.e-]+)\s+axis\s+([-\d.e ]+?)\s+XYZ(?:\s+dof\s+([a-z ]+?))?\s+(?:limits.*?)?end/gs;
for (const match of asf.matchAll(expression)) {
  const [, name, direction, length, axis, dof] = match;
  bones.set(name, { direction: new T.Vector3(...direction.trim().split(/\s+/).map(Number)).normalize().multiplyScalar(Number(length) * scale),
    axis: rotation(axis.trim().split(/\s+/).map(Number)), dof: dof?.trim().split(/\s+/) ?? [] });
}
for (const line of asf.match(/:hierarchy\s+begin(.*?)end/s)[1].trim().split('\n')) {
  const [parent, ...children] = line.trim().split(/\s+/);
  for (const child of children) parents.set(child, parent);
}
const frames = [];
let frame;
for (const line of amc.split('\n')) {
  const text = line.trim();
  if (!text || /^[#:]/.test(text)) continue;
  if (/^\d+$/.test(text)) { frame = {}; frames.push(frame); }
  else { const [name, ...values] = text.split(/\s+/); frame[name] = values.map(Number); }
}
function world(values) {
  const poses = new Map([['root', { position: new T.Vector3(...values.root.slice(0, 3)).multiplyScalar(scale), rotation: rotation(values.root.slice(3)) }]]);
  function calculate(name) {
    if (poses.has(name)) return poses.get(name);
    const bone = bones.get(name), parent = calculate(parents.get(name));
    const dof = {};
    for (let i = 0; i < bone.dof.length; i++) dof[bone.dof[i]] = values[name]?.[i] ?? 0;
    const local = bone.axis.clone().multiply(rotation([dof.rx ?? 0, dof.ry ?? 0, dof.rz ?? 0])).multiply(bone.axis.clone().invert());
    const orientation = parent.rotation.clone().multiply(local);
    const position = bone.direction.clone().transformDirection(orientation).multiplyScalar(bone.direction.length()).add(parent.position);
    const result = { position, rotation: orientation }; poses.set(name, result); return result;
  }
  for (const name of bones.keys()) calculate(name);
  return poses;
}
const start = Number(startArg), end = Number(endArg);
if (!(start >= 0 && end > start && end * 120 <= frames.length)) throw Error('Capture range is invalid');
const raw = [];
for (let index = Math.round(start * 120); index < Math.round(end * 120); index += 4) raw.push(world(frames[index]));
const p = (sample, name) => sample.get(name).position;
const first = raw[0], left = p(first, 'lhipjoint').clone().sub(p(first, 'rhipjoint')).normalize();
const up = p(first, 'upperback').clone().sub(p(first, 'root')).normalize();
const forward = new T.Vector3().crossVectors(left, up).normalize();
const yaw = new T.Quaternion().setFromAxisAngle(new T.Vector3(0, 1, 0), -Math.atan2(forward.x, forward.z));
const floor = Math.min(...['lfoot', 'rfoot', 'ltoes', 'rtoes'].map(name => p(first, name).y));
const bodyScale = .9491 / (p(first, 'root').y - floor);
const origin = p(first, 'root').clone().applyQuaternion(yaw);
const segments = [['root', 'lowerback'], ['lowerback', 'upperback'], ['upperback', 'thorax'], ['lowerneck', 'upperneck'], ['upperneck', 'head']];
const round = vector => vector.toArray().map(value => +value.toFixed(6));
const outputFrames = raw.map(sample => {
  const normalize = name => p(sample, name).clone().applyQuaternion(yaw).sub(origin).multiplyScalar(bodyScale).add(new T.Vector3(0, .9491, 0));
  return { hip: round(normalize('root')), knees: [round(normalize('lfemur')), round(normalize('rfemur'))],
    spine: segments.map(([parent, child]) => round(p(sample, child).clone().sub(p(sample, parent)).applyQuaternion(yaw).normalize())) };
});
// Remove whole-rep travel/endpoint drift for seamless in-place demonstration.
// This is an adapted rendering clip, not an unmodified measurement stream.
const initial = structuredClone(outputFrames[0]), final = structuredClone(outputFrames.at(-1));
for (let index = 0; index < outputFrames.length; index++) {
  const amount = index / (outputFrames.length - 1), frame = outputFrames[index];
  const close = (value, first, last) => value.map((number, axis) => +(number - amount * (last[axis] - first[axis])).toFixed(6));
  frame.hip = close(frame.hip, initial.hip, final.hip);
  frame.knees = frame.knees.map((value, side) => close(value, initial.knees[side], final.knees[side]));
  frame.spine = frame.spine.map((value, bone) => round(new T.Vector3(...close(value, initial.spine[bone], final.spine[bone])).normalize()));
}
const clip = { schema: 'ds_demo_squat_mocap_v1', source: 'CMU Graphics Lab 13_29',
  source_fps: 120, fps: 30, source_range_s: [start, end], coordinate_frame: 'Y-up, X-left, Z-forward',
  source_sha256: { asf: createHash('sha256').update(asf).digest('hex'), amc: createHash('sha256').update(amc).digest('hex') },
  render_only: true, classifier_features: false, in_place_loop: true, frames: outputFrames };
await writeFile(output, JSON.stringify(clip) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ path: output, frames: outputFrames.length, startHip: outputFrames[0].hip,
  endHip: outputFrames.at(-1).hip, hipMin: Math.min(...outputFrames.map(f => f.hip[1])),
  heights: outputFrames.filter((_, i) => i % 15 === 0).map((f, i) => [start + i * .5, f.hip[1]]) }));
