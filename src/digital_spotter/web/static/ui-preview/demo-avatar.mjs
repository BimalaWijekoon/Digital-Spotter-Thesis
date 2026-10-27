/** Offline CC0 skinned human; no camera capture, tracking or inference. */
import * as THREE from '../vendor/three-r180/three.module.min.js';
import { GLTFLoader } from '../vendor/three-r180/loaders/GLTFLoader.js';
import { createHumanRig } from './demo-human-rig.mjs';
import { sampleCapturedSquat } from './demo-captured-motion.mjs';

export async function createDemoAvatar(canvas) {
  const [{ scene: human }, squatMotion] = await Promise.all([
    new GLTFLoader().loadAsync(new URL('../vendor/quaternius-human/character.glb', import.meta.url).href),
    fetch(new URL('../vendor/cmu-squat/squat.json', import.meta.url)).then(response => {
      if (!response.ok) throw new Error('Squat motion unavailable');
      return response.json();
    }),
  ]);
  const rig = createHumanRig(human);
  // Render-only gym colours, authored over the intact CC0 skin in its bind pose.
  const palette = Object.fromEntries(Object.entries({ skin: 0xbe937e, shirt: 0x6388a5,
    pants: 0x34485c, shoes: 0x26323e }).map(([name, value]) => [name, new THREE.Color(value)]));
  human.traverse(item => {
    if (!item.isMesh) return;
    item.frustumCulled = false;
    const position = item.geometry.getAttribute('position');
    const colors = new Float32Array(position.count * 3);
    for (let index = 0; index < position.count; index++) {
      const x = Math.abs(position.getX(index)), y = position.getY(index);
      const color = item.name === 'Eyes' || item.name === 'Eyebrows' ? palette.shoes
        : y < .13 ? palette.shoes : y < 1.0 ? palette.pants
          : y < 1.54 && x < .40 ? palette.shirt : palette.skin;
      color.toArray(colors, index * 3);
    }
    item.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    item.material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .85 });
  });
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0xf2f6f8);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(29, 1, .1, 30);
  camera.position.set(2.5, 1.5, 3.4);
  camera.lookAt(0, .95, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0xa8b7c4, 2.3));
  const key = new THREE.DirectionalLight(0xffffff, 3);
  key.position.set(3, 5, 4);
  scene.add(key);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(8, 8),
    new THREE.MeshStandardMaterial({ color: 0xe7edf0, roughness: 1 }));
  floor.rotation.x = -Math.PI / 2;
  scene.add(floor);
  const grid = new THREE.GridHelper(6, 20, 0xc2cfd5, 0xd5dfe4);
  grid.position.y = .002;
  scene.add(grid);
  const shadow = new THREE.Mesh(new THREE.CircleGeometry(.62, 40),
    new THREE.MeshBasicMaterial({ color: 0x8e9faa, transparent: true, opacity: .14, depthWrite: false }));
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = .004;
  shadow.scale.y = .65;
  scene.add(shadow);

  scene.add(human);
  const material = color => new THREE.MeshStandardMaterial({ color, roughness: .65 });
  const dark = material(0x283a49), metal = material(0x9aa9b4);
  const mesh = (geometry, mat) => { const item = new THREE.Mesh(geometry, mat); scene.add(item); return item; };
  const belt = mesh(new THREE.TorusGeometry(.17, .012, 8, 32), dark);
  belt.rotation.x = Math.PI / 2; belt.scale.y = .72;
  const wearable = mesh(new THREE.BoxGeometry(.09, .08, .04), metal);
  const pelvis = human.getObjectByName('pelvis');
  const bar = new THREE.Group();
  const barShaft = new THREE.Mesh(new THREE.CylinderGeometry(.018, .018, 1.55, 14), metal);
  barShaft.rotation.z = Math.PI / 2;
  bar.add(barShaft);
  for (const sign of [-1, 1]) {
    const plate = new THREE.Mesh(new THREE.CylinderGeometry(.18, .18, .075, 30), dark);
    plate.rotation.z = Math.PI / 2;
    plate.position.x = sign * .60;
    bar.add(plate);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(.065, .065, .085, 20), metal);
    hub.rotation.z = Math.PI / 2;
    hub.position.x = sign * .60;
    bar.add(hub);
  }
  scene.add(bar);
  let latest, latestConfig;

  function render(pose, config = {}) {
    latest = pose; latestConfig = config;
    if (config.exercise === 'squat') pose = sampleCapturedSquat(squatMotion, config.form, config.progress ?? 0);
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!width || !height) return;
    const ratio = renderer.getPixelRatio();
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }
    bar.position.copy(rig.update(pose, config));
    pelvis.getWorldPosition(belt.position); belt.position.y += .035;
    wearable.position.copy(belt.position); wearable.position.z -= .12;
    renderer.render(scene, camera);
  }
  const observer = new ResizeObserver(() => { if (latest) render(latest, latestConfig); });
  observer.observe(canvas);
  return {
    render,
    dispose() {
      observer.disconnect();
      const geometries = new Set(), materials = new Set(), skeletons = new Set();
      scene.traverse(item => {
        if (item.geometry) geometries.add(item.geometry);
        if (item.material) materials.add(item.material);
        if (item.skeleton) skeletons.add(item.skeleton);
      });
      geometries.forEach(item => item.dispose()); materials.forEach(item => item.dispose());
      skeletons.forEach(item => item.dispose());
      renderer.dispose();
    },
  };
}
