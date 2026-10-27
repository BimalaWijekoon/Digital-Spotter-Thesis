const ENDPOINT = '/api/research/imu-window';
const COLORS = ['#32668e', '#b47855', '#688d73'];

export function parseIMUWindow(data) {
  if (data?.version !== 'research_imu_window_v1'
      || !['receiving', 'degraded', 'stale', 'unavailable'].includes(data.state)
      || !Array.isArray(data.samples) || data.samples.length > 100) return null;
  for (const sample of data.samples) {
    if (!Number.isSafeInteger(sample?.sequence) || !Number.isFinite(sample.t_ms)
        || !['acceleration_m_s2', 'angular_velocity_rad_s'].every((field) =>
          Array.isArray(sample[field]) && sample[field].length === 3
          && sample[field].every(Number.isFinite))) return null;
  }
  return data;
}

export class IMUWindowClient {
  constructor({ fetchFn = (...args) => globalThis.fetch(...args), onWindow }) {
    this.fetchFn = fetchFn;
    this.onWindow = onWindow;
    this.timer = null;
    this.inFlight = false;
    this.unsupported = false;
  }

  async pollOnce() {
    if (this.inFlight || this.unsupported) return;
    this.inFlight = true;
    try {
      const response = await this.fetchFn(ENDPOINT, { cache: 'no-store' });
      if (response.status === 404) {
        this.unsupported = true;
        this.stop();
        this.onWindow(null);
        return;
      }
      if (!response.ok) throw new Error('IMU window unavailable');
      const window = parseIMUWindow(await response.json());
      if (!window) throw new Error('invalid IMU window');
      this.onWindow(window);
    } catch {
      this.onWindow(null);
    } finally {
      this.inFlight = false;
    }
  }

  start() {
    if (this.timer !== null) return;
    void this.pollOnce();
    this.timer = setInterval(() => { void this.pollOnce(); }, 250);
  }

  stop() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }
}

export function drawIMUChart(canvas, samples, field) {
  const width = Math.max(1, canvas.clientWidth);
  const height = Math.max(1, canvas.clientHeight);
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  context.scale(scale, scale);
  if (samples.length < 2) return;
  const values = samples.flatMap((sample) => sample[field]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 0.1);
  const start = samples[0].t_ms;
  const duration = Math.max(samples.at(-1).t_ms - start, 1);
  for (let axis = 0; axis < 3; axis += 1) {
    context.beginPath();
    context.strokeStyle = COLORS[axis];
    context.lineWidth = 1.7;
    let previous = null;
    for (const sample of samples) {
      const x = 8 + ((sample.t_ms - start) / duration) * (width - 16);
      const y = 10 + (1 - (sample[field][axis] - min) / range) * (height - 20);
      if (previous !== null && (sample.t_ms - previous.t_ms > 120
          || ((sample.sequence - previous.sequence + 65536) % 65536) !== 1)) {
        context.moveTo(x, y);
      } else if (previous === null) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
      previous = sample;
    }
    context.stroke();
  }
}
