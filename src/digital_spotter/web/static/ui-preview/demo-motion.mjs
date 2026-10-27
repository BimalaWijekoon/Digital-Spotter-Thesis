/** Illustrative 3D motion only: not measured pose, IMU data or model output. */
export function sampleDemoPose(exercise, form, progress) {
  if (!['squat', 'deadlift'].includes(exercise) || !['correct', 'incorrect'].includes(form)
      || !Number.isFinite(progress)) throw new TypeError('invalid animation scenario');
  const phase = Math.min(1, Math.max(0, progress));
  const wave = (1 - Math.cos(phase * Math.PI * 2)) / 2;
  const depth = exercise === 'squat' ? wave : 1 - wave;
  const incorrect = form === 'incorrect';
  const hipY = 1.03 - depth * (exercise === 'squat' ? .50 : .36);
  const hipZ = -depth * (exercise === 'squat' ? .28 : .36);
  const pitch = .06 + depth * (exercise === 'squat' ? .46 : 1.20)
    + (incorrect ? .30 * depth : 0);
  const shift = incorrect ? .06 * depth : 0;
  const shoulderY = hipY + .55 * Math.cos(pitch);
  const shoulderZ = hipZ + .55 * Math.sin(pitch);
  const result = {
    hipL: [-.16 + shift, hipY, hipZ], hipR: [.16 + shift, hipY, hipZ],
    shoulderL: [-.23 + shift, shoulderY, shoulderZ],
    shoulderR: [.23 + shift, shoulderY, shoulderZ],
    head: [shift, shoulderY + .19 * Math.cos(pitch), shoulderZ + .19 * Math.sin(pitch)],
    bar: [0, exercise === 'squat' ? shoulderY + .015 : .23 + .76 * (1 - depth),
      exercise === 'squat' ? shoulderZ - .10 : .28 + (incorrect ? .08 * depth : 0)],
  };
  for (const [side, sign] of [['L', -1], ['R', 1]]) {
    const ankle = [sign * .18, .10, 0];
    const hip = result[`hip${side}`];
    const dy = hip[1] - ankle[1], dz = hip[2] - ankle[2];
    const distance = Math.hypot(dy, dz);
    const along = (.46 ** 2 - .48 ** 2 + distance ** 2) / (2 * distance);
    const bend = Math.sqrt(Math.max(0, .46 ** 2 - along ** 2));
    result[`ankle${side}`] = ankle;
    result[`knee${side}`] = [sign * (.17 - (incorrect && exercise === 'squat' ? .08 * depth : 0)),
      ankle[1] + dy / distance * along - dz / distance * bend,
      ankle[2] + dz / distance * along + dy / distance * bend];
    const shoulder = result[`shoulder${side}`];
    const hand = [sign * (exercise === 'squat' ? .46 : .29), result.bar[1], result.bar[2]];
    result[`hand${side}`] = hand;
    result[`elbow${side}`] = exercise === 'squat'
      ? [sign * .38 + shift, shoulderY - .20, shoulderZ + .03]
      : [(shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2 - .02,
        (shoulder[2] + hand[2]) / 2 + .04];
  }
  return result;
}

export class DemoPlayback {
  constructor() { this.reset(); }
  reset() { this.state = 'idle'; this.elapsedMs = 0; this.lastNow = null; }
  start(now) {
    if (!Number.isFinite(now)) throw new TypeError('invalid animation clock');
    if (this.state !== 'paused') this.elapsedMs = 0;
    this.lastNow = now;
    this.state = 'running';
  }
  pause(now) {
    if (this.state !== 'running') return;
    this.tick(now);
    if (this.state === 'running') this.state = 'paused';
    this.lastNow = null;
  }
  tick(now) {
    if (this.state === 'running') {
      this.elapsedMs = Math.min(18000, this.elapsedMs + Math.max(0, now - this.lastNow));
      this.lastNow = now;
      if (this.elapsedMs >= 18000) this.state = 'complete';
    }
    return this.snapshot();
  }
  snapshot() {
    return { state: this.state, elapsedMs: this.elapsedMs,
      completedReps: Math.floor(this.elapsedMs / 6000),
      progress: this.state === 'complete' ? 1 : (this.elapsedMs % 6000) / 6000 };
  }
}
