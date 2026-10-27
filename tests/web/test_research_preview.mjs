import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createResearchPreview } from '../../src/digital_spotter/web/static/research-preview.mjs';
import { isPrivateResearchOrigin } from '../../src/digital_spotter/web/static/ui-preview/private-access.mjs';

test('official reader and license match the frozen release bytes', async () => {
  const base = new URL('../../src/digital_spotter/web/static/vendor/mediamtx-v1.12.3/', import.meta.url);
  for (const [file, hash] of [
    ['reader.js', '1d899415b8065a5cb2602cdeb968dd07497d2a3f009e904809435202f8c44bce'],
    ['LICENSE', 'ecae73b0a23185a35a1222edc0aae5245bb9739420bad0125b0c42e935301a80'],
  ]) {
    assert.equal(createHash('sha256').update(await readFile(new URL(file, base))).digest('hex'), hash);
  }
});

function fixture() {
  let options, deadline, closeCount = 0, cleared = 0;
  const video = { srcObject: null, async play() {}, pause() {} };
  const states = [];
  const preview = createResearchPreview({
    videoElement: video,
    Reader: class { constructor(value) { options = value; } close() { closeCount++; } },
    onState: value => states.push(value),
    setTimer: (callback, delay) => { deadline = { callback, delay }; return 1; },
    clearTimer: () => { cleared++; },
  });
  return { preview, video, states, get options() { return options; },
    get deadline() { return deadline; }, get closeCount() { return closeCount; },
    get cleared() { return cleared; } };
}

test('research preview uses the canonical player and bounds its lifetime', async () => {
  const f = fixture();
  await f.preview.start('http://127.0.0.1:8889/picamera2/whep');
  assert.equal(f.options.url, 'http://127.0.0.1:8889/picamera2/whep');
  assert.equal(f.deadline.delay, 120000);
  const stream = {};
  f.options.onTrack({ streams: [stream] });
  await Promise.resolve();
  assert.equal(f.video.srcObject, stream);
  assert.equal(f.preview.state, 'playing');
  f.deadline.callback();
  assert.equal(f.closeCount, 1);
  assert.equal(f.video.srcObject, null);
  assert.equal(f.preview.state, 'stopped');
});

test('research preview refuses non-loopback and credential-bearing URLs', async () => {
  for (const url of ['http://192.0.2.1:8889/x/whep', 'https://example.org/x/whep',
    'http://secret@127.0.0.1:8889/x/whep', 'http://127.0.0.1:8889/x/whep?token=secret']) {
    const f = fixture();
    await assert.rejects(f.preview.start(url));
    assert.equal(f.options, undefined);
  }
});

test('research UI can explicitly allow its private Tailscale WHEP endpoint', async () => {
  let options;
  const preview = createResearchPreview({
    videoElement: { srcObject: null, async play() {}, pause() {} },
    Reader: class { constructor(value) { options = value; } close() {} },
    maxDurationMs: null,
    allowEndpoint: isPrivateResearchOrigin,
  });

  await preview.start('https://pidigitalspotter.example-tailnet.ts.net:8443/picamera2/whep');
  assert.equal(
    options.url,
    'https://pidigitalspotter.example-tailnet.ts.net:8443/picamera2/whep',
  );
  preview.stop();
});

test('manual stop clears the deadline and does not expose reader errors', async () => {
  const f = fixture();
  await f.preview.start('http://127.0.0.1:8889/picamera2/whep');
  f.options.onError('private upstream detail');
  assert.equal(f.states.at(-1).reason, 'whep_reader_error');
  f.preview.stop();
  assert.equal(f.cleared, 1);
  assert.equal(f.closeCount, 1);
  assert.equal(f.preview.state, 'stopped');
});

test('explicit UI lifetime stays open until the viewer stops it', async () => {
  let scheduled = false;
  const preview = createResearchPreview({
    videoElement: { srcObject: null, async play() {}, pause() {} },
    Reader: class { close() {} },
    maxDurationMs: null,
    setTimer: () => { scheduled = true; return 1; },
  });
  await preview.start('http://127.0.0.1:8889/picamera2/whep');
  assert.equal(scheduled, false);
  preview.stop();
  assert.equal(preview.state, 'stopped');
});
