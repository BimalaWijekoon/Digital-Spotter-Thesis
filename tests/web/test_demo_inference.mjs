import assert from 'node:assert/strict';
import test from 'node:test';
import { DemoInferenceClient, describeDemoDecision } from '../../src/digital_spotter/web/static/ui-preview/demo-inference.mjs';

const result = { source: 'synthetic_training_replay', live: false, reference_only: true,
  animation_drives_features: false, actuators_enabled: false,
  feedback: { enabled: false, cue: 'good', dispatched: false, warnings: [] },
  exercise: 'squat', form: 'incorrect', rep_id: 1, fixture_index: 1, load_kg: 45,
  raw_probability: .1, calibrated_probability: .2, threshold: .4,
  predicted_class: 0, model_version: 'digital_spotter_v5_imu_synthetic_r1' };

test('bad-squat false negative is explained without changing the model decision', () => {
  const description = describeDemoDecision({ ...result, source_label: 1,
    calibrated_probability: .39154328994402116, threshold: .3976007923801824,
    matches_source_label: false });
  assert.equal(description.result, 'Good form');
  assert.match(description.detail, /Label: incorrect/);
  assert.match(description.detail, /39\.15% < 39\.76%/);
});

test('demo sends scenario not prediction and keeps actual disagreeing model result', async () => {
  const calls = [];
  const client = new DemoInferenceClient(async (url, options) => {
    calls.push([url, options]);
    return { ok: true, json: async () => result };
  });
  const actual = await client.predict({ exercise: 'squat', form: 'incorrect' }, 1);
  assert.equal(actual.predicted_class, 0);
  assert.equal(calls[0][0], '/api/research/demo/predict');
  assert.equal(calls[0][1].headers['X-DS-Demo'], '1');
  assert.deepEqual(JSON.parse(calls[0][1].body), { exercise: 'squat', form: 'incorrect', rep_id: 1 });
});

test('reset invalidates an in-flight result without creating another model request', async () => {
  let finish, count = 0;
  const client = new DemoInferenceClient(() => {
    count++;
    return new Promise(resolve => { finish = resolve; });
  });
  const pending = client.predict({ exercise: 'squat', form: 'incorrect' }, 1);
  assert.equal(await client.predict({ exercise: 'squat', form: 'incorrect' }, 2), null);
  client.reset();
  finish({ ok: true, json: async () => result });
  assert.equal(await pending, null);
  assert.equal(count, 1);
});

test('demo start requests feedback without choosing a model result', async () => {
  const calls = [];
  const client = new DemoInferenceClient(async (url, options) => {
    calls.push([url, options]);
    return { ok: true, json: async () => ({ enabled: true, cue: 'start',
      dispatched: true, warnings: [] }) };
  });

  const result = await client.startFeedback();

  assert.equal(result.cue, 'start');
  assert.equal(calls[0][0], '/api/research/demo/start');
  assert.equal(calls[0][1].headers['X-DS-Demo'], '1');
  assert.equal(calls[0][1].body, undefined);
});
