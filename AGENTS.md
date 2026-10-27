# Digital Spotter agent instructions

This file is the root instruction source for all work in this repository. It
applies to every directory unless a more specific `AGENTS.md` is added later.

## Mission

Convert the current prototype into a secure, measurable, maintainable exercise
analysis product for a Raspberry Pi 4B 8 GB and a separate wireless lower-back
ESP32-C3 + MPU6500 wearable. Preserve working behavior while replacing prototype
paths through staged, reversible work.

The product is edge-first:

- Camera and IMU capture, fusion, rep detection, inference, feedback, and local
  session persistence must continue without internet access.
- ESP32-C3 to Pi transport is local secure BLE. Cloud MQTT is not part of the
  target real-time path.
- Wi-Fi is for browser access, administration, updates, and asynchronous cloud
  synchronization.
- SQLite is the local source of truth and outbox. Cloud storage is downstream.

## Fixed constraints

- Edge computer: Raspberry Pi 4 Model B, 8 GB RAM.
- Sensor MCU: ESP32-C3.
- Sensor: MPU6500 mounted in a separate lower-back wearable (`WHO_AM_I=0x70`).
- No tether between the moving sensor and the Pi in normal gym use.
- Vision must be optimized for the Pi rather than assuming an accelerator.
- Real hardware behavior must be distinguished from mocks and development data.
- Do not interpret lower-back IMU motion as direct barbell velocity or power.
  Freeze those semantics only after an independently validated derivation or a
  retrained model contract replaces them.

## Required reading order

Before making a non-trivial change, read the documents relevant to the work:

1. `AGENTS.md`
2. `docs/PRODUCT_REQUIREMENTS.md`
3. `docs/CURRENT_STATE.md`
4. `ARCHITECTURE.md`
5. `docs/INTERFACES.md`
6. `docs/SECURITY.md`
7. `RULES.md`
8. `PLAN.md`
9. `docs/TEST_STRATEGY.md`
10. `docs/OPERATIONS.md`
11. `docs/DECISIONS.md`

`PLAN.md` controls implementation order. `ARCHITECTURE.md` controls target component
boundaries. `docs/INTERFACES.md` controls wire and data contracts. `RULES.md` wins
when an old prototype comment or historical plan conflicts with it.

The superseded root JSON plans were removed during the approved M3-00 cleanup.
They are not current authority; Git history retains the previously tracked copies.

## Before changing code

1. Run `git status --short` and preserve all user-owned changes.
2. Identify the `PLAN.md` work-package ID being implemented.
3. Trace the current path end-to-end before replacing it.
4. Record assumptions that cannot be verified locally.
5. Define the relevant acceptance test before implementation.
6. Confirm whether the test uses real hardware, a deterministic replay, or a mock.
7. For destructive cleanup, database migrations, credential rotation, cloud
   provisioning, or Git-history rewriting, obtain explicit owner approval.

Do not combine cleanup, architecture replacement, model changes, and UI redesign in
one unreviewable change. Prefer thin vertical slices with rollback boundaries.

## Non-negotiable system behavior

- There must be one canonical feature-building and inference path. Manual API,
  replay, live session, and tests must call it rather than rebuilding features.
- High-rate queues must be bounded. Vision uses latest-frame semantics; stale
  frames are dropped rather than processed late.
- Sensor samples and camera results use monotonic capture timestamps. Fusion must
  not use network arrival time as measurement time.
- Sequence gaps, clock resets, stale samples, low pose visibility, and missing
  model artifacts are explicit states.
- Missing IMU data must not be silently replaced with zeros in production scoring.
- Mock inference must never set a production readiness flag or produce persisted
  user-facing analysis as if it were real.
- A network or cloud outage must not interrupt an active local session.
- Database writes occur outside high-rate capture callbacks and use transactions.
- Video is streamed with hardware H.264/WebRTC. Python MJPEG is a migration-only
  fallback, not the target product path.
- The model package includes a machine-readable manifest, hashes, input shape,
  exact feature order, preprocessing contract, threshold, metrics, and provenance.

## Security requirements

- Never commit secrets, private keys, real Wi-Fi credentials, device credentials,
  Firebase service-account keys, or user data.
