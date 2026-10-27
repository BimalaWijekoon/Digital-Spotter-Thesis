# Device preflight — 2026-09-15

Scope: current read-only device inspection before continuing the research
checklist in `PLAN.md` section 14. Human-camera acceptance is explicitly last.

## Observed

| Check | Result |
|---|---|
| Pi SSH | Successful key-based, noninteractive login using existing access |
| Architecture | aarch64 |
| Uptime at first check | Approximately 49 minutes |
| Load averages | 0.00 / 0.00 / 0.00 |
| Power flags | `throttled=0x0` |
| Temperature | 56.0 C, one idle measurement |
| RAM | 7819 MiB total, 7581 MiB available; swap unused |
| Root disk | 29 GB total, approximately 14 GB available, 50% used |
| Bluetooth | Service active, controller powered, discovery off |
| Camera enumeration | `rpicam-hello --list-cameras` detects IMX219, 3280x2464 |
| Matching capture/BLE client processes | `bluetoothd` only in the checked Python/Bluetooth/MediaMTX/rpicam/libcamera process-name filter |
| Matching service units | No spotter/MediaMTX/camera-named units returned by the service-unit filter |
| Windows USB serial | CP210x USB-to-UART adapter on COM7, VID 10C4 / PID EA60 |

Kernel warning inspection showed boot-time dummy-regulator/staging-module warnings
and two `brcmf_cfg80211_reg_notifier: Firmware rejected country setting` entries.
SSH worked during inspection. The country-setting warning is recorded for later
network investigation if symptoms occur; its cause was not diagnosed and no
network configuration was changed.

## Evidence boundaries

- COM7 identifies the connected USB serial adapter; it does not prove the running
  ESP firmware, IMU identity or BLE stream. Those require checklist item 2.
- Camera enumeration does not prove frame capture, pose quality or browser video.
- Idle temperature and current power flags do not establish sustained stability.
- No serial port was opened, no firmware flashed, no service restarted, and no
  Pi networking, credentials or Bluetooth state changed.
- No mock or replay was used. No application regression suite was needed for
  these read-only hardware inspections and documentation edits.

Result: Pi access and initial device availability verified. Continue with a short
existing-R9 GATT/IMU verification; retain human-camera tests for the final stage.
