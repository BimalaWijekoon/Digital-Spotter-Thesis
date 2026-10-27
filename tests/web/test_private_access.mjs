import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isPrivateResearchOrigin,
  resolvePrivateWhepUrl,
} from '../../src/digital_spotter/web/static/ui-preview/private-access.mjs';

const cameraConfig = {
  loopback_whep_url: 'http://127.0.0.1:8889/picamera2/whep',
  tailscale_https_port: 8443,
  whep_path: '/picamera2/whep',
};

test('research UI accepts only the loopback bench or a Tailscale HTTPS origin', () => {
  assert.equal(isPrivateResearchOrigin(new URL('http://127.0.0.1:4174/ui-preview/')), true);
  assert.equal(isPrivateResearchOrigin(new URL(
    'https://pidigitalspotter.example-tailnet.ts.net/ui-preview/')),
  true);
  assert.equal(isPrivateResearchOrigin(new URL(
    'http://pidigitalspotter.example-tailnet.ts.net/ui-preview/')),
  false);
  assert.equal(isPrivateResearchOrigin(new URL('https://example.com/ui-preview/')), false);
});

test('camera endpoint follows the private page without storing a tailnet identity', () => {
  assert.equal(resolvePrivateWhepUrl(cameraConfig,
    new URL('http://127.0.0.1:4174/ui-preview/')),
  'http://127.0.0.1:8889/picamera2/whep');
  assert.equal(resolvePrivateWhepUrl(cameraConfig,
    new URL('https://pidigitalspotter.example-tailnet.ts.net/ui-preview/')),
  'https://pidigitalspotter.example-tailnet.ts.net:8443/picamera2/whep');
  assert.throws(() => resolvePrivateWhepUrl(cameraConfig,
    new URL('https://example.com/ui-preview/')), /private research origin/);
});
