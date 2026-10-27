# BLE R7 — reconnect and restart evidence

**Result:** PASS
**Completed:** 2026-08-28
**Environment:** real Raspberry Pi 4B, ESP32-C3, and MPU6500
**Mode:** plain BLE, explicitly unpaired and unbonded

R7 retained the complete passing R6 real-IMU contract and added only bounded
recovery. The ESP restarts advertising non-blockingly after disconnect with a
100 ms delay, at most three attempts, and 500 ms between failed attempts. The Pi
test client uses `pair=false` and at most three scan/connect attempts with bounded
0/0.5/1.0 second backoff.

## Results

The ordinary recovery matrix passed 10/10. Every connection completed the R7
device-info check, bounded control echo, real 20-byte notification check, clean
disconnect, and fresh advertisement discovery.

```text
cycles=10/10
bounded_retries=0
stream_samples=56
advertising_recovery_ms=110.484..308.700
```

After the owner disconnected ESP USB power, waited five seconds, and reconnected
it, the first Pi connection attempt timed out. The designed 0.5-second backoff
then recovered on attempt 2. Real streaming passed and advertising returned in
122.566 ms after the client stopped.

After `sudo systemctl restart bluetooth`, the controller was powered, idle, and
had no competing BLE client. Reconnection passed on attempt 1, real stream
timestamps remained monotonic, and advertising returned in 167.640 ms.

No pairing, bond, BlueZ device removal, global Bluetooth-state deletion, NVS
erase, or full-chip erase was used.

## Preserved diagnostic

The first R7 matrix invocation stopped on a transient inherited sensor-interval
assertion before exact interval diagnostics were printed. No ESP change followed.
The diagnostic single cycle and full 10-cycle rerun passed, with per-cycle
timestamp deltas retained in the checkpoint. The required R7 recovery gates did
not reproduce the failure.

## Boundary

R7 proves the standalone research client and ESP recovery behavior. It does not
yet provide research status/start/stop controls, final NeoPixel/buzzer cues,
standard bonding, or the canonical boot-managed Pi adapter. R8 is next.
