import { ResearchSessionStatus } from './research-session-status.mjs';
import { IMUWindowClient, drawIMUChart } from './imu-charts.mjs';
import { parseTestInputResult } from './test-input-result.mjs';
import { WorkoutClient, completedSetDownload, setControlState } from './workout-client.mjs';
import { mountDemoPage } from './demo-page.mjs?v=20261026-demo-pose-guide';

const pageTabs = [...document.querySelectorAll('.page-tabs [role="tab"]')];
const pageTitle = document.querySelector('#page-title');

const selectPage = (selected) => {
  for (const tab of pageTabs) {
    const active = tab === selected;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !active;
  }
  pageTitle.textContent = selected.textContent;
  history.replaceState(null, '', `#${selected.dataset.page}`);
  window.dispatchEvent(new CustomEvent('ds-preview-page-change', { detail: selected.dataset.page }));
};

for (const [index, tab] of pageTabs.entries()) {
  tab.addEventListener('click', () => selectPage(tab));
  tab.addEventListener('keydown', (event) => {
    let next;
    if (event.key === 'ArrowRight') next = pageTabs[(index + 1) % pageTabs.length];
    if (event.key === 'ArrowLeft') next = pageTabs[(index - 1 + pageTabs.length) % pageTabs.length];
    if (event.key === 'Home') next = pageTabs[0];
    if (event.key === 'End') next = pageTabs[pageTabs.length - 1];
    if (!next) return;
    event.preventDefault();
    selectPage(next);
    next.focus();
  });
}

const tabs = [...document.querySelectorAll('.mobile-view-tabs button[data-view]')];

for (const tab of tabs) {
  tab.addEventListener('click', () => {
    document.body.dataset.mobileView = tab.dataset.view;
    for (const item of tabs) {
      item.setAttribute('aria-pressed', String(item === tab));
    }
  });
}

const setupForm = document.querySelector('#set-setup');
let workoutStatus = null;
let commandPending = false;
let lastCompletedSet = null;
let workout;
function updateWorkoutControls() {
  if (!setupForm) return;
  const exercise = setupForm.querySelector('#exercise-select');
  const load = setupForm.querySelector('#load-kg');
  const state = workoutStatus?.session.state;
  const valid = ['0', '1'].includes(exercise.value) && load.value !== ''
    && load.validity.valid && Number.isFinite(Number(load.value));
  const view = setControlState({ sessionState: state, commandPending,
    serviceAvailable: Boolean(workoutStatus), validContext: valid,
    hasCompletedSet: Boolean(lastCompletedSet) });
  exercise.disabled = view.busy;
  load.disabled = view.busy;
  const primary = document.querySelector('#start-set');
  primary.disabled = view.primaryDisabled;
  primary.textContent = view.primaryLabel;
  primary.dataset.action = view.primaryAction;
  primary.setAttribute('aria-label', view.primaryAction === 'stop'
    ? 'Finish set and download JSON' : 'Start set');
  document.querySelector('#pause-set').disabled = view.pauseDisabled;
  document.querySelector('#stop-set').disabled = view.stopDisabled;
  document.querySelector('#pause-set').textContent = view.pauseLabel;
  document.querySelector('#download-set-json').hidden = !view.downloadVisible;
  document.querySelector('#setup-message').textContent = !workoutStatus ? 'Connect to the Pi'
    : state === 'paused' ? 'Paused' : state === 'active' ? 'Set running'
      : workoutStatus.session.saved ? 'Set saved' : valid ? 'Ready to start' : 'Choose exercise and load';
}
async function workoutCommand(action, data = {}) {
  if (commandPending) return;
  commandPending = true;
  updateWorkoutControls();
  try { return await workout.command(action, data); }
  catch (error) { document.querySelector('#setup-message').textContent = error.message; }
  finally { commandPending = false; updateWorkoutControls(); }
  return null;
}

