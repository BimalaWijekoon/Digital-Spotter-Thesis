/** Complete authored human/barbell scenes: never retarget or detach equipment. */
import * as THREE from '../vendor/three-r180/three.module.min.js';
import { GLTFLoader } from '../vendor/three-r180/loaders/GLTFLoader.js';
import { getReviewClip, reviewClipTime } from './demo-review-clips.mjs';
import {
  DEMO_POSE_BONE_BY_INDEX,
  DEMO_POSE_REQUIRED_BONES,
  drawDemoPoseGuide,
} from './demo-pose-guide.mjs';

function worldPosition(bone) {
  return bone.getWorldPosition(new THREE.Vector3());
}

function projectedPose(entry, camera) {
  const points = Array(33).fill(null);
  for (const [index, name] of Object.entries(DEMO_POSE_BONE_BY_INDEX)) {
    points[Number(index)] = worldPosition(entry.bones[name]);
  }

  const shoulderLeft = points[11], shoulderRight = points[12];
  const head = worldPosition(entry.bones.Head), neck = worldPosition(entry.bones.neck_01);
  const shoulderWidth = Math.max(.001, shoulderLeft.distanceTo(shoulderRight));
  const lateral = shoulderLeft.clone().sub(shoulderRight).normalize();
  const up = head.clone().sub(neck);
  if (up.lengthSq() < 1e-8) up.set(0, 1, 0);
  else up.normalize();
  const face = head.clone().addScaledVector(up, shoulderWidth * .28);
  const facePoint = (index, side, height) => {
    points[index] = face.clone()
      .addScaledVector(lateral, shoulderWidth * side)
      .addScaledVector(up, shoulderWidth * height);
  };
  facePoint(0, 0, .02);
  facePoint(1, .035, .06); facePoint(2, .065, .06); facePoint(3, .095, .05);
  facePoint(4, -.035, .06); facePoint(5, -.065, .06); facePoint(6, -.095, .05);
  facePoint(7, .16, .015); facePoint(8, -.16, .015);
  facePoint(9, .045, -.075); facePoint(10, -.045, -.075);

  for (const [ankleIndex, toeIndex, heelIndex] of [[27, 31, 29], [28, 32, 30]]) {
    const ankle = points[ankleIndex], toe = points[toeIndex];
    const foot = toe.clone().sub(ankle);
    points[heelIndex] = foot.lengthSq() < 1e-8
      ? ankle.clone() : ankle.clone().addScaledVector(foot, -.28);
  }

  camera.updateMatrixWorld(true);
  return points.map(point => {
    const projected = point.clone().project(camera);
    return {
      x: (projected.x + 1) / 2,
      y: (1 - projected.y) / 2,
      visibility: projected.z >= -1 && projected.z <= 1 ? 1 : 0,
    };
  });
}

