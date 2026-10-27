import { createResearchPreview } from '../research-preview.mjs?v=20261026-tailnet-camera';
import { formatPoseTestResult } from './pose-test-result.mjs';
import { mountPoseGuide } from './pose-guide.mjs';
import { isPrivateResearchOrigin, resolvePrivateWhepUrl } from './private-access.mjs';

const start = document.querySelector('#camera-preview-start');
const stop = document.querySelector('#camera-preview-stop');
const status = document.querySelector('#camera-preview-status');
const readiness = document.querySelector('#camera-readiness');
const devicesStatus = document.querySelector('#devices-camera-status');
const videoStatus = document.querySelector('#devices-video-status');
const stage = document.querySelector('.camera-stage');
const placeholder = document.querySelector('#camera-preview-placeholder');
const video = document.querySelector('#camera-preview-video');
const poseTestStart = document.querySelector('#person-pose-test-start');
const poseTestStatus = document.querySelector('#person-pose-test-status');
const poseTestOverlay = document.querySelector('#person-pose-test-overlay');
const poseTestSeconds = document.querySelector('#person-pose-test-seconds');
const poseTestPhase = document.querySelector('#person-pose-test-phase');
const poseTestResult = document.querySelector('#person-pose-test-result');
const poseTestEndpoint = '/api/research/person-pose-test';

const privatePage = isPrivateResearchOrigin(location);
const readerAvailable = typeof window.MediaMTXWebRTCReader === 'function';

async function loadCameraEndpoint() {
  const response = await fetch('./camera-config.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('Camera configuration unavailable');
  return resolvePrivateWhepUrl(await response.json(), location);
}

if (!privatePage || !readerAvailable) {
  status.textContent = 'Camera unavailable';
} else {
  mountPoseGuide({ video, canvas: document.querySelector('#pose-guide-canvas'),
    status: document.querySelector('#pose-guide-status') });
  let poseTestActive = false;
  let usesLiveCamera = false;
  let poseTestPoll = null;
  const showState = (state) => {
    const live = state === 'playing';
    const active = ['connecting', 'playing', 'degraded'].includes(state);
    stage.dataset.cameraState = state;
    video.hidden = !live;
    placeholder.hidden = live;
    start.disabled = active || poseTestActive;
    stop.disabled = !active;
    status.textContent = {
      idle: 'Not connected',
      connecting: 'Connecting',
      playing: 'Camera live',
      degraded: 'Camera unavailable',
      stopped: 'Stopped',
    }[state] ?? 'Camera unavailable';
    const cameraState = live ? 'Camera live' : state === 'connecting' ? 'Connecting'
      : state === 'degraded' ? 'Unavailable' : state === 'stopped' ? 'Camera stopped' : 'Not checked';
    readiness.textContent = cameraState;
    devicesStatus.textContent = cameraState;
    videoStatus.textContent = cameraState;
    if (live && document.querySelector('#workout-tab').getAttribute('aria-selected') !== 'true') {
      document.querySelector('#workout-tab').click();
    }
  };

  const preview = createResearchPreview({
    videoElement: video,
    Reader: window.MediaMTXWebRTCReader,
    onState: ({ state }) => showState(state),
    maxDurationMs: null,
    allowEndpoint: isPrivateResearchOrigin,
  });

  const showPoseTest = (state) => {
    usesLiveCamera = state.uses_live_camera === true;
    const phase = state.phase;
    poseTestActive = phase === 'countdown' || phase === 'running';
    poseTestStart.disabled = poseTestActive;
    start.disabled = poseTestActive || ['connecting', 'playing', 'degraded'].includes(preview.state);
    poseTestOverlay.hidden = !poseTestActive;
    poseTestResult.hidden = phase !== 'complete';
    if (phase === 'countdown' || phase === 'running') {
      poseTestSeconds.textContent = String(state.remaining_s ?? '—');
      poseTestPhase.textContent = phase === 'countdown' ? 'Move into frame' : 'Checking real pose';
      poseTestStatus.textContent = phase === 'countdown'
        ? `Starting in ${state.remaining_s}s`
        : `Testing · ${state.remaining_s}s left`;
    } else if (phase === 'complete') {
      const result = state.result ?? {};
      poseTestStatus.textContent = formatPoseTestResult(result);
    } else if (phase === 'failed') {
      poseTestStatus.textContent = `Test failed · ${state.error ?? 'camera unavailable'}`;
    } else {
      poseTestStatus.textContent = 'Ready';
    }
  };

  const updatePoseTest = async () => {
    const response = await fetch(poseTestEndpoint, { cache: 'no-store' });
    if (!response.ok) throw new Error('Pose test service unavailable');
    const state = await response.json();
    showPoseTest(state);
    if (!poseTestActive && poseTestPoll !== null) {
      clearInterval(poseTestPoll);
      poseTestPoll = null;
    }
    return state;
  };

  const startPoseTestPoll = () => {
    if (poseTestPoll !== null) clearInterval(poseTestPoll);
    poseTestPoll = setInterval(() => {
      updatePoseTest().catch(() => { poseTestStatus.textContent = 'Test status unavailable'; });
    }, 1000);
  };

  updatePoseTest().then((state) => {
    if (state.phase === 'countdown' || state.phase === 'running') {
      if (!usesLiveCamera) preview.stop();
      startPoseTestPoll();
    }
  }).catch(() => {
    poseTestStart.disabled = true;
    poseTestStatus.textContent = 'Pose test unavailable';
  });

  poseTestStart.addEventListener('click', async () => {
    poseTestActive = true;
    if (!usesLiveCamera) preview.stop();
    else if (preview.state !== 'playing') {
      try {
        await preview.start(await loadCameraEndpoint());
      } catch {
        poseTestActive = false;
        poseTestStatus.textContent = 'Connect camera first';
        poseTestStart.disabled = false;
        return;
      }
    }
    start.disabled = true;
    poseTestStart.disabled = true;
    poseTestStatus.textContent = 'Starting test';
    try {
      const response = await fetch(poseTestEndpoint, {
        method: 'POST',
        headers: { 'X-DS-Person-Test': '1' },
        credentials: 'omit',
        cache: 'no-store',
      });
      if (!response.ok) throw new Error(`Pose test start failed: ${response.status}`);
      showPoseTest(await response.json());
      startPoseTestPoll();
    } catch {
      poseTestActive = false;
      poseTestStatus.textContent = 'Could not start pose test';
      await updatePoseTest().catch(() => { poseTestStart.disabled = true; });
    }
  });

  showState('idle');
  start.addEventListener('click', async () => {
    if (poseTestActive) return;
    start.disabled = true;
    status.textContent = 'Connecting';
    try {
      await preview.start(await loadCameraEndpoint());
    } catch {
      preview.stop();
      status.textContent = 'Local camera unavailable';
      readiness.textContent = 'Unavailable';
      devicesStatus.textContent = 'Unavailable';
      videoStatus.textContent = 'Unavailable';
    }
  });
  stop.addEventListener('click', () => preview.stop());
  window.addEventListener('ds-preview-page-change', (event) => {
    if (event.detail !== 'workout' && preview.state !== 'idle') preview.stop();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && preview.state !== 'idle') preview.stop();
  });
  window.addEventListener('pagehide', () => preview.stop());
}
