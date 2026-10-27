/**
 * frontend/js/websocket.js
 * Purpose: Socket.IO client — connects to Flask-SocketIO API
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

class APISocket {
    constructor() {
        this._socket = null;
        this._connected = false;
        this._handlers = {};
    }

    connect(host, port) {
        const url = `http://${host}:${port}`;
        this._socket = io(url, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 10,
        });

        this._socket.on('connect', () => {
            this._connected = true;
            console.log('[WS] Connected');
            if (this._handlers['connect']) this._handlers['connect']();
        });

        this._socket.on('disconnect', () => {
            this._connected = false;
            console.log('[WS] Disconnected');
            if (this._handlers['disconnect']) this._handlers['disconnect']();
        });

        this._socket.on('connect_error', (err) => {
            console.warn('[WS] Connection error:', err.message);
        });

        // Auto-register known events
        const events = ['pose_data', 'inference_result', 'rep_complete',
                        'session_update', 'system_status', 'error',
                        'stream_started', 'stream_stopped', 'pong'];
        events.forEach(ev => {
            this._socket.on(ev, (data) => {
                if (this._handlers[ev]) this._handlers[ev](data);
            });
        });
    }

    on(event, callback) { this._handlers[event] = callback; }
    emit(event, data) { if (this._socket) this._socket.emit(event, data); }
    startStream() { this.emit('start_stream'); }
    stopStream() { this.emit('stop_stream'); }
    isConnected() { return this._connected; }

    disconnect() {
        if (this._socket) { this._socket.disconnect(); this._socket = null; }
        this._connected = false;
    }
}
