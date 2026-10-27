/**
 * frontend/js/stream.js
 * Purpose: WebRTC connection manager — connects to mediamtx WHEP endpoint
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

class StreamManager {
    constructor() {
        this._pc = null;
        this._videoEl = null;
        this._connected = false;
        this._onPlayingCb = null;
        this._onStatsCb = null;
        this._statsInterval = null;
        this._whepUrl = '';
    }

    async connect(host, port, path) {
        this._whepUrl = `http://${host}:${port}/${path}/whep`;
        try {
            this._pc = this._createPeerConnection();
            this._pc.addTransceiver('video', { direction: 'recvonly' });
            this._pc.addTransceiver('audio', { direction: 'recvonly' });
            const offer = await this._pc.createOffer();
            await this._pc.setLocalDescription(offer);
            await this._negotiateWhep(offer);
            this._startStatsPolling();
        } catch (e) {
            console.error('[Stream] Connection failed:', e);
            this._connected = false;
        }
    }

    disconnect() {
        if (this._statsInterval) clearInterval(this._statsInterval);
        if (this._pc) { this._pc.close(); this._pc = null; }
        this._connected = false;
        console.log('[Stream] Disconnected');
    }

    attachVideo(videoEl) { this._videoEl = videoEl; }
    onPlaying(cb) { this._onPlayingCb = cb; }
    onStats(cb) { this._onStatsCb = cb; }
    isConnected() { return this._connected; }

    async reconnect(host, port, path) {
        this.disconnect();
        await this.connect(host, port, path);
    }

    _createPeerConnection() {
        const pc = new RTCPeerConnection({
            iceServers: [],
            sdpSemantics: 'unified-plan',
        });
        pc.ontrack = (ev) => {
            if (this._videoEl && ev.streams[0]) {
                this._videoEl.srcObject = ev.streams[0];
                this._videoEl.play().catch(() => {});
                this._connected = true;
                if (this._onPlayingCb) this._onPlayingCb();
                console.log('[Stream] Video track received');
            }
        };
        pc.oniceconnectionstatechange = () => {
            console.log('[Stream] ICE state:', pc.iceConnectionState);
            if (pc.iceConnectionState === 'disconnected' || pc.iceConnectionState === 'failed') {
                this._connected = false;
            }
        };
        return pc;
    }

    async _negotiateWhep(offer) {
        const resp = await fetch(this._whepUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/sdp' },
            body: offer.sdp,
        });
        if (!resp.ok) throw new Error(`WHEP ${resp.status}`);
        const sdp = await resp.text();
        await this._pc.setRemoteDescription({ type: 'answer', sdp });
    }

    _startStatsPolling() {
        this._statsInterval = setInterval(async () => {
            if (!this._pc || !this._onStatsCb) return;
            try {
                const stats = await this._pc.getStats();
                let report = {};
                stats.forEach(s => {
                    if (s.type === 'inbound-rtp' && s.kind === 'video') {
                        report.fps = s.framesPerSecond || 0;
                        report.bytesReceived = s.bytesReceived || 0;
                        report.packetsLost = s.packetsLost || 0;
                    }
                });
                this._onStatsCb(report);
            } catch (e) { /* ignore stats errors */ }
        }, 1500);
    }
}
