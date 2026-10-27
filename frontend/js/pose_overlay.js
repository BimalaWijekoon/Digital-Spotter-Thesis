/**
 * frontend/js/pose_overlay.js
 * Purpose: Canvas overlay — draws BlazePose skeleton on top of video
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

class PoseOverlay {
    constructor() {
        this._canvas = null;
        this._ctx = null;
        this._video = null;
        this._visible = true;
        this._connections = [
            [11,12],[11,23],[12,24],[23,24],
            [23,25],[24,26],[25,27],[26,28],
            [27,29],[28,30],[29,31],[30,32],[27,31],[28,32],
        ];
        this._landmarkMap = {
            'LEFT_SHOULDER':11,'RIGHT_SHOULDER':12,
            'LEFT_HIP':23,'RIGHT_HIP':24,
            'LEFT_KNEE':25,'RIGHT_KNEE':26,
            'LEFT_ANKLE':27,'RIGHT_ANKLE':28,
            'LEFT_HEEL':29,'RIGHT_HEEL':30,
            'LEFT_FOOT_INDEX':31,'RIGHT_FOOT_INDEX':32,
            'NOSE':0,
        };
    }

    init(videoEl, canvasEl) {
        this._video = videoEl;
        this._canvas = canvasEl;
        this._ctx = canvasEl.getContext('2d');
        this._resizeCanvas();
        window.addEventListener('resize', () => this._resizeCanvas());
    }

    draw(landmarks) {
        if (!this._visible || !this._ctx) return;
        this.clear();

        const w = this._canvas.width;
        const h = this._canvas.height;

        // Build index-based lookup
        const pts = {};
        for (const [name, coords] of Object.entries(landmarks)) {
            const idx = this._landmarkMap[name];
            if (idx !== undefined) {
                pts[idx] = this._scaleToCanvas(coords[0], coords[1], w, h);
            }
        }

        // Draw connections
        this._ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)';
        this._ctx.lineWidth = 2;
        this._ctx.lineCap = 'round';
        for (const [a, b] of this._connections) {
            if (pts[a] && pts[b]) {
                this._ctx.beginPath();
                this._ctx.moveTo(pts[a].x, pts[a].y);
                this._ctx.lineTo(pts[b].x, pts[b].y);
                this._ctx.stroke();
            }
        }

        // Draw joints
        for (const [idx, pt] of Object.entries(pts)) {
            this._ctx.fillStyle = 'rgba(0, 229, 255, 0.9)';
            this._ctx.beginPath();
            this._ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
            this._ctx.fill();
            this._ctx.strokeStyle = 'rgba(0, 229, 255, 0.4)';
            this._ctx.lineWidth = 1;
            this._ctx.beginPath();
            this._ctx.arc(pt.x, pt.y, 7, 0, Math.PI * 2);
            this._ctx.stroke();
        }
    }

    drawAngleAnnotation(joint, angle, landmarks) {
        if (!this._ctx || !landmarks[joint]) return;
        const w = this._canvas.width;
        const h = this._canvas.height;
        const pt = this._scaleToCanvas(landmarks[joint][0], landmarks[joint][1], w, h);
        this._ctx.fillStyle = '#fff';
        this._ctx.font = '11px "Space Mono", monospace';
        this._ctx.fillText(`${Math.round(angle)}°`, pt.x + 10, pt.y - 5);
    }

    clear() {
        if (this._ctx) this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);
    }

    setVisible(v) { this._visible = v; if (!v) this.clear(); }
    isVisible() { return this._visible; }

    _scaleToCanvas(nx, ny, w, h) {
        return { x: nx * w, y: ny * h };
    }

    _resizeCanvas() {
        if (!this._canvas || !this._video) return;
        const rect = this._video.getBoundingClientRect();
        this._canvas.width = rect.width;
        this._canvas.height = rect.height;
    }
}