- Any discovered credential exposure is a release blocker. Sanitizing a file is
  not rotation; the credential owner must revoke and replace it.
- The Pi must not contain a Firebase Admin service-account key.
- Cloud writes go through an authenticated API gateway with per-device identity.
- BLE commands require a provisioned device identity, encryption/bonding, a
  session nonce, authentication, and replay protection.
- Production API mutation endpoints require authentication and authorization.
- CORS must use an explicit allow-list; wildcard CORS is development-only.
- TLS certificate verification may not be disabled in production firmware.
- Logs and telemetry must not contain secrets, raw biometric video by default, or
  unnecessary personal information.

Read `docs/SECURITY.md` before touching provisioning, networking, authentication,
cloud storage, logs, video retention, firmware updates, or secrets.

## Code boundaries

The target package layout is defined in `ARCHITECTURE.md`. Until migration reaches
that layout:

- New product logic belongs in a new canonical package, not in
  `scripts/dashboard/main.py`.
- FastAPI handlers validate/authorize and delegate; they do not engineer model
  features or own hardware.
- The vision worker is the only owner of camera/pose resources.
- The IMU adapter is the only owner of BlueZ/BLE state.
- The core owns session state, time alignment, fusion, inference, and persistence.
- Cloud sync reads the durable outbox; it does not subscribe directly to live
  sensor callbacks.
- Hardware adapters expose interfaces so deterministic replay and fakes can test
  the core without pretending to be release hardware.

Avoid deep access to another class's private attributes. Add a narrow public
interface or event contract instead.

## Dependency and configuration rules

- Use one locked Python dependency definition after the packaging migration.
- Pin versions used in production and record Raspberry Pi/aarch64 compatibility.
- Do not import full TensorFlow in the final Pi runtime. The production model must
  use built-in LiteRT/TFLite operations unless an approved decision says otherwise.
- All configuration is typed, validated on startup, and separated into
  development, test, and production profiles.
- Production must fail closed on missing mandatory configuration. It must not
  silently switch to mock mode.
- Hostnames, ports, hardware IDs, and paths must not be hard-coded in application
  logic.

## Verification and evidence

At minimum, run the tests associated with the touched component. The current
prototype baseline commands are:

```bash
python -m pytest tests -q
python scripts/validate_model.py
git diff --check
```

Use `docs/TEST_STRATEGY.md` for product gates. Every handoff must state:

- files changed;
- tests run and exact result;
- real hardware used or not used;
- mock/replay components used;
- performance measurements taken or not taken;
- security or data migrations still pending;
- whether changes are uncommitted, committed locally, or pushed.

Passing unit tests is not proof that BLE, camera, timing, thermal, cloud, or gym
behavior works.

## Documentation maintenance

Update documentation in the same change when a contract or decision changes:

| Change | Required document |
|---|---|
| Product scope or acceptance criterion | `docs/PRODUCT_REQUIREMENTS.md` |
| Component/data-flow boundary | `ARCHITECTURE.md` and `docs/DECISIONS.md` |
| BLE/event/API/schema contract | `docs/INTERFACES.md` |
| Security control or threat | `docs/SECURITY.md` |
| Work status, dependency, gate | `PLAN.md` |
| Test layer or performance budget | `docs/TEST_STRATEGY.md` |
| Deployment, monitoring, recovery | `docs/OPERATIONS.md` |
| Verified current-code fact | `docs/CURRENT_STATE.md` |

Do not mark a work package complete without its acceptance evidence. Do not replace
measured facts with estimates.

## Stop and ask the owner

Stop before proceeding when any of these decisions is required and not already
recorded:

- a change from the accepted lower-back ESP32-C3 + MPU6500 wearable;
- deletion or archival of prototype directories or data;
- rewriting Git history to remove secrets;
- destructive database migration;
- Firebase/Google Cloud project creation, billing, or production deployment;
- certificate authority, user identity, retention, or privacy-policy choices;
- a change to the model feature contract, label meaning, or safety claims;
- a hardware purchase or a change beyond the fixed Pi 4B/ESP32-C3 scope.

## Definition of done

A task is done only when its scoped behavior is implemented, relevant automated
tests pass, required real-hardware evidence is recorded, security checks pass,
documentation is current, rollback is known, and no mock is being represented as a
real product result.
