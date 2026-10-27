/** Same-origin real session commands. No optimistic/fabricated model results. */
export function setControlState({
  sessionState, commandPending, serviceAvailable, validContext, hasCompletedSet,
}) {
  const busy = sessionState === 'active' || sessionState === 'paused';
  return {
    busy,
    primaryAction: busy ? 'stop' : 'start',
    primaryLabel: busy ? 'Finish + JSON' : 'Start set',
    primaryDisabled: commandPending || !serviceAvailable || (!busy && !validContext),
    pauseDisabled: commandPending || !busy,
    stopDisabled: commandPending || !busy,
    pauseLabel: sessionState === 'paused' ? 'Resume' : 'Pause',
    downloadVisible: !busy && hasCompletedSet,
  };
}

export function completedSetDownload(completedSet) {
  if (!completedSet || completedSet.schema_version !== 1
    || completedSet.kind !== 'digital_spotter_research_set'
    || typeof completedSet.session_id !== 'string' || !completedSet.session_id) return null;
  const safeId = completedSet.session_id.replace(/[^a-zA-Z0-9_-]/g, '-');
  return {
    filename: `digital-spotter-set-${safeId}.json`,
    text: `${JSON.stringify(completedSet, null, 2)}\n`,
  };
}

export class WorkoutClient {
  constructor({ fetchFn = (...args) => fetch(...args), onStatus }) {
    this.fetchFn = fetchFn;
    this.onStatus = onStatus;
    this.timer = null;
    this.available = false;
    this.inFlight = false;
  }
  async poll() {
    if (this.inFlight) return;
    this.inFlight = true;
    try {
      const response = await this.fetchFn('/api/workout/status', { cache: 'no-store' });
      if (!response.ok) throw new Error('workout service unavailable');
      const state = await response.json();
      if (state.version !== 'workout_v1'
        || !['connected', 'disconnected', 'unavailable'].includes(state.network?.state)
        || typeof state.network.has_local_address !== 'boolean'
        || !['idle', 'active', 'paused'].includes(state.session?.state)
        || !Number.isInteger(state.session.rep_count) || state.session.rep_count < 0
        || !Number.isFinite(state.session.elapsed_s)) throw new Error('invalid workout status');
      this.available = true;
      this.onStatus(state);
      return state;
    } catch {
      this.available = false;
      this.onStatus(null);
      return null;
    } finally { this.inFlight = false; }
  }
  async command(action, data = {}) {
    const response = await this.fetchFn('/api/workout/command', {
      method: 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-DS-Workout': '1' },
      body: JSON.stringify({ action, data }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error ?? 'Command failed');
    this.onStatus(result);
    return result;
  }
  start() { if (this.timer === null) this.timer = setInterval(() => this.poll(), 1000); }
  stop() { clearInterval(this.timer); this.timer = null; }
}
