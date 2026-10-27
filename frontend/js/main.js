/**
 * frontend/js/main.js
 * Purpose: Entry point — initializes UIController on DOM ready
 * Author: bimalawijekoon
 * Version: 1.0.0
 */

let app;

document.addEventListener('DOMContentLoaded', () => {
    app = new UIController();
    app.init();
    console.log('[DigitalSpotter] Dashboard ready');
});