function downloadSetJson(completedSet) {
  const download = completedSetDownload(completedSet);
  if (!download) return false;
  const url = URL.createObjectURL(new Blob([download.text], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = download.filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return true;
}

async function finishSet() {
  const result = await workoutCommand('stop');
  if (!result?.completed_set) return;
  lastCompletedSet = result.completed_set;
  downloadSetJson(lastCompletedSet);
  updateWorkoutControls();
  document.querySelector('#setup-message').textContent = 'Set saved · JSON downloaded';
}
if (setupForm) {
  const exercise = setupForm.querySelector('#exercise-select');
  const load = setupForm.querySelector('#load-kg');
  const message = setupForm.querySelector('#setup-message');

  const updateSetupMessage = () => {
    const validExercise = exercise.value === '0' || exercise.value === '1';
    const validLoad = load.value !== '' && load.validity.valid && Number.isFinite(Number(load.value));
    updateWorkoutControls();
  };

  exercise.addEventListener('change', updateSetupMessage);
  load.addEventListener('input', updateSetupMessage);
  setupForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (workoutStatus?.session.state === 'active' || workoutStatus?.session.state === 'paused') {
      await finishSet();
      return;
    }
    const result = await workoutCommand('start', {
      exercise_id: Number(exercise.value), load_kg: Number(load.value),
    });
    if (result?.session.state === 'active') lastCompletedSet = null;
  });
  updateSetupMessage();
}

const sensorLabel = {
  receiving: 'Receiving',
  degraded: 'Receiving · degraded',
  stale: 'Stale',
  unavailable: 'Unavailable',
};

const networkLabel = {
  connected: 'Connected',
  disconnected: 'Disconnected',
  unavailable: 'Unavailable',
};

function renderNetwork(network) {
  const state = network?.state ?? 'unavailable';
  const chip = document.querySelector('#network-chip');
  chip.dataset.state = state;
  document.querySelector('#network-chip-label').textContent = `Wi-Fi ${networkLabel[state]}`;
  document.querySelector('#devices-network-status').textContent = networkLabel[state];
}

function renderResearchStatus(status) {
  const active = status?.session.state === 'active';
  const wearable = active ? status.wearable.state : 'unavailable';
  const pose = active ? status.camera.state : 'unavailable';
  document.querySelector('#rep-count').textContent = active ? String(status.session.rep_count) : '—';
  document.querySelector('#wearable-readiness').textContent = sensorLabel[wearable];
  document.querySelector('#devices-wearable-status').textContent = sensorLabel[wearable];
  document.querySelector('#devices-imu-status').textContent = sensorLabel[wearable];
  document.querySelector('#imu-data-status').textContent = wearable === 'receiving' || wearable === 'degraded'
    ? 'Data arriving' : wearable === 'stale' ? 'Stale' : 'No data';
  document.querySelector('#devices-pose-status').textContent = sensorLabel[pose];
  document.querySelector('#pose-readiness').textContent = pose === 'receiving'
    ? 'Pose tracked' : pose === 'degraded' ? 'Pose degraded' : 'Pose —';
  document.querySelector('#analysis-readiness').textContent = 'Unavailable';
  document.querySelector('#devices-analysis-status').textContent = 'Unavailable';
  document.querySelector('#devices-model-status').textContent = 'Not ready';
  document.querySelector('#devices-sync-status').textContent = 'Not verified';
  document.querySelector('#result-label').textContent = active && status.latest_rep
    ? 'Not assessed' : 'Unavailable';
  document.querySelector('#analysis-detail').textContent = 'Live inputs unavailable';
  document.querySelector('#bad-form-probability').textContent = '—';
  document.querySelector('#model-version').textContent = '—';
}