export async function createDemoAvatar(canvas, poseCanvas) {
  if (!poseCanvas || typeof poseCanvas.getContext !== 'function') {
    throw new TypeError('demo pose guide canvas is required');
  }
  const loader = new GLTFLoader();
  const scenarios = ['squat', 'deadlift'].flatMap(exercise =>
    ['correct', 'incorrect'].map(form => ({ exercise, form })));
  const entries = await Promise.all(scenarios.map(async ({ exercise, form }) => {
    const definition = getReviewClip(exercise, form);
    const gltf = await loader.loadAsync(definition.url.href);
    const clip = gltf.animations.find(item => item.name === definition.animation);
    if (!clip || !Number.isFinite(clip.duration) || clip.duration <= 0) {
      throw new Error('Review animation unavailable');
    }
    const root = gltf.scene;
    root.traverse(item => { if (item.isMesh) item.frustumCulled = false; });
    const bones = Object.fromEntries(DEMO_POSE_REQUIRED_BONES.map(name => [name, root.getObjectByName(name)]));
    if (Object.values(bones).some(value => !value)) throw new Error('Review pose bones unavailable');
    const mixer = new THREE.AnimationMixer(root);
    const action = mixer.clipAction(clip).setLoop(THREE.LoopOnce, 1);
    action.clampWhenFinished = true;
    return { exercise, form, definition, root, clip, mixer, action, bones };
  }));
  function seek(entry, progress) {
    // A single mixer samples all human AND barbell tracks at the same time.
    // Explicit reset permits deterministic seek/pause and a new repetition.
    entry.action.reset().play();
    entry.mixer.setTime(reviewClipTime(progress, entry.clip.duration));
    entry.root.updateMatrixWorld(true);
  }
  const bounds = new THREE.Box3();
  for (const entry of entries) {
    for (const progress of [0, .25, .5, .75, 1]) {
      seek(entry, progress);
      bounds.expandByObject(entry.root, true);
    }
    seek(entry, 0);
  }
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  if (!Number.isFinite(sphere.radius) || sphere.radius <= 0) throw new Error('Invalid review scene bounds');

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0xf2f6f8);
  const scene = new THREE.Scene();
  entries.forEach(entry => scene.add(entry.root));
  scene.add(new THREE.HemisphereLight(0xffffff, 0xa8b7c4, 2.3));
  const key = new THREE.DirectionalLight(0xffffff, 2.8);
  key.position.set(3, 5, -4); scene.add(key);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(8, 8),
    new THREE.MeshStandardMaterial({ color: 0xe7edf0, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -.002; scene.add(floor);
  const grid = new THREE.GridHelper(6, 20, 0xc2cfd5, 0xd5dfe4);
  grid.position.y = -.001; scene.add(grid);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(.52, 40),
    new THREE.MeshBasicMaterial({ color: 0x718693, transparent: true, opacity: .12, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2; shadow.scale.y = .65; scene.add(shadow);
  const camera = new THREE.PerspectiveCamera(34, 1, .05, 40);
  const direction = new THREE.Vector3(2.6, 1.1, -4).normalize();
  const right = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), direction).normalize();
  const up = new THREE.Vector3().crossVectors(direction, right).normalize();
  const corners = [];
  for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) {
    for (const z of [bounds.min.z, bounds.max.z]) corners.push(new THREE.Vector3(x, y, z).sub(sphere.center));
  }
  let latest = { exercise: 'squat', form: 'correct', progress: 0 };

  function render(config = latest) {
    latest = config;
    const definition = getReviewClip(config.exercise, config.form);
    let activeEntry = null;
    for (const entry of entries) {
      entry.root.visible = definition !== null && entry.definition === definition;
      if (entry.root.visible) { seek(entry, config.progress ?? 0); activeEntry = entry; }
    }
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = renderer.getPixelRatio();
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      const vertical = THREE.MathUtils.degToRad(camera.fov / 2);
      const horizontal = Math.atan(Math.tan(vertical) * camera.aspect);
      // Fit the actual scene box instead of its much larger enclosing sphere.
      // All projected corners stay inside the viewport with a small margin.
      const distance = Math.max(...corners.map(offset => offset.dot(direction) + Math.max(
        Math.abs(offset.dot(right)) / Math.tan(horizontal),
        Math.abs(offset.dot(up)) / Math.tan(vertical)) * 1.08));
      camera.position.copy(sphere.center).addScaledVector(direction, distance);
      camera.lookAt(sphere.center); camera.updateProjectionMatrix();
    }
    renderer.render(scene, camera);
    drawDemoPoseGuide(poseCanvas, activeEntry ? projectedPose(activeEntry, camera) : null);
  }
  const observer = new ResizeObserver(() => render(latest));
  observer.observe(canvas);
  return {
    render,
    dispose() {
      observer.disconnect();
      entries.forEach(entry => { entry.mixer.stopAllAction(); entry.mixer.uncacheRoot(entry.root); });
      const geometries = new Set(), materials = new Set(), skeletons = new Set();
      const textures = new Set(), images = new Set();
      scene.traverse(item => {
        if (item.geometry) geometries.add(item.geometry);
        if (item.material) (Array.isArray(item.material) ? item.material : [item.material]).forEach(value => materials.add(value));
        if (item.skeleton) skeletons.add(item.skeleton);
      });
      for (const material of materials) for (const value of Object.values(material)) {
        if (value?.isTexture) textures.add(value);
      }
      for (const texture of textures) {
        texture.dispose();
        if (typeof texture.source?.data?.close === 'function') images.add(texture.source.data);
      }
      images.forEach(image => image.close());
      geometries.forEach(item => item.dispose()); materials.forEach(item => item.dispose());
      skeletons.forEach(item => item.dispose());
      drawDemoPoseGuide(poseCanvas, null); renderer.dispose();
    },
  };
}
