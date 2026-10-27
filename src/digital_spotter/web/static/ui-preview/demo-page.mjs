import { DemoPlayback } from './demo-motion.mjs';
import { drawIMUChart } from './imu-charts.mjs';
import { DemoInferenceClient, describeDemoDecision } from './demo-inference.mjs';
import { phaseReplayView, drawPhaseIMUChart } from './demo-imu-replay.mjs';
import { getReviewClip } from './demo-review-clips.mjs';

export function mountDemoPage() {
  const root = document.querySelector('#demo-view');
  if (!root) return;
  const get = id => root.querySelector(`#${id}`);
  const exercise = get('demo-exercise'), form = get('demo-form'), load = get('demo-load');
  const play = get('demo-start'), pause = get('demo-pause'), reset = get('demo-reset');
  const chartSource = get('demo-imu-source');
  const player = new DemoPlayback();
  const inference = new DemoInferenceClient();
  let avatar, loading, frameId, lastFrame = 0, active = false, latestIMU = null;
  let catalog = null, requestedRep = 0, latestResult = null;
  let chartKey = '';

  function selection() { return { exercise: exercise.value, form: form.value }; }
  function selectedCase() {
    const config = selection();
    return catalog?.cases.find(item => item.exercise === config.exercise && item.form === config.form);
  }
  function clearResult() {
    inference.reset(); requestedRep = 0; latestResult = null;
    get('demo-result').textContent = 'Not run';
    get('demo-result').removeAttribute('data-class');
    get('demo-result-detail').textContent = catalog
      ? catalog.actuators_enabled
        ? 'Synthetic replay · physical cues ready'
        : 'Synthetic replay · physical feedback disabled'
      : 'Model connection unavailable';
    get('demo-probability').textContent = '—';
    get('demo-result').title = '';
  }
  function updateLoad() {
    load.value = selectedCase()?.load_kg ?? '';
  }
  async function predictRep(repId) {
    get('demo-result-detail').textContent = `Calculating · rep ${repId}`;
    try {
      const result = await inference.predict(selection(), repId);
      if (!result) return;
      latestResult = result;
      const description = describeDemoDecision(result);
      get('demo-result').textContent = description.result;
      get('demo-result').dataset.class = String(result.predicted_class);
      get('demo-probability').textContent = `${(100 * result.calibrated_probability).toFixed(1)}%`;
      get('demo-result-detail').textContent = description.detail;
      const cueState = result.actuators_enabled
        ? result.feedback.dispatched ? 'Physical cue sent' : 'Physical cue warning'
        : 'Physical feedback disabled';
      get('demo-result').title = `${result.model_version}\nRaw: ${result.raw_probability}\nCalibrated: ${result.calibrated_probability}\nThreshold: ${result.threshold}\n${cueState}`;
      get('demo-model-status').textContent = 'V5 · calculated';
    } catch (error) {
      latestResult = null;
      get('demo-result').textContent = 'Unavailable';
      get('demo-result').removeAttribute('data-class');
      get('demo-probability').textContent = '—';
      get('demo-result-detail').textContent = error.message;
      suspend();
    }
  }
  function showState() {
    const state = player.snapshot();
    play.disabled = !avatar || !catalog || state.state === 'running';
    const hasClip = getReviewClip(exercise.value, form.value) !== null;
    play.textContent = state.state === 'paused' ? 'Resume' : hasClip ? 'Start demo' : 'Run replay';
    pause.disabled = state.state !== 'running';
    for (const control of [exercise, form, load]) control.disabled = state.state === 'running';
    get('demo-reps').textContent = `${state.completedReps} / 3`;
    get('demo-elapsed').textContent = `${(state.elapsedMs / 1000).toFixed(1)} s`;
    get('demo-playback-status').textContent = {
      idle: 'Ready · 3 repetitions', running: 'Replay running', paused: 'Paused', complete: 'Replay complete',
    }[state.state];
    const config = selection();
    const view = phaseReplayView(selectedCase()?.imu_replay, state);
    const phases = config.exercise === 'squat' ? ['Descent', 'Bottom', 'Lockout'] : ['Setup', 'Mid-pull', 'Lockout'];
    get('demo-phase').textContent = view.phase ? `P${view.phase} · ${phases[view.phase - 1]}` : '—';
    if (avatar) get('demo-render-status').textContent = hasClip ? 'Review animation' : 'Clip not supplied';
    get('demo-animation-missing').hidden = hasClip;
    get('demo-canvas').setAttribute('aria-label', hasClip
      ? `${config.exercise} custom review animation` : 'No incorrect-form animation supplied');
    get('demo-motion-source').textContent = hasClip
      ? 'Predefined motion · separate replay inputs' : 'Replay inputs only · no matching animation';
    const technique = getReviewClip(config.exercise, config.form)?.technique
      ?? (config.form === 'correct' ? 'Correct form' : 'Incorrect form');
    get('demo-scenario-label').textContent = `${config.exercise === 'squat' ? 'Squat' : 'Deadlift'} · ${technique}`;
    get('demo-scenario-label').title = 'Selected demonstration example, not an error diagnosed by the binary classifier';
  }
  function draw(now = performance.now()) {
    if (!avatar || !active) return;
    const state = player.tick(now), config = selection();
    avatar.render({ ...config, progress: state.progress });
    if (catalog && state.completedReps > requestedRep) {
      requestedRep = state.completedReps;
      void predictRep(requestedRep);
    }
    if (chartSource.value === 'replay') drawIMU();
    showState();
  }
  function animate(now) {
    frameId = null;
    if (!active || player.state !== 'running') return;
    if (now - lastFrame >= 32) { draw(now); lastFrame = now; }
    if (player.state === 'running') frameId = requestAnimationFrame(animate);
  }
  function suspend() {
    player.pause(performance.now());
    if (frameId !== undefined && frameId !== null) cancelAnimationFrame(frameId);
    frameId = null;
    // pause() advances the clock to now; paint that same state once so the
    // phase badge, plot and human do not freeze on different render ticks.
    if (avatar && active) draw();
    else showState();
  }
  function drawIMU(data = latestIMU) {
    latestIMU = data;
    if (!active) return;
    if (chartSource.value === 'replay') {
      const scenario = selectedCase(), replay = scenario?.imu_replay;
      const view = phaseReplayView(replay, player.snapshot());
      const canvas = get('demo-acceleration');
      const key = `${scenario?.fixture_index}:${view.phase}:${canvas.clientWidth}:${canvas.clientHeight}`;
      if (chartKey !== key) {
        for (const [id, field] of [['demo-acceleration', 'acceleration_m_s2'], ['demo-gyroscope', 'angular_velocity_rad_s']]) {
          drawPhaseIMUChart(get(id), replay, view, field);
          get(id).parentElement.setAttribute('aria-label', `${field}: synthetic replay phase medians, ${view.points.length} of 3 phases shown`);
        }
        chartKey = key;
      }
      get('demo-imu-status').textContent = !replay ? 'Unavailable' : view.phase ? `Replay · P${view.phase}` : 'Replay · ready';
      get('demo-imu-note').textContent = '3 phase medians · not a live stream';
      return;
    }
    chartKey = '';
    const samples = ['receiving', 'degraded'].includes(data?.state) ? data.samples : [];
    get('demo-imu-status').textContent = samples.length ? 'Live wearable data' : 'No live data';
    get('demo-imu-note').textContent = 'Live wearable · not used by replay model';
    for (const [id, field] of [['demo-acceleration', 'acceleration_m_s2'], ['demo-gyroscope', 'angular_velocity_rad_s']]) {
      drawIMUChart(get(id), samples, field);
      get(id).parentElement.setAttribute('aria-label', samples.length ? `${field}: live wearable data` : `${field}: no live data`);
    }
  }
  async function activate() {
    active = true;
    if (!loading) get('demo-render-status').textContent = 'Loading 3D';
    if (!loading) loading = import('./demo-review-avatar.mjs?v=20261026-demo-pose-guide').then(async ({ createDemoAvatar }) => {
      avatar = await createDemoAvatar(get('demo-canvas'), get('demo-pose-guide-canvas'));
      get('demo-render-status').textContent = 'Review animation';
    }).catch(() => { get('demo-render-status').textContent = '3D unavailable'; });
    await Promise.all([loading, inference.catalog().then(value => {
      catalog = value; updateLoad();
      if (!latestResult) get('demo-result-detail').textContent = value.actuators_enabled
        ? 'Synthetic replay · physical cues ready' : 'Synthetic replay · physical feedback disabled';
      get('demo-model-status').textContent = latestResult ? 'V5 · calculated' : 'V5 · ready';
    }).catch(error => {
      catalog = null; updateLoad();
      get('demo-result-detail').textContent = error.message;
    })]);
    draw(); drawIMU(latestIMU); showState();
  }
  for (const control of [exercise, form, load]) control.addEventListener('change', () => {
    suspend(); player.reset(); clearResult(); updateLoad(); draw(); showState();
  });
  play.addEventListener('click', () => {
    if (!active || !avatar || !catalog) return;
    if (player.state !== 'paused') {
      clearResult();
      void inference.startFeedback().then(value => {
        if (value.enabled && !value.dispatched) {
          get('demo-result-detail').textContent = 'Demo started · physical cue unavailable';
        }
      }).catch(() => {
        get('demo-result-detail').textContent = 'Demo started · physical cue unavailable';
      });
    }
    player.start(performance.now()); showState();
    if (frameId === null || frameId === undefined) frameId = requestAnimationFrame(animate);
  });
  pause.addEventListener('click', suspend);
  reset.addEventListener('click', () => { suspend(); player.reset(); clearResult(); draw(); showState(); });
  chartSource.addEventListener('change', () => { chartKey = ''; drawIMU(); });
  window.addEventListener('ds-preview-page-change', ({ detail }) => {
    if (detail === 'demo') void activate();
    else { suspend(); active = false; }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) suspend(); });
  window.addEventListener('ds-workout-status', ({ detail }) => {
    const network = detail?.network?.state;
    get('demo-pi-status').textContent = detail
      ? network === 'connected' ? 'Core online · Wi-Fi connected'
        : network === 'disconnected' ? 'Core online · Wi-Fi disconnected'
          : 'Core online · Wi-Fi unavailable'
      : 'Unavailable';
    const wearable = detail?.wearable?.state;
    get('demo-wearable-status').textContent = ['receiving', 'degraded'].includes(wearable)
      ? 'Live data arriving' : wearable === 'stale' ? 'Stale' : 'Unavailable';
    get('demo-model-status').textContent = catalog ? (latestResult ? 'V5 · calculated' : 'V5 · ready')
      : detail?.model?.loaded ? 'Loaded · demo disabled' : 'Unavailable';
  });
  window.addEventListener('ds-imu-window', ({ detail }) => drawIMU(detail));
  window.addEventListener('pagehide', () => { suspend(); avatar?.dispose(); }, { once: true });
  showState();
}
