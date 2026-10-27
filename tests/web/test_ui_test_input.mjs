import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import { parseTestInputResult } from '../../src/digital_spotter/web/static/ui-preview/test-input-result.mjs';

const result = {
  version: 'v5_test_input_v1',
  source: 'frozen_fitted_medians',
  live: false,
  reference_only: true,
  model_version: 'digital_spotter_v5_scope_faithful',
  raw_probability: 0.03,
  calibrated_probability: 0.067,
  threshold: 0.205,
  predicted_class: 0,
};

test('test-input result accepts only an explicit non-live V5 calculation', () => {
  assert.deepEqual(parseTestInputResult(result), result);
  for (const change of [
    { live: true }, { reference_only: false }, { predicted_class: 1 },
    { model_version: 'old_model' }, { calibrated_probability: 1.5 },
  ]) {
    assert.equal(parseTestInputResult({ ...result, ...change }), null);
  }
});

test('Digital Spotter page keeps source disclosure local to the result', async () => {
  const html = await readFile(new URL('../../src/digital_spotter/web/static/ui-preview/index.html', import.meta.url), 'utf8');
  assert.match(html, /<title>Digital Spotter<\/title>/);
  assert.match(html, /data-page="demo">Demo<\/button>/);
  assert.match(html, /id="result-source"[^>]*>Test input<\/span>/);
  assert.doesNotMatch(html, />[^<]*(?:preview only|research preview)[^<]*</i);
  assert.doesNotMatch(html, /aria-label="[^"]*(?:preview only|research preview)/i);
  assert.doesNotMatch(html, /id="preview-notice-copy"/);
});
