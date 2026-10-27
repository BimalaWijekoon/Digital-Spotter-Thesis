/** Retarget illustrative movement to the bundled CC0 skin; no ML features. */
import * as THREE from '../vendor/three-r180/three.module.min.js';

export function createHumanRig(model) {
  model.updateMatrixWorld(true);
  const bind = new Map(), bones = new Map();
  model.traverse(bone => {
    if (!bone.isBone) return;
    bones.set(bone.name, bone);
    bind.set(bone, { position: bone.position.clone(), quaternion: bone.quaternion.clone(),
      worldPosition: bone.getWorldPosition(new THREE.Vector3()),
      worldQuaternion: bone.getWorldQuaternion(new THREE.Quaternion()) });
  });
  const bone = name => {
    if (!bones.has(name)) throw new Error(`Human rig missing ${name}`);
    return bones.get(name);
  };
  for (const name of ['pelvis', 'spine_01', 'spine_02', 'spine_03', 'neck_01', 'Head',
    ...['l', 'r'].flatMap(side => ['thigh', 'calf', 'foot', 'upperarm', 'lowerarm', 'hand'].map(part => `${part}_${side}`))]) bone(name);
  const axisX = new THREE.Vector3(1, 0, 0);
  const worldPosition = item => item.getWorldPosition(new THREE.Vector3());
  const restHip = bind.get(bone('pelvis')).worldPosition.clone();
  const footHeight = bind.get(bone('foot_l')).worldPosition.y;

  function worldRotation(item, quaternion) {
    const parent = item.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
    item.quaternion.copy(parent.multiply(quaternion));
    item.updateWorldMatrix(false, true);
  }
  function pitch(name, angle) {
    const item = bone(name);
    worldRotation(item, new THREE.Quaternion().setFromAxisAngle(axisX, angle)
      .multiply(bind.get(item).worldQuaternion));
  }
  function aim(item, child, target) {
    const original = bind.get(child).worldPosition.clone().sub(bind.get(item).worldPosition).normalize();
    const desired = target.clone().sub(worldPosition(item)).normalize();
    const rotation = new THREE.Quaternion().setFromUnitVectors(original, desired)
      .multiply(bind.get(item).worldQuaternion);
    worldRotation(item, rotation);
  }
  function limb(upper, lower, end, target, pole) {
    const start = worldPosition(upper);
    const first = bind.get(lower).worldPosition.distanceTo(bind.get(upper).worldPosition);
    const second = bind.get(end).worldPosition.distanceTo(bind.get(lower).worldPosition);
    const direction = target.clone().sub(start);
    const reach = THREE.MathUtils.clamp(direction.length(), Math.abs(first - second) + 1e-5, first + second - 1e-5);
    direction.normalize();
    const bendDirection = pole.clone().sub(start);
    bendDirection.addScaledVector(direction, -bendDirection.dot(direction)).normalize();
    const along = (first * first - second * second + reach * reach) / (2 * reach);
    const height = Math.sqrt(Math.max(0, first * first - along * along));
    const knee = start.clone().addScaledVector(direction, along).addScaledVector(bendDirection, height);
    aim(upper, lower, knee);
    aim(lower, end, start.addScaledVector(direction, reach));
  }

  return {
    footHeight,
    update(pose, { exercise = 'squat' } = {}) {
      for (const [item, rest] of bind) {
        item.position.copy(rest.position); item.quaternion.copy(rest.quaternion);
      }
      model.updateMatrixWorld(true);
      const hip = new THREE.Vector3().fromArray(pose.hipL).add(new THREE.Vector3().fromArray(pose.hipR)).multiplyScalar(.5);
      const shoulders = new THREE.Vector3().fromArray(pose.shoulderL).add(new THREE.Vector3().fromArray(pose.shoulderR)).multiplyScalar(.5);
      const trunk = Math.atan2(shoulders.z - hip.z, shoulders.y - hip.y);
      const pelvis = bone('pelvis');
      const desiredHip = restHip.clone().add(new THREE.Vector3(hip.x, hip.y - 1.03, hip.z));
      // The asset's arms are shorter than the old drawing's: lower its setup
      // naturally rather than stretching arm bones to reach a floor-level bar.
      if (exercise === 'deadlift') desiredHip.y -= .12 * THREE.MathUtils.clamp((.99 - pose.bar[1]) / .76, 0, 1);
      pelvis.position.copy(pelvis.parent.worldToLocal(desiredHip));
      model.updateMatrixWorld(true);
      if (pose.captureSpine) {
        for (const [name, child, index] of [['pelvis', 'spine_01', 0], ['spine_01', 'spine_02', 0],
          ['spine_02', 'spine_03', 1], ['spine_03', 'neck_01', 2], ['neck_01', 'Head', 3]]) {
          const target = worldPosition(bone(name)).add(new THREE.Vector3(...pose.captureSpine[index]));
          aim(bone(name), bone(child), target);
        }
        const direction = new THREE.Vector3(...pose.captureSpine[4]);
        worldRotation(bone('Head'), new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction)
          .multiply(bind.get(bone('Head')).worldQuaternion));
      } else {
        for (const [name, amount] of [['pelvis', .22], ['spine_01', .48], ['spine_02', .76],
          ['spine_03', 1], ['neck_01', .35], ['Head', .20]]) pitch(name, trunk * amount);
      }

      for (const [side, drawingSide, sign] of [['l', 'R', 1], ['r', 'L', -1]]) {
        // The drawing's L/R are screen-side names, not the skin's anatomical sides.
        const restFoot = bind.get(bone(`foot_${side}`)).worldPosition;
        const target = new THREE.Vector3(sign * .18, footHeight, restFoot.z);
        const pole = new THREE.Vector3().fromArray(pose[`knee${drawingSide}`]);
        if (!pose.captureSpine) pole.z += .35;
        limb(bone(`thigh_${side}`), bone(`calf_${side}`), bone(`foot_${side}`), target, pole);
        worldRotation(bone(`foot_${side}`), bind.get(bone(`foot_${side}`)).worldQuaternion.clone());
      }

      const neck = worldPosition(bone('neck_01'));
      const bar = exercise === 'squat'
        ? neck.clone().add(new THREE.Vector3(0, -.02, -.11))
        : new THREE.Vector3(0, .23 + .48 * THREE.MathUtils.clamp((pose.bar[1] - .23) / .76, 0, 1), pose.bar[2]);
      for (const [side, sign] of [['l', 1], ['r', -1]]) {
        const shoulder = worldPosition(bone(`upperarm_${side}`));
        const wrist = bar.clone().add(new THREE.Vector3(sign * (exercise === 'squat' ? .43 : .29), exercise === 'squat' ? .035 : .10, .015));
        const elbow = shoulder.clone().add(new THREE.Vector3(sign * .20, -.30, exercise === 'squat' ? -.30 : .10));
        limb(bone(`upperarm_${side}`), bone(`lowerarm_${side}`), bone(`hand_${side}`), wrist, elbow);
        for (const digit of ['index', 'middle', 'ring', 'pinky']) {
          for (let joint = 1; joint <= 3; joint++) {
            const finger = bones.get(`${digit}_0${joint}_${side}`);
            if (finger) finger.quaternion.copy(bind.get(finger).quaternion)
              .multiply(new THREE.Quaternion().setFromAxisAngle(axisX, joint === 1 ? .55 : .85));
          }
        }
      }
      model.updateMatrixWorld(true);
      return bar;
    },
  };
}
