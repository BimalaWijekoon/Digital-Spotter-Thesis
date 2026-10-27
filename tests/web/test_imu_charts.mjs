import assert from 'node:assert/strict';
import test from 'node:test';

import { IMUWindowClient, parseIMUWindow } from '../../src/digital_spotter/web/static/ui-preview/imu-charts.mjs';

const sample = {
  sequence: 1, t_ms: 0,
  acceleration_m_s2: [1, 2, 3], angular_velocity_rad_s: [0.1, 0.2, 0.3],
};

test('accepts a bounded real IMU window and rejects invalid vectors', async () => {
  const window = { version: 'research_imu_window_v1', state: 'degraded', samples: [sample] };
  assert.deepEqual(parseIMUWindow(window), window);
  assert.equal(parseIMUWindow({ ...window, samples: [{ ...sample, acceleration_m_s2: [1, NaN, 3] }] }), null);
  const seen = [];
  const client = new IMUWindowClient({
    fetchFn: async (url) => {
      assert.equal(url, '/api/research/imu-window');
      return { ok: true, json: async () => window };
    },
    onWindow: (value) => seen.push(value),
  });
  await client.pollOnce();
  assert.equal(seen[0].samples[0].sequence, 1);
});
