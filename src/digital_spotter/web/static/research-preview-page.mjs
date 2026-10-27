import { createResearchPreview } from './research-preview.mjs';
import { LiveVideoController } from './live-video-controller.mjs';
import { PoseCanvasOverlay } from './pose-overlay.mjs';
import { ResearchTelemetrySession } from './research-telemetry.mjs';

const status = document.querySelector('#status');
const form = document.querySelector('#preview-form');
const start = document.querySelector('#start');
const stop = document.querySelector('#stop');
const endpoint = document.querySelector('#whep-url');
const poseStatus = document.querySelector('#pose-status');
const video = document.querySelector('video');
let session;
const preview = createResearchPreview({
  videoElement: video,
  Reader: window.MediaMTXWebRTCReader,
  onDeadline: () => session.stop(),
  onState: ({ state, reason }) => {
    status.dataset.state = state;
    status.textContent = reason ? `${state}: ${reason}` : state;
    start.disabled = !['idle', 'stopped'].includes(state);
    stop.disabled = ['idle', 'stopped'].includes(state);
  },
});
const overlay = new PoseCanvasOverlay({
  videoElement: video,
  canvasElement: document.querySelector('#pose-canvas'),
  onState: ({ state, reason, deltaUs }) => {
    poseStatus.dataset.state = state;
    poseStatus.textContent = state === 'rendered'
      ? `Pose matched (${Math.round(deltaUs / 1_000)} ms capture difference)`
      : `Pose unavailable: ${reason}`;
  },
});
const controller = new LiveVideoController({
  videoElement: video,
  player: {
    start: ({ whepUrl }) => preview.start(whepUrl),
    stop: () => preview.stop(),
  },
  overlay,
});
session = new ResearchTelemetrySession({ controller });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await session.start(endpoint.value);
  } catch {
    session.stop();
    preview.stop();
    status.textContent = 'Preview could not start. Check the local endpoint and relay.';
    status.dataset.state = 'degraded';
  }
});
stop.addEventListener('click', () => session.stop());
window.addEventListener('pagehide', () => session.stop());
