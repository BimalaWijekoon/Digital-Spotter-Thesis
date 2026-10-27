import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import {
  WorkoutClient,
  completedSetDownload,
  setControlState,
} from '../../src/digital_spotter/web/static/ui-preview/workout-client.mjs';

test('workout commands use real same-origin API and explicit selected context', async () => {
  let request;
  let rendered;
  const state = { version: 'workout_v1', network: { state: 'connected', interface: 'wlan0', has_local_address: true }, session: { state: 'active', rep_count: 0, elapsed_s: 0 } };
  const client = new WorkoutClient({ fetchFn: async (url, options) => {
    request = { url, options };
    return { ok: true, json: async () => state };
  }, onStatus: value => { rendered = value; } });
  await client.command('start', { exercise_id: 1, load_kg: 35 });
  assert.equal(request.options.headers['X-DS-Workout'], '1');
  assert.deepEqual(JSON.parse(request.options.body), { action: 'start', data: { exercise_id: 1, load_kg: 35 } });
  assert.equal(rendered, state);
});

test('unreachable workout service never fabricates an active session', async () => {
  let state = 'not set';
  const client = new WorkoutClient({ fetchFn: async () => { throw Error('offline'); }, onStatus: value => { state = value; } });
  assert.equal(await client.poll(), null);
  assert.equal(state, null);
  assert.equal(client.available, false);
});

test('invalid or missing network state fails the status contract closed', async () => {
  const state = { version: 'workout_v1', session: { state: 'idle', rep_count: 0, elapsed_s: 0 } };
  let rendered = 'not set';
  const client = new WorkoutClient({ fetchFn: async () => ({ ok: true, json: async () => state }), onStatus: value => { rendered = value; } });

  assert.equal(await client.poll(), null);
  assert.equal(rendered, null);
});

test('an active set exposes a primary finish action instead of disabling it', () => {
  assert.deepEqual(setControlState({
    sessionState: 'active', commandPending: false, serviceAvailable: true,
    validContext: true, hasCompletedSet: false,
  }), {
    busy: true, primaryAction: 'stop', primaryLabel: 'Finish + JSON',
    primaryDisabled: false, pauseDisabled: false, stopDisabled: false,
    pauseLabel: 'Pause', downloadVisible: false,
  });
});

test('completed set JSON uses a stable research filename and formatted body', () => {
  const completed = {
    schema_version: 1, kind: 'digital_spotter_research_set',
    session_id: 'a123', status: 'complete', hardware_simulated: false,
  };
  assert.deepEqual(completedSetDownload(completed), {
    filename: 'digital-spotter-set-a123.json',
    text: `${JSON.stringify(completed, null, 2)}\n`,
  });
  assert.equal(completedSetDownload(null), null);
});

test('set panel contains the visible finish/download wiring', async () => {
  const root = new URL('../../src/digital_spotter/web/static/ui-preview/', import.meta.url);
  const [html, controller] = await Promise.all([
    readFile(new URL('index.html', root), 'utf8'),
    readFile(new URL('preview.js', root), 'utf8'),
  ]);
  assert.match(html, /id="download-set-json"[^>]*>Download JSON</);
  assert.match(controller, /async function finishSet\(\)/);
  assert.match(controller, /completed_set/);
});
