/**
 * frontend/js/charts.js
 * Purpose: Chart.js angle time series chart — rolling 60-frame window
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

class AngleChart {
    constructor() {
        this._chart = null;
        this._maxFrames = 60;
        this._frameCount = 0;
        this._joints = ['LEFT_KNEE', 'RIGHT_KNEE', 'LEFT_HIP', 'RIGHT_HIP', 'TRUNK', 'LEFT_ANKLE', 'RIGHT_ANKLE'];
        this._colors = ['#00e5ff', '#00b8d4', '#7b61ff', '#9c84ff', '#ffa726', '#00c853', '#66bb6a'];
    }

    init(canvasEl) {
        const ctx = canvasEl.getContext('2d');
        this._chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: this._joints.map((name, i) => ({
                    label: name.replace('_', ' '),
                    data: [],
                    borderColor: this._colors[i],
                    borderWidth: name.includes('KNEE') ? 2 : 1,
                    pointRadius: 0,
                    tension: 0.3,
                    fill: false,
                })),
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                scales: {
                    x: { display: false },
                    y: {
                        min: 0, max: 180,
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#5f6368', font: { family: "'Space Mono'", size: 9 } },
                    },
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'bottom',
                        labels: {
                            color: '#5f6368',
                            font: { family: "'Space Mono'", size: 8 },
                            boxWidth: 8, padding: 6,
                            usePointStyle: true,
                        },
                    },
                },
                interaction: { intersect: false, mode: 'index' },
            },
        });
    }

    update(angles) {
        if (!this._chart) return;
        this._frameCount++;
        this._chart.data.labels.push(this._frameCount);
        if (this._chart.data.labels.length > this._maxFrames) {
            this._chart.data.labels.shift();
        }

        this._joints.forEach((joint, i) => {
            const ds = this._chart.data.datasets[i];
            ds.data.push(angles[joint] || 0);
            if (ds.data.length > this._maxFrames) ds.data.shift();
        });

        this._chart.update('none');
    }

    highlight(jointName) {
        if (!this._chart) return;
        this._chart.data.datasets.forEach((ds, i) => {
            ds.borderWidth = (this._joints[i] === jointName) ? 3 : 1;
        });
        this._chart.update('none');
    }

    reset() {
        if (!this._chart) return;
        this._frameCount = 0;
        this._chart.data.labels = [];
        this._chart.data.datasets.forEach(ds => { ds.data = []; });
        this._chart.update('none');
    }

    setWindow(frames) { this._maxFrames = frames; }
}
