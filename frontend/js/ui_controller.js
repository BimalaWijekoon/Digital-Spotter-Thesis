/**
 * frontend/js/ui_controller.js
 * Purpose: Orchestrates all UI components — connects stream, websocket, overlay, charts
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

class UIController {
    constructor() {
        this.stream = new StreamManager();
        this.socket = new APISocket();
        this.overlay = new PoseOverlay();
        this.chart = new AngleChart();
        this._sessionId = null;
        this._sessionTimer = null;
        this._sessionStart = null;
        this._overlayVisible = true;
    }

    init() {
        // Pi backend host — set explicitly via window.DS_PI_HOST (injected by
        // a small inline <script> in index.html) so the dashboard can be
        // hosted on a completely different domain (e.g. Vercel) while still
        // talking to the Pi over its Tailscale address.
        // Falls back to window.location.hostname for the case where Flask
        // is still serving the dashboard directly from the Pi itself.
        const host = window.DS_PI_HOST || window.location.hostname || '100.84.40.18';
        const apiPort = 5000;
        const streamPort = 8889;
        const streamPath = 'picam';

        // Init overlay & chart
        this.overlay.init(
            document.getElementById('video-feed'),
            document.getElementById('pose-canvas')
        );
        this.chart.init(document.getElementById('angle-chart'));

        // Connect WebSocket
        this.socket.connect(host, apiPort);
        this.socket.on('connect', () => this._onConnected());
        this.socket.on('disconnect', () => this._onDisconnected());
        this.socket.on('pose_data', (d) => this.onPoseData(d));
        this.socket.on('inference_result', (d) => this.onInferenceResult(d));
        this.socket.on('rep_complete', (d) => this.onRepComplete(d));
        this.socket.on('session_update', (d) => this.onSessionUpdate(d));
        this.socket.on('system_status', (d) => this.onSystemStatus(d));

        // Connect MJPEG stream
        const videoEl = document.getElementById('video-feed');
        videoEl.src = `http://${host}:${apiPort}/api/video_feed`;
        
        // Hide no-signal when image loads
        videoEl.onload = () => {
            document.getElementById('no-signal').classList.add('hidden');
        };
        videoEl.onerror = () => {
            document.getElementById('no-signal').classList.remove('hidden');
            console.log('[UI] MJPEG stream not available');
        };

        // Bind UI controls
        this._bindControls();

        // Load session history
        this._loadSessionHistory();

        console.log('[UI] Initialized');
    }

    onPoseData(data) {
        // Update angle cards
        if (data.angles) {
            for (const [joint, angle] of Object.entries(data.angles)) {
                const el = document.getElementById(`angle-${joint}`);
                if (el) el.textContent = `${Math.round(angle)}°`;
            }
            this.chart.update(data.angles);
        }

        // Update overlay
        if (data.landmarks) {
            this.overlay.draw(data.landmarks);
            if (data.angles) {
                this.overlay.drawAngleAnnotation('LEFT_KNEE', data.angles.LEFT_KNEE, data.landmarks);
                this.overlay.drawAngleAnnotation('RIGHT_KNEE', data.angles.RIGHT_KNEE, data.landmarks);
            }
        }

        // Update FPS/latency
        if (data.fps !== undefined) document.getElementById('fps-label').textContent = `${Math.round(data.fps)} FPS`;
        if (data.processing_time_ms !== undefined) document.getElementById('latency-label').textContent = `${Math.round(data.processing_time_ms)}ms`;
    }

    onInferenceResult(result) {
        const alert = document.getElementById('form-alert');
        const label = document.getElementById('form-label');
        const bar = document.getElementById('form-bar');
        const conf = document.getElementById('form-confidence');
        const feedbackFill = document.getElementById('feedback-fill');

        const pct = Math.round((result.confidence || 0.5) * 100);

        if (result.is_bad_form) {
            alert.className = 'card form-alert bad';
            label.textContent = 'BAD FORM';
        } else {
            alert.className = 'card form-alert good';
            label.textContent = 'GOOD FORM';
        }

        bar.style.width = `${100 - pct}%`;
        feedbackFill.style.width = `${100 - pct}%`;
        conf.textContent = `${100 - pct}% good`;
    }

    onRepComplete(rep) {
        // Update phase indicator
        document.querySelectorAll('.phase-step').forEach(el => el.classList.remove('active'));
        const phaseEl = document.getElementById(`phase-${rep.phase}`);
        if (phaseEl) phaseEl.classList.add('active');
    }

    onSessionUpdate(stats) {
        document.getElementById('rep-total').textContent = stats.total_reps || 0;
        document.getElementById('rep-good').textContent = stats.good_reps || 0;
        document.getElementById('rep-bad').textContent = stats.bad_reps || 0;
    }

    onSystemStatus(status) {
        document.getElementById('sys-camera').textContent = status.camera_ok ? '✓ OK' : '✗ Off';
        document.getElementById('sys-model').textContent = status.model_ok ? '✓ Loaded' : '✗ None';
        if (status.clients !== undefined) document.getElementById('sys-clients').textContent = status.clients;
    }

    async startSession(exerciseId, heightCm, weightKg, ftr, loadKg) {
        try {
            const resp = await fetch('/api/session/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    exercise_id: parseInt(exerciseId),
                    height_cm: parseFloat(heightCm),
                    weight_kg: parseFloat(weightKg),
                    ftr: parseFloat(ftr),
                    load_kg: parseFloat(loadKg)
                }),
            });
            const data = await resp.json();
            this._sessionId = data.session_id;

            // UI state
            document.getElementById('btn-start-session').classList.add('hidden');
            document.getElementById('btn-stop-session').classList.remove('hidden');
            document.getElementById('session-timer').classList.remove('hidden');
            document.getElementById('rep-total').textContent = '0';
            document.getElementById('rep-good').textContent = '0';
            document.getElementById('rep-bad').textContent = '0';
            this.chart.reset();

            // Start timer
            this._sessionStart = Date.now();
            this._sessionTimer = setInterval(() => this._updateTimer(), 1000);

            // Request live data
            this.socket.startStream();
        } catch (e) {
            console.error('[UI] Failed to start session:', e);
        }
    }

    async stopSession() {
        if (!this._sessionId) return;
        try {
            const resp = await fetch('/api/session/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: this._sessionId }),
            });
            const data = await resp.json();

            // UI state
            document.getElementById('btn-start-session').classList.remove('hidden');
            document.getElementById('btn-stop-session').classList.add('hidden');
            clearInterval(this._sessionTimer);

            this.socket.stopStream();
            this._loadSessionHistory();
            this._sessionId = null;
        } catch (e) {
            console.error('[UI] Failed to stop session:', e);
        }
    }

    toggleOverlay() {
        this._overlayVisible = !this._overlayVisible;
        this.overlay.setVisible(this._overlayVisible);
    }

    // Private methods
    _onConnected() {
        const dot = document.getElementById('status-dot');
        dot.classList.add('connected');
        dot.classList.remove('error');
        document.getElementById('connection-label').textContent = 'Connected';
    }

    _onDisconnected() {
        const dot = document.getElementById('status-dot');
        dot.classList.remove('connected');
        dot.classList.add('error');
        document.getElementById('connection-label').textContent = 'Disconnected';
    }

    _bindControls() {
        document.getElementById('btn-start-session').addEventListener('click', () => {
            const exId = document.getElementById('exercise-select').value;
            const height = document.getElementById('subject-height').value || 175.0;
            const weight = document.getElementById('subject-weight').value || 75.0;
            const ftr = document.getElementById('subject-ftr').value || 1.20;
            const load = document.getElementById('session-load').value || 0.0;
            this.startSession(exId, height, weight, ftr, load);
        });
        document.getElementById('btn-stop-session').addEventListener('click', () => {
            this.stopSession();
        });
        document.getElementById('btn-toggle-overlay').addEventListener('click', () => {
            this.toggleOverlay();
        });
        document.getElementById('btn-fullscreen').addEventListener('click', () => {
            const container = document.getElementById('video-container');
            if (document.fullscreenElement) document.exitFullscreen();
            else container.requestFullscreen().catch(() => { });
        });
    }

    _updateTimer() {
        if (!this._sessionStart) return;
        const elapsed = Math.floor((Date.now() - this._sessionStart) / 1000);
        const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const s = String(elapsed % 60).padStart(2, '0');
        document.getElementById('timer-value').textContent = `${m}:${s}`;
    }

    async _loadSessionHistory() {
        try {
            const resp = await fetch('/api/sessions?limit=5');
            const data = await resp.json();
            const list = document.getElementById('session-list');

            if (!data.sessions || data.sessions.length === 0) {
                list.innerHTML = '<div class="session-list__empty">No sessions yet</div>';
                return;
            }

            list.innerHTML = data.sessions.map(s => `
                <div class="session-item anim-fade-in">
                    <span class="session-item__name">${s.exercise_name}</span>
                    <span class="session-item__stats">
                        <span class="session-item__good">${s.good_reps}✓</span>
                        <span class="session-item__bad">${s.bad_reps}✗</span>
                    </span>
                </div>
            `).join('');
        } catch (e) {
            /* Session history will load when API is available */
        }
    }
}