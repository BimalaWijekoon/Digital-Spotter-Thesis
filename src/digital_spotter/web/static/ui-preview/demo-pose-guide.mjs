/** Presentation-only pose guide drawn from authored animation bones. */
import { POSE_GUIDE_STYLE } from '../pose-overlay.mjs';
import { POSE_CONNECTIONS } from './pose-connections.mjs';

export const DEMO_POSE_BONE_BY_INDEX = Object.freeze({
  11: 'upperarm_l', 12: 'upperarm_r',
  13: 'lowerarm_l', 14: 'lowerarm_r',
  15: 'hand_l', 16: 'hand_r',
  17: 'pinky_01_l', 18: 'pinky_01_r',
  19: 'index_01_l', 20: 'index_01_r',
  21: 'thumb_01_l', 22: 'thumb_01_r',
  23: 'thigh_l', 24: 'thigh_r',
  25: 'calf_l', 26: 'calf_r',
  27: 'foot_l', 28: 'foot_r',
  31: 'ball_leaf_l', 32: 'ball_leaf_r',
});

export const DEMO_POSE_REQUIRED_BONES = Object.freeze([
  'Head', 'neck_01', ...new Set(Object.values(DEMO_POSE_BONE_BY_INDEX)),
]);

export function drawDemoPoseGuide(canvas, landmarks, {
  devicePixelRatio = globalThis.devicePixelRatio ?? 1,
} = {}) {
  if (!canvas || typeof canvas.getContext !== 'function'
      || typeof canvas.getBoundingClientRect !== 'function') {
    throw new TypeError('demo pose canvas is required');
  }
  const context = canvas.getContext('2d');
  if (!context) throw new Error('demo pose canvas context is unavailable');
  const rect = canvas.getBoundingClientRect();
  if (!Number.isFinite(rect.width) || !Number.isFinite(rect.height)
      || rect.width <= 0 || rect.height <= 0) {
    return { status: 'cleared', visibleLandmarks: 0 };
  }
  const ratio = Number.isFinite(devicePixelRatio) && devicePixelRatio > 0
    ? devicePixelRatio : 1;
  const pixelWidth = Math.max(1, Math.round(rect.width * ratio));
  const pixelHeight = Math.max(1, Math.round(rect.height * ratio));
  if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  if (!Array.isArray(landmarks) || landmarks.length !== 33) {
    return { status: 'cleared', visibleLandmarks: 0 };
  }
  const visible = new Map();
  landmarks.forEach((point, index) => {
    if (Number.isFinite(point?.x) && Number.isFinite(point?.y)
        && point.x >= 0 && point.x <= 1 && point.y >= 0 && point.y <= 1
        && Number.isFinite(point.visibility) && point.visibility >= .15) {
      visible.set(index, { x: point.x * rect.width, y: point.y * rect.height });
    }
  });
  context.strokeStyle = POSE_GUIDE_STYLE.strokeStyle;
  context.fillStyle = POSE_GUIDE_STYLE.fillStyle;
  context.lineWidth = POSE_GUIDE_STYLE.lineWidth;
  context.lineCap = POSE_GUIDE_STYLE.lineCap;
  for (const [fromIndex, toIndex] of POSE_CONNECTIONS) {
    const from = visible.get(fromIndex), to = visible.get(toIndex);
    if (!from || !to) continue;
    context.beginPath(); context.moveTo(from.x, from.y); context.lineTo(to.x, to.y); context.stroke();
  }
  for (const point of visible.values()) {
    context.beginPath(); context.arc(point.x, point.y, POSE_GUIDE_STYLE.radius, 0, Math.PI * 2); context.fill();
  }
  return { status: 'rendered', visibleLandmarks: visible.size };
}
