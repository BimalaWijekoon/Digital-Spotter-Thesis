import assert from 'node:assert/strict';
import test from 'node:test';

import { ResearchSessionStatus } from '../../src/digital_spotter/web/static/ui-preview/research-session-status.mjs';

test('polls same-origin status and keeps analysis unavailable', async () => {
  const seen = [];
  const client = new ResearchSessionStatus({
    fetchFn: async (url) => {
      assert.equal(url, '/api/research/session-status');
      return { ok: true, json: async () => ({
        version: 'research_status_v1',
        session: { state: 'active', rep_count: 2 },
        wearable: { state: 'degraded' },
        camera: { state: 'receiving' },
        analysis: { state: 'unavailable', reason: 'v5_live_feature_contract_unverified' },
        latest_rep: { number: 2, quality: 'unavailable' },
      }) };
    },
    onStatus: (status) => seen.push(status),
  });

  await client.pollOnce();
  assert.equal(seen[0].session.rep_count, 2);
  assert.equal(seen[0].analysis.state, 'unavailable');
});

test('failed or dishonest response clears displayed live status', async () => {
  const seen = [];
  const client = new ResearchSessionStatus({
    fetchFn: async () => ({ ok: true, json: async () => ({
      version: 'research_status_v1',
      session: { state: 'active', rep_count: 1 },
      wearable: { state: 'receiving' },
      camera: { state: 'receiving' },
      analysis: { state: 'ready', probability: 0.9 },
      latest_rep: null,
    }) }),
    onStatus: (status) => seen.push(status),
  });

  await client.pollOnce();
  assert.equal(seen[0], null);
});

test('a plain static preview without the API stops polling after 404', async () => {
  let calls = 0;
  const seen = [];
  const client = new ResearchSessionStatus({
    fetchFn: async () => { calls += 1; return { ok: false, status: 404 }; },
    onStatus: (status) => seen.push(status),
  });
  await client.pollOnce();
  await client.pollOnce();
  assert.equal(calls, 1);
  assert.deepEqual(seen, [null]);
});
