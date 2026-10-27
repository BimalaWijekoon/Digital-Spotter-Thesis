/** Letterbox-aware pose drawing for a canvas layered over a video element. */

const DEFAULT_CONNECTIONS = Object.freeze([
  [11, 12], [11, 23], [12, 24], [23, 24],
  [23, 25], [24, 26], [25, 27], [26, 28],
  [27, 29], [28, 30], [29, 31], [30, 32],
  [27, 31], [28, 32],
]);

export const POSE_GUIDE_STYLE = Object.freeze({
  strokeStyle: 'rgba(0, 229, 255, 0.65)',
  fillStyle: 'rgba(0, 229, 255, 0.9)',
  lineWidth: 2,
  lineCap: 'round',
  radius: 4,
});


function positiveFinite(value, name) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${name} must be a positive finite number`);
  }
}


export function containedVideoRect(containerWidth, containerHeight, mediaWidth, mediaHeight) {
  positiveFinite(containerWidth, "containerWidth");
  positiveFinite(containerHeight, "containerHeight");
  positiveFinite(mediaWidth, "mediaWidth");
  positiveFinite(mediaHeight, "mediaHeight");

  const scale = Math.min(containerWidth / mediaWidth, containerHeight / mediaHeight);
  const width = mediaWidth * scale;
  const height = mediaHeight * scale;
  return {
    x: (containerWidth - width) / 2,
    y: (containerHeight - height) / 2,
    width,
    height,
  };
}


export function projectLandmark(landmark, videoRect) {
  const normalizedX = Math.min(1, Math.max(0, landmark.x));
  const normalizedY = Math.min(1, Math.max(0, landmark.y));
  return {
    x: videoRect.x + (normalizedX * videoRect.width),
    y: videoRect.y + (normalizedY * videoRect.height),
  };
}

export function coveredVideoRect(containerWidth, containerHeight, mediaWidth, mediaHeight) {
  positiveFinite(containerWidth, 'containerWidth');
  positiveFinite(containerHeight, 'containerHeight');
  positiveFinite(mediaWidth, 'mediaWidth');
  positiveFinite(mediaHeight, 'mediaHeight');
  const scale = Math.max(containerWidth / mediaWidth, containerHeight / mediaHeight);
  const width = mediaWidth * scale;
  const height = mediaHeight * scale;
  return { x: (containerWidth - width) / 2, y: (containerHeight - height) / 2, width, height };
}


export class PoseCanvasOverlay {
  constructor({
    videoElement,
    canvasElement,
    connections = DEFAULT_CONNECTIONS,
    minimumVisibility = 0.5,
    fit = 'contain',
    mirrored = false,
    devicePixelRatio = () => globalThis.devicePixelRatio ?? 1,
    onState = () => {},
  }) {
    if (!videoElement || typeof videoElement.getBoundingClientRect !== 'function') {
      throw new TypeError("videoElement is required");
    }
    if (!canvasElement || typeof canvasElement.getContext !== 'function') {
      throw new TypeError("canvasElement is required");
    }
    if (!Array.isArray(connections)) {
      throw new TypeError("connections must be an array");
    }
    if (
      typeof minimumVisibility !== 'number'
      || minimumVisibility < 0
      || minimumVisibility > 1
    ) {
      throw new RangeError("minimumVisibility must be between 0 and 1");
    }

    const context = canvasElement.getContext('2d');
    if (!context) {
      throw new Error("2D canvas context is unavailable");
    }

    this.videoElement = videoElement;
    this.canvasElement = canvasElement;
    this.context = context;
    this.connections = connections;
    this.minimumVisibility = minimumVisibility;
    if (!['contain', 'cover'].includes(fit)) throw new RangeError('unsupported video fit');
    this.fit = fit;
    this.mirrored = mirrored;
    this.devicePixelRatio = devicePixelRatio;
    this.onState = onState;
  }

  render(match) {
    const viewport = this.#resizeCanvas();
    this.context.clearRect(0, 0, viewport.width, viewport.height);

    if (match?.status !== 'matched' || !match.pose) {
      return this.#cleared(match?.status ?? "pose_unavailable", match?.deltaUs ?? null);
    }
    if (match.pose.quality !== 'good') {
      return this.#cleared(`pose_quality_${match.pose.quality ?? 'unknown'}`, match.deltaUs ?? null);
    }

    return this.#drawPose(match.pose, viewport, { deltaUs: match.deltaUs ?? null });
  }

  renderDiagnostic(pose, { ageMs } = {}) {
    const viewport = this.#resizeCanvas();
    this.context.clearRect(0, 0, viewport.width, viewport.height);
    if (!pose || !['good', 'vision_degraded'].includes(pose.quality)
        || !Number.isFinite(ageMs) || ageMs < 0 || ageMs > 500) {
      return this.#cleared('diagnostic_pose_unavailable', null);
    }
    return this.#drawPose(pose, viewport, { diagnostic: true });
  }

  #drawPose(pose, viewport, { diagnostic = false, deltaUs = null }) {
    const mediaWidth = this.videoElement.videoWidth || pose.image_width;
    const mediaHeight = this.videoElement.videoHeight || pose.image_height;
    const videoRect = (this.fit === 'cover' ? coveredVideoRect : containedVideoRect)(
      viewport.width,
      viewport.height,
      mediaWidth,
      mediaHeight,
    );
    const visible = new Map();
    pose.landmarks.forEach((landmark, index) => {
      if (
        Number.isFinite(landmark?.x)
        && Number.isFinite(landmark?.y)
        && Number.isFinite(landmark?.visibility)
        && landmark.visibility >= this.minimumVisibility
        && (!diagnostic || (landmark.x >= 0 && landmark.x <= 1
          && landmark.y >= 0 && landmark.y <= 1))
      ) {
        const point = projectLandmark(landmark, videoRect);
        if (this.mirrored) point.x = viewport.width - point.x;
        visible.set(index, point);
      }
    });

    this.context.strokeStyle = POSE_GUIDE_STYLE.strokeStyle;
    this.context.lineWidth = POSE_GUIDE_STYLE.lineWidth;
    this.context.lineCap = POSE_GUIDE_STYLE.lineCap;
    for (const [fromIndex, toIndex] of this.connections) {
      const from = visible.get(fromIndex);
      const to = visible.get(toIndex);
      if (!from || !to) {
        continue;
      }
      this.context.beginPath();
      this.context.moveTo(from.x, from.y);
      this.context.lineTo(to.x, to.y);
      this.context.stroke();
    }

    this.context.fillStyle = POSE_GUIDE_STYLE.fillStyle;
    for (const point of visible.values()) {
      this.context.beginPath();
      this.context.arc(point.x, point.y, POSE_GUIDE_STYLE.radius, 0, Math.PI * 2);
      this.context.fill();
    }

    if (diagnostic) {
      this.onState({ state: 'diagnostic', reason: 'latest_pose_not_frame_aligned', deltaUs: null });
      return { status: 'diagnostic', visibleLandmarks: visible.size, frameAligned: false };
    }
    this.onState({ state: "rendered", reason: null, deltaUs });
    return { status: "rendered", visibleLandmarks: visible.size };
  }

  clear(reason = "cleared") {
    const viewport = this.#resizeCanvas();
    this.context.clearRect(0, 0, viewport.width, viewport.height);
    return this.#cleared(reason, null);
  }

  #cleared(reason, deltaUs) {
    this.onState({ state: "cleared", reason, deltaUs });
    return { status: "cleared", reason };
  }

  #resizeCanvas() {
    const rect = this.videoElement.getBoundingClientRect();
    positiveFinite(rect.width, "video display width");
    positiveFinite(rect.height, "video display height");
    const rawRatio = this.devicePixelRatio();
    const ratio = Number.isFinite(rawRatio) && rawRatio > 0 ? rawRatio : 1;
    const pixelWidth = Math.max(1, Math.round(rect.width * ratio));
    const pixelHeight = Math.max(1, Math.round(rect.height * ratio));

    if (this.canvasElement.width !== pixelWidth) {
      this.canvasElement.width = pixelWidth;
    }
    if (this.canvasElement.height !== pixelHeight) {
      this.canvasElement.height = pixelHeight;
    }
    this.canvasElement.style.width = `${rect.width}px`;
    this.canvasElement.style.height = `${rect.height}px`;
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    return { width: rect.width, height: rect.height };
  }
}