const researchStatus = new ResearchSessionStatus({ onStatus: renderResearchStatus });
function renderWorkoutStatus(status) {
  window.dispatchEvent(new CustomEvent('ds-workout-status', { detail: status }));
  workoutStatus = status;
  if (status?.completed_set) lastCompletedSet = status.completed_set;
  updateWorkoutControls();
  if (!status) { renderNetwork(null); renderResearchStatus(null); return; }
  renderNetwork(status.network);
  // Reuse the existing sensor presentation, including truthful degraded states.
  renderResearchStatus({ ...status, session: { ...status.session, state: 'active' } });
  const elapsed = Math.floor(status.session.elapsed_s);
  document.querySelector('#set-timer').textContent = `${String(Math.floor(elapsed / 60)).padStart(2, '0')}:${String(elapsed % 60).padStart(2, '0')}`;
  document.querySelector('#devices-ble-status').textContent = ['receiving', 'degraded'].includes(status.wearable.state)
    ? 'Connected · data arriving' : status.wearable.state === 'stale' ? 'No recent data' : 'Unavailable';
  document.querySelector('#devices-model-status').textContent = status.model.loaded ? 'V5 loaded' : 'Not ready';
  document.querySelector('#devices-analysis-status').textContent = 'Inputs unverified';
  document.querySelector('#analysis-readiness').textContent = 'Inputs unverified';
  document.querySelector('#model-version').textContent = 'V5';
  document.querySelector('#analysis-detail').textContent = status.analysis.reason === 'phase_or_calibrated_imu_unavailable'
    ? 'Calibration / complete phases required' : 'Live input validation required';
}
workout = new WorkoutClient({ onStatus: renderWorkoutStatus });
workout.poll().then(state => { if (state) workout.start(); else researchStatus.start(); });
document.querySelector('#pause-set').addEventListener('click', () => workoutCommand(
  workoutStatus?.session.state === 'paused' ? 'resume' : 'pause'));
document.querySelector('#stop-set').addEventListener('click', finishSet);
document.querySelector('#download-set-json').addEventListener('click', () => {
  if (downloadSetJson(lastCompletedSet)) {
    document.querySelector('#setup-message').textContent = 'JSON downloaded';
  }
});
window.addEventListener('pagehide', () => researchStatus.stop());
window.addEventListener('pagehide', () => workout.stop());

const imuPlots = [
  [document.querySelector('#acceleration-chart'), 'acceleration_m_s2', 'Acceleration'],
  [document.querySelector('#gyroscope-chart'), 'angular_velocity_rad_s', 'Gyroscope'],
];
const imuWindow = new IMUWindowClient({ onWindow: (data) => {
  window.dispatchEvent(new CustomEvent('ds-imu-window', { detail: data }));
  const samples = data?.state === 'receiving' || data?.state === 'degraded' ? data.samples : [];
  for (const [canvas, field, label] of imuPlots) {
    drawIMUChart(canvas, samples, field);
    canvas.parentElement.setAttribute('aria-label', samples.length
      ? `${label}: ${samples.length} recent live IMU samples; X blue, Y brown, Z green`
      : `${label}: no current IMU data`);
  }
} });
imuWindow.start();
window.addEventListener('pagehide', () => imuWindow.stop());

async function loadTestInputResult() {
  try {
    let response = await fetch('/api/workout/model-check', { cache: 'no-store' });
    if (!response.ok) response = await fetch('./test-input-result.json', { cache: 'no-store' });
    if (!response.ok) return;
    const result = parseTestInputResult(await response.json());
    if (!result) return;
    document.querySelector('#test-input-class').textContent = `Class ${result.predicted_class}`;
    document.querySelector('#test-input-probability').textContent = `${(result.calibrated_probability * 100).toFixed(1)}%`;
    const model = document.querySelector('#test-input-model');
    model.textContent = 'V5 scope-faithful';
    model.title = result.model_version;
    document.querySelector('#test-input-output').hidden = false;
  } catch {
    // A missing, invalid, or unreachable fixed input never changes live readiness.
  }
}

void loadTestInputResult();

mountDemoPage();
const initialPage = pageTabs.find(tab => `#${tab.dataset.page}` === location.hash);
if (initialPage) selectPage(initialPage);
