const ENDPOINT = '/api/research/session-status';
const SENSOR_STATES = new Set(['receiving', 'degraded', 'stale', 'unavailable']);

function validStatus(status) {
  return status?.version === 'research_status_v1'
    && ['idle', 'active', 'stopping', 'storage_degraded', 'closed'].includes(status.session?.state)
    && Number.isSafeInteger(status.session?.rep_count)
    && status.session.rep_count >= 0
    && SENSOR_STATES.has(status.wearable?.state)
    && SENSOR_STATES.has(status.camera?.state)
    && status.analysis?.state === 'unavailable'
    && status.analysis?.reason === 'v5_live_feature_contract_unverified'
    && (status.latest_rep === null || (
      Number.isSafeInteger(status.latest_rep?.number)
      && status.latest_rep.number >= 1
      && ['good', 'vision_degraded', 'imu_degraded', 'unsynchronized', 'unavailable'].includes(status.latest_rep.quality)
    ));
}

export class ResearchSessionStatus {
  constructor({ fetchFn = (...args) => globalThis.fetch(...args), onStatus }) {
    if (typeof onStatus !== 'function') throw new TypeError('onStatus is required');
    this.fetchFn = fetchFn;
    this.onStatus = onStatus;
    this.timer = null;
    this.inFlight = false;
    this.unsupported = false;
  }

  async pollOnce() {
    if (this.inFlight || this.unsupported) return;
    this.inFlight = true;
    try {
      const response = await this.fetchFn(ENDPOINT, { cache: 'no-store' });
      if (response.status === 404) {
        this.unsupported = true;
        if (this.timer !== null) clearInterval(this.timer);
        this.timer = null;
        this.onStatus(null);
        return;
      }
      if (!response.ok) throw new Error('status unavailable');
      const status = await response.json();
      if (!validStatus(status)) throw new Error('invalid research status');
      this.onStatus(status);
    } catch {
      this.onStatus(null);
    } finally {
      this.inFlight = false;
    }
  }

  start() {
    if (this.timer !== null) return;
    void this.pollOnce();
    this.timer = setInterval(() => { void this.pollOnce(); }, 1000);
  }

  stop() {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.onStatus(null);
  }
}
