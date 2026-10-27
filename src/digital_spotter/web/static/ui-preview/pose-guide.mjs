/** Latest-pose visual guide. This does not establish video/pose synchronization. */
import { PoseCanvasOverlay } from '../pose-overlay.mjs';
import { POSE_CONNECTIONS } from './pose-connections.mjs';


export function parsePoseGuide(data) {
  const pose = data?.pose;
  if (data?.version !== 'research_pose_latest_v1' || data.frame_aligned !== false
      || data.state !== 'detected' || !Number.isFinite(data.age_ms)
      || data.age_ms < 0 || data.age_ms > 500 || !pose
      || !['good', 'vision_degraded'].includes(pose.quality)
      || ![pose.image_width, pose.image_height].every(n => Number.isInteger(n) && n > 0 && n <= 8192)
      || !Array.isArray(pose.landmarks) || pose.landmarks.length !== 33
      || !pose.landmarks.every(p => ['x', 'y', 'z', 'visibility'].every(k => Number.isFinite(p?.[k]))
        && p.visibility >= 0 && p.visibility <= 1)) return null;
  return data;
}

export class PoseGuideClient {
  constructor({ fetchFn = (...args) => fetch(...args), onPose,
    isActive = () => true, now = () => performance.now() }) {
    Object.assign(this, { fetchFn, onPose, isActive, now });
    this.inFlight = false;
    this.timer = null;
    this.expiresAt = 0;
  }
  async poll() {
    if (!this.isActive() || this.now() >= this.expiresAt) this.onPose(null);
    if (this.inFlight) return;
    if (!this.isActive()) { this.onPose(null); return; }
    this.inFlight = true;
    const started = this.now();
    try {
      const response = await this.fetchFn('/api/research/pose-latest', { cache: 'no-store' });
      if (!response.ok) throw new Error('pose guide unavailable');
      const data = await response.json();
      if (Number.isFinite(data?.age_ms)) data.age_ms += Math.max(0, this.now() - started);
      const current = this.isActive() ? parsePoseGuide(data) : null;
      this.expiresAt = current ? this.now() + 500 - current.age_ms : 0;
      this.onPose(current);
    } catch { this.onPose(null); }
    finally { this.inFlight = false; }
  }
  start() {
    if (this.timer !== null) return;
    void this.poll();
    this.timer = setInterval(() => this.poll(), 200);
  }
  stop() { clearInterval(this.timer); this.timer = null; this.onPose(null); }
}

export function mountPoseGuide({ video, canvas, status }) {
  const overlay = new PoseCanvasOverlay({ videoElement: video, canvasElement: canvas,
    connections: POSE_CONNECTIONS, fit: 'cover', mirrored: true, minimumVisibility: .15 });
  const client = new PoseGuideClient({
    isActive: () => !document.hidden && !video.hidden && video.readyState >= 2,
    onPose: data => {
      const bounds = video.getBoundingClientRect();
      if (!bounds.width || !bounds.height) { canvas.hidden = true; status.hidden = true; return; }
      const result = overlay.renderDiagnostic(data?.pose, { ageMs: data?.age_ms });
      const visible = result.status === 'diagnostic' && result.visibleLandmarks > 0;
      canvas.hidden = !visible;
      status.hidden = !visible;
      status.textContent = 'Pose guide · unsynced';
    },
  });
  client.start();
  window.addEventListener('pagehide', () => client.stop(), { once: true });
  return client;
}
