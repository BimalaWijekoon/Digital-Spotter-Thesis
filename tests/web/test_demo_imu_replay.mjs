import assert from 'node:assert/strict';
import test from 'node:test';
import { parseReplayIMU, phaseReplayView } from '../../src/digital_spotter/web/static/ui-preview/demo-imu-replay.mjs';
import { DemoPlayback } from '../../src/digital_spotter/web/static/ui-preview/demo-motion.mjs';

const replay = {
  version: 'demo_phase_imu_v1', source: 'synthetic_training_replay',
  representation: 'phase_medians', measured_timestamps: false,
  units: { acceleration_m_s2: 'm/s^2', angular_velocity_rad_s: 'rad/s' },
  phases: [1, 2, 3].map(phase => ({ phase,
    acceleration_m_s2: [phase * .25, -.1, 9.8], angular_velocity_rad_s: [.2, phase * .1, 0] })),
};

test('replay retains exact phase values and rejects wrong order, units or fake timing', () => {
  assert.deepEqual(parseReplayIMU(replay), replay);
  for (const invalid of [
    { ...replay, phases: [...replay.phases].reverse() },
    { ...replay, measured_timestamps: true },
    { ...replay, units: { ...replay.units, angular_velocity_rad_s: 'deg/s' } },
    { ...replay, phases: replay.phases.map(row => ({ ...row, acceleration_m_s2: [NaN, 0, 1] })) },
  ]) assert.throws(() => parseReplayIMU(invalid), /Replay IMU contract mismatch/);
});

test('three original points follow playback, pause, completion and reset without interpolation', () => {
  const player = new DemoPlayback();
  assert.deepEqual(phaseReplayView(replay, player.snapshot()).points, []);
  player.start(0);
  assert.equal(phaseReplayView(replay, player.snapshot()).phase, 1);
  let view = phaseReplayView(replay, player.tick(2100));
  assert.equal(view.phase, 2);
  assert.deepEqual(view.points, replay.phases.slice(0, 2));
  player.pause(2100);
  assert.deepEqual(phaseReplayView(replay, player.tick(15000)), view);
  player.start(15000);
  view = phaseReplayView(replay, player.tick(31000));
  assert.equal(view.phase, 3);
  assert.deepEqual(view.points, replay.phases);
  player.reset();
  assert.deepEqual(phaseReplayView(replay, player.snapshot()).points, []);
});
