/** Same-origin polling for the temporary loopback-only M3-04 research bridge. */

export class ResearchTelemetrySession {
  constructor({
    controller,
    fetchFn = (...args) => globalThis.fetch(...args),
    setIntervalFn = setInterval,
    clearIntervalFn = clearInterval,
    onTransportState = () => {},
  }) {
    if (!controller || typeof controller.start !== 'function'
      || typeof controller.acceptPoseSample !== 'function'
      || typeof controller.createClockSyncRequest !== 'function'
      || typeof controller.resetTelemetry !== 'function') {
      throw new TypeError('live video controller is required');
    }
    this.controller = controller;
    this.fetchFn = fetchFn;
    this.setIntervalFn = setIntervalFn;
    this.clearIntervalFn = clearIntervalFn;
    this.onTransportState = onTransportState;
    this.active = false;
    this.cursor = 0;
    this.requestNumber = 0;
    this.polling = false;
    this.syncing = false;
    this.abort = null;
    this.pollTimer = null;
    this.clockTimer = null;
  }

  async start(whepUrl) {
    if (this.active) throw new Error('research telemetry is already active');
    await this.controller.start({ whepUrl });
    this.active = true;
    this.cursor = 0;
    this.abort = new AbortController();
    await Promise.all([this.pollOnce(), this.syncOnce()]);
    if (this.active) {
      this.pollTimer = this.setIntervalFn(() => { void this.pollOnce(); }, 50);
      this.clockTimer = this.setIntervalFn(() => { void this.syncOnce(); }, 2_000);
    }
  }

  stop() {
    if (!this.active) return;
    this.active = false;
    this.abort.abort();
    if (this.pollTimer !== null) this.clearIntervalFn(this.pollTimer);
    if (this.clockTimer !== null) this.clearIntervalFn(this.clockTimer);
    this.pollTimer = null;
    this.clockTimer = null;
    this.controller.stop();
  }

  async pollOnce() {
    if (!this.active || this.polling) return;
    this.polling = true;
    try {
      const response = await this.fetchFn(`/api/pose-events?after=${this.cursor}`, {
        cache: 'no-store', credentials: 'omit', signal: this.abort.signal,
      });
      if (!response.ok) throw new Error('pose endpoint unavailable');
      const batch = await response.json();
      if (!Number.isSafeInteger(batch?.cursor) || batch.cursor < this.cursor
        || !Array.isArray(batch.events) || batch.events.length > 120) {
        throw new TypeError('invalid pose batch');
      }
      if (!this.active) return;
      for (const event of batch.events) this.controller.acceptPoseSample(event);
      this.cursor = batch.cursor;
      this.onTransportState('pose_transport_ready');
    } catch {
      if (this.active) {
        this.cursor = 0;
        this.controller.resetTelemetry('pose_transport_unavailable');
        this.onTransportState('pose_transport_unavailable');
      }
    } finally {
      this.polling = false;
    }
  }

  async syncOnce() {
    if (!this.active || this.syncing) return;
    this.syncing = true;
    try {
      const request = this.controller.createClockSyncRequest(`research-${++this.requestNumber}`);
      const response = await this.fetchFn('/api/clock-sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        cache: 'no-store', credentials: 'omit', signal: this.abort.signal,
      });
      if (!response.ok) throw new Error('clock endpoint unavailable');
      const body = await response.json();
      if (this.active) {
        this.controller.acceptClockSyncResponse(body);
        this.onTransportState('clock_synchronized');
      }
    } catch {
      if (this.active) {
        this.controller.resetTelemetry('clock_sync_unavailable');
        this.onTransportState('clock_sync_unavailable');
      }
    } finally {
      this.syncing = false;
    }
  }
}
