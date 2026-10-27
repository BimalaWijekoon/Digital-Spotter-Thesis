import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

const ui = new URL('../../src/digital_spotter/web/static/ui-preview/', import.meta.url);

test('research UI connects the camera from its panel without a typed URL', async () => {
  const html = await readFile(new URL('index.html', ui), 'utf8');
  const script = await readFile(new URL('camera-preview.mjs', ui), 'utf8');
  const styles = await readFile(new URL('styles.css', ui), 'utf8');
  const config = JSON.parse(await readFile(new URL('camera-config.json', ui), 'utf8'));

  assert.match(html, /id="camera-preview-start"[^>]*type="button"/);
  assert.match(html, /id="person-pose-test-start"[^>]*type="button"/);
  assert.match(html, /id="person-pose-test-overlay"/);
  assert.doesNotMatch(html, /id="camera-whep-url"/);
  assert.match(script, /camera-config\.json/);
  assert.match(script, /\/api\/research\/person-pose-test/);
  assert.doesNotMatch(script, /fetch\(`\$\{poseTestEndpoint\}\/latest`/,
    'idle UI must not request a saved result that does not exist');
  assert.equal(new URL(config.loopback_whep_url).hostname, '127.0.0.1');
  assert.equal(new URL(config.loopback_whep_url).pathname, '/picamera2/whep');
  assert.equal(config.tailscale_https_port, 8443);
  assert.equal(config.whep_path, '/picamera2/whep');
  assert.match(styles, /\.camera-stage video\s*\{[^}]*object-fit:\s*cover/);
  assert.equal(
    /\.camera-stage video\s*\{[^}]*transform:\s*scaleX\(-1\)/.test(styles),
    true,
    'live camera video should be mirrored horizontally',
  );
});

test('research relay requests camera only while a viewer needs it', async () => {
  const relay = await readFile(new URL('../../deploy/mediamtx.research-on-demand.yml', import.meta.url), 'utf8');
  assert.match(relay, /rtspAddress: 127\.0\.0\.1:8554/);
  assert.match(relay, /webrtcAddress: 127\.0\.0\.1:8889/);
  assert.match(relay, /webrtcLocalTCPAddress: 127\.0\.0\.1:8189/);
  assert.match(relay, /runOnDemand: \.\/research_camera_publisher\.sh/);
  assert.match(relay, /runOnDemandCloseAfter: 5s/);
});

test('pose test timer stays in a corner instead of covering the live camera', async () => {
  const styles = await readFile(new URL('styles.css', ui), 'utf8');
  const badge = styles.match(/\.person-pose-test-overlay\s*\{([^}]*)\}/)?.[1];
  assert.ok(badge, 'pose test timer style must exist');
  assert.doesNotMatch(badge, /inset:\s*0(?:\s|;|$)/,
    'countdown and capture must not cover the camera');
  assert.match(badge, /bottom:\s*\d+px/);
  assert.match(badge, /left:\s*\d+px/);
  assert.match(badge, /pointer-events:\s*none/);
});
