import assert from 'node:assert/strict';
import test from 'node:test';

import { ResearchTelemetrySession } from '../../src/digital_spotter/web/static/research-telemetry.mjs';


function harness({ failClock = false } = {}) {
  const seen = { starts: [], poses: [], clocks: [], resets: [], stops: 0, timers: [], cancelled: [] };
  const controller = {
    async start(options) { seen.starts.push(options); },
    stop() { seen.stops += 1; },
    createClockSyncRequest(id) {
      return { schema_version: 1, message_type: 'clock_sync_request',
        request_id: id, client_sent_ms: 1_000 };
    },
    acceptClockSyncResponse(response) { seen.clocks.push(response); },
    acceptPoseSample(sample) { seen.poses.push(sample); },
    resetTelemetry(reason) { seen.resets.push(reason); },
  };
  const fetchFn = async (url, options) => {
    if (url === '/api/clock-sync') {
      if (failClock) throw new Error('transport failed');
      const request = JSON.parse(options.body);
      return { ok: true, async json() {
        return { ...request, message_type: 'clock_sync_response',
          server_received_monotonic_us: 6_010_000,
          server_sent_monotonic_us: 6_011_000 };
      } };
    }
    assert.equal(url, '/api/pose-events?after=0');
    return { ok: true, async json() {
      return { cursor: 1, events: [{ schema_version: 1, message_type: 'pose_sample',
        frame_sequence: 7 }] };
    } };
  };
  const session = new ResearchTelemetrySession({
    controller, fetchFn,
    setIntervalFn: (callback, ms) => { seen.timers.push({ callback, ms }); return ms; },
    clearIntervalFn: (id) => seen.cancelled.push(id),
  });
  return { session, seen };
}


test('research viewer uses same-origin pose and clock endpoints, then stops cleanly', async () => {
  const { session, seen } = harness();
  await session.start('http://127.0.0.1:8889/picamera2/whep');
  assert.deepEqual(seen.starts, [{ whepUrl: 'http://127.0.0.1:8889/picamera2/whep' }]);
  assert.equal(seen.clocks.length, 1);
  assert.equal(seen.poses.length, 1);
  assert.deepEqual(seen.timers.map(({ ms }) => ms), [50, 2_000]);
  session.stop();
  assert.equal(seen.stops, 1);
  assert.deepEqual(seen.cancelled, [50, 2_000]);
});


test('clock transport failure invalidates telemetry without reporting a match', async () => {
  const { session, seen } = harness({ failClock: true });
  await session.start('http://127.0.0.1:8889/picamera2/whep');
  assert.deepEqual(seen.resets, ['clock_sync_unavailable']);
  assert.equal(seen.clocks.length, 0);
  session.stop();
});


test('a bridge cursor reset clears old pose state and restarts polling', async () => {
  const { session, seen } = harness();
  await session.start('http://127.0.0.1:8889/picamera2/whep');
  assert.equal(session.cursor, 1);
  session.fetchFn = async (url) => {
    assert.equal(url, '/api/pose-events?after=1');
    return { ok: true, async json() { return { cursor: 0, events: [] }; } };
  };
  await session.pollOnce();
  assert.equal(session.cursor, 0);
  assert.deepEqual(seen.resets, ['pose_transport_unavailable']);
  session.stop();
});
