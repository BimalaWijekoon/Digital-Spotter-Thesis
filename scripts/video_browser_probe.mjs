/** Bounded real-Chromium playback probe; saves numeric evidence only. Node >=22. */
import { spawn } from 'node:child_process';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const [chromium, url, whepUrl] = process.argv.slice(2);
const viewerUrl = new URL(url);
const privateViewer = (viewerUrl.protocol === 'http:' && viewerUrl.hostname === '127.0.0.1')
  || (viewerUrl.protocol === 'https:' && viewerUrl.hostname.endsWith('.ts.net'));
if (!chromium || !url || !privateViewer) {
  throw new Error('Usage: node video_browser_probe.mjs CHROMIUM PRIVATE_VIEWER_URL');
}
const profile = await mkdtemp(join(tmpdir(), 'ds-video-browser-'));
const browser = spawn(chromium, [
  '--headless', '--no-sandbox', '--disable-gpu', '--no-first-run',
  '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0',
  `--user-data-dir=${profile}`, 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });
let socket;
let sequence = 0;
const pending = new Map();
const timeout = setTimeout(() => browser.kill('SIGTERM'), 60000);
try {
  const endpoint = await new Promise((resolve, reject) => {
    let output = '';
    browser.stderr.on('data', (chunk) => {
      output = (output + chunk.toString()).slice(-8192);
      const match = output.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) resolve(match[1]);
    });
    browser.once('exit', () => reject(new Error('Browser exited before CDP became ready')));
  });
  const origin = new URL(endpoint);
  const page = await fetch(`http://${origin.host}/json/new?about:blank`, {
    method: 'PUT', signal: AbortSignal.timeout(5000),
  }).then((response) => response.json());
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });
  const browserDiagnostics = [];
  socket.addEventListener('message', ({ data }) => {
    const reply = JSON.parse(data);
    if (pending.has(reply.id)) {
      pending.get(reply.id)(reply);
      pending.delete(reply.id);
    } else if (reply.method === 'Runtime.exceptionThrown') {
      browserDiagnostics.push({ type: 'exception',
        text: reply.params?.exceptionDetails?.text ?? 'unknown exception',
        description: reply.params?.exceptionDetails?.exception?.description ?? null });
    } else if (reply.method === 'Log.entryAdded') {
      browserDiagnostics.push({ type: 'log', level: reply.params?.entry?.level,
        text: reply.params?.entry?.text });
    } else if (reply.method === 'Network.requestWillBeSent'
      && reply.params?.request?.url?.includes('/whep')) {
      browserDiagnostics.push({ type: 'http-request', method: reply.params.request.method,
        url: reply.params.request.url });
    } else if (reply.method === 'Network.responseReceived'
      && (reply.params?.response?.status >= 400 || reply.params?.response?.url?.includes('/whep'))) {
      browserDiagnostics.push({ type: 'http-response', status: reply.params.response.status,
        url: reply.params.response.url,
        location: reply.params.response.headers?.location ?? null });
    } else if (reply.method === 'Network.loadingFailed') {
      browserDiagnostics.push({ type: 'network', error: reply.params?.errorText,
        blocked: reply.params?.blockedReason ?? null });
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timed out')); }, 40000);
    pending.set(id, (reply) => {
      clearTimeout(timer);
      if (reply.error || reply.result?.exceptionDetails) reject(new Error(
        reply.error?.message ?? reply.result.exceptionDetails.text ?? 'Browser evaluation failed'));
      else resolve(reply.result);
    });
    socket.send(JSON.stringify({ id, method, params }));
  });
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Network.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: `(() => {
    const NativePeerConnection = window.RTCPeerConnection;
    window.__dsPeerConnections = [];
    window.__dsPeerLogs = [];
    window.RTCPeerConnection = class extends NativePeerConnection {
      constructor(...args) {
        super(...args);
        window.__dsPeerConnections.push(this);
        this.__dsLog = { connection: [], ice: [], candidates: [], remote_sdp: null };
        window.__dsPeerLogs.push(this.__dsLog);
        this.addEventListener('connectionstatechange', () => {
          this.__dsLog.connection.push(this.connectionState);
        });
        this.addEventListener('iceconnectionstatechange', () => {
          this.__dsLog.ice.push(this.iceConnectionState);
        });
        this.addEventListener('icecandidate', event => {
          if (event.candidate) this.__dsLog.candidates.push(event.candidate.candidate);
        });
      }
      setRemoteDescription(description) {
        this.__dsLog.remote_sdp = description?.sdp ?? null;
        return super.setRemoteDescription(description);
      }
    };
  })();` });
  const loaded = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Viewer page load timed out')), 10000);
    const onMessage = ({ data }) => {
      if (JSON.parse(data).method === 'Page.loadEventFired') {
        clearTimeout(timer);
        socket.removeEventListener('message', onMessage);
        resolve();
      }
    };
    socket.addEventListener('message', onMessage);
  });
  await send('Page.navigate', { url });
  await loaded;
  const evaluate = async (expression) => (await send('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true,
  })).result.value;
  const result = await evaluate(`(async () => {
    const endpoint = ${JSON.stringify(whepUrl ?? null)};
    if (endpoint) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const directCameraButton = document.querySelector('#camera-preview-start');
      if (directCameraButton) {
        directCameraButton.click();
      } else {
        const input = document.querySelector('#whep-url');
        const form = document.querySelector('#preview-form');
        if (!input || !form) return { passed: false, reason: 'viewer_page_unavailable' };
        input.value = endpoint;
        form.requestSubmit();
      }
    }
    const deadline = performance.now() + 30000;
    let video;
    while (performance.now() < deadline) {
      video = document.querySelector('video');
      if (video && video.videoWidth > 0 && video.currentTime > 0) break;
      await new Promise(r => setTimeout(r, 200));
    }
    if (!video || !video.videoWidth) {
      const peers = await Promise.all((window.__dsPeerConnections ?? []).map(async pc => ({
        connection_state: pc.connectionState,
        ice_connection_state: pc.iceConnectionState,
        ice_gathering_state: pc.iceGatheringState,
        signaling_state: pc.signalingState,
        candidates: [...(await pc.getStats()).values()]
          .filter(item => ['candidate-pair', 'local-candidate', 'remote-candidate'].includes(item.type))
          .map(item => ({ type: item.type, state: item.state ?? null,
            candidateType: item.candidateType ?? null, protocol: item.protocol ?? null,
            address: item.address ?? null, port: item.port ?? null }))
      })));
      return { passed: false, reason: 'no_decoded_video', peers,
        peer_logs: (window.__dsPeerLogs ?? []).slice(-3),
        camera_status: document.querySelector('#camera-preview-status')?.textContent ?? null,
        camera_start_disabled: document.querySelector('#camera-preview-start')?.disabled ?? null,
        reader_type: typeof window.MediaMTXWebRTCReader,
        scripts: [...document.scripts].map(script => script.src).filter(Boolean) };
    }
    const before = video.getVideoPlaybackQuality().totalVideoFrames;
    const timeBefore = video.currentTime;
    const capture = { callbacks: 0, finite: 0, ageMs: [] };
    let sampling = true;
    const observeFrame = (now, metadata) => {
      if (!sampling) return;
      capture.callbacks += 1;
      if (Number.isFinite(metadata?.captureTime)) {
        capture.finite += 1;
        capture.ageMs.push(now - metadata.captureTime);
      }
      video.requestVideoFrameCallback(observeFrame);
    };
    if (typeof video.requestVideoFrameCallback === 'function') {
      video.requestVideoFrameCallback(observeFrame);
    }
    await new Promise(r => setTimeout(r, 3000));
    sampling = false;
    const quality = video.getVideoPlaybackQuality();
    const result = { width: video.videoWidth, height: video.videoHeight,
      decoded_frames: quality.totalVideoFrames, frames_in_3s: quality.totalVideoFrames - before,
      dropped_frames: quality.droppedVideoFrames, media_time_advanced_s: video.currentTime - timeBefore,
      ready_state: video.readyState, hardware_simulated: false, user_agent: navigator.userAgent,
      capture_time_callbacks: capture.callbacks, finite_capture_times: capture.finite,
      mean_capture_to_callback_ms: capture.ageMs.length
        ? capture.ageMs.reduce((sum, value) => sum + value, 0) / capture.ageMs.length : null,
      pose_state: document.querySelector('#pose-status')?.dataset.state ?? null,
      pose_text: document.querySelector('#pose-status')?.textContent ?? null };
    result.peers = await Promise.all((window.__dsPeerConnections ?? []).slice(-3).map(async pc => ({
      connection_state: pc.connectionState,
      ice_connection_state: pc.iceConnectionState,
      ice_gathering_state: pc.iceGatheringState,
      signaling_state: pc.signalingState,
      candidates: [...(await pc.getStats()).values()]
        .filter(item => ['candidate-pair', 'local-candidate', 'remote-candidate'].includes(item.type))
        .map(item => ({ type: item.type, state: item.state ?? null,
          candidateType: item.candidateType ?? null, protocol: item.protocol ?? null,
          address: item.address ?? null, port: item.port ?? null }))
    })));
    result.peer_logs = (window.__dsPeerLogs ?? []).slice(-3);
    result.passed = result.frames_in_3s > 0 && result.media_time_advanced_s > 0;
    if (endpoint) {
      const uiPreview = Boolean(document.querySelector('#camera-preview-start'));
      result.viewer = uiPreview ? 'ui-preview' : 'research-preview';
      result.player_state = uiPreview
        ? document.querySelector('#camera-preview-status').textContent
        : document.querySelector('#status').dataset.state;
      document.querySelector(uiPreview ? '#camera-preview-stop' : '#stop').click();
      result.clean_stop = (uiPreview
        ? document.querySelector('#camera-preview-status').textContent === 'Stopped'
        : document.querySelector('#status').dataset.state === 'stopped')
        && video.srcObject === null;
      result.passed = result.passed
        && result.player_state === (uiPreview ? 'Camera live' : 'playing')
        && result.clean_stop;
    }
    return result;
  })()`);
  result.browser_diagnostics = browserDiagnostics;
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.passed ? 0 : 1;
} finally {
  clearTimeout(timeout);
  socket?.close();
  browser.kill('SIGTERM');
  await new Promise(resolve => {
    if (browser.exitCode !== null) return resolve();
    const timer = setTimeout(() => { browser.kill('SIGKILL'); resolve(); }, 5000);
    browser.once('exit', () => { clearTimeout(timer); resolve(); });
  });
}
