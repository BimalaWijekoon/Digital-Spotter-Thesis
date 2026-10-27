// Original synthetic phase summaries, never a generated high-rate sensor stream.
const COLORS = ['#32668e', '#b47855', '#688d73'];
const FIELDS = ['acceleration_m_s2', 'angular_velocity_rad_s'];

export function parseReplayIMU(value) {
  if (value?.version !== 'demo_phase_imu_v1' || value.source !== 'synthetic_training_replay' ||
      value.representation !== 'phase_medians' || value.measured_timestamps !== false ||
      value.units?.acceleration_m_s2 !== 'm/s^2' || value.units?.angular_velocity_rad_s !== 'rad/s' ||
      !Array.isArray(value.phases) || value.phases.length !== 3 ||
      !value.phases.every((row, index) => row?.phase === index + 1 && FIELDS.every(field =>
        Array.isArray(row[field]) && row[field].length === 3 && row[field].every(Number.isFinite)))) {
    throw new Error('Replay IMU contract mismatch');
  }
  return value;
}

export function phaseReplayView(replay, playback) {
  if (!replay || playback.state === 'idle') return { phase: null, points: [] };
  // Equal display slots only: animation timing is not a measured capture clock.
  const phase = playback.state === 'complete' ? 3 : Math.min(3, 1 + Math.floor(playback.progress * 3));
  return { phase, points: replay.phases.slice(0, phase) };
}

export function drawPhaseIMUChart(canvas, replay, view, field) {
  const width = Math.max(1, canvas.clientWidth), height = Math.max(1, canvas.clientHeight);
  const scale = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
  const context = canvas.getContext('2d');
  context.scale(scale, scale);
  if (!replay) return;
  const values = replay.phases.flatMap(row => row[field]);
  const min = Math.min(...values), max = Math.max(...values), range = Math.max(max - min, .1);
  const left = 38, right = width - 20, top = 48, bottom = Math.max(top + 1, height - 30);
  const x = phase => left + (phase - 1) / 2 * (right - left);
  const y = value => bottom - (value - min) / range * (bottom - top);
  context.font = '10px system-ui'; context.fillStyle = '#607482'; context.textAlign = 'right';
  context.fillText(max.toFixed(2), left - 6, top + 3);
  context.fillText(min.toFixed(2), left - 6, bottom + 3);
  context.textAlign = 'center';
  for (let phase = 1; phase <= 3; phase++) {
    context.fillStyle = view.phase === phase ? '#244f70' : '#71818a';
    context.fillText(`P${phase}`, x(phase), height - 10);
  }
  for (let axis = 0; axis < 3; axis++) {
    context.strokeStyle = COLORS[axis]; context.fillStyle = COLORS[axis]; context.lineWidth = 1.5;
    context.setLineDash([4, 4]); context.beginPath();
    for (const [index, point] of view.points.entries()) {
      if (index === 0) context.moveTo(x(point.phase), y(point[field][axis]));
      else context.lineTo(x(point.phase), y(point[field][axis]));
    }
    context.stroke(); context.setLineDash([]);
    for (const point of view.points) {
      context.beginPath(); context.arc(x(point.phase), y(point[field][axis]), 3, 0, Math.PI * 2); context.fill();
    }
  }
}
