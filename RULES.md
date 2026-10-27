# Digital Spotter engineering rules

These rules are normative. `MUST`, `MUST NOT`, `SHOULD`, and `MAY` have their usual
standards meaning. Exceptions require an entry in `docs/DECISIONS.md` with owner
approval, reason, risk, and rollback.

**Active research exception:** ADR-019 is owner-approved and controls the current
BLE bring-up. Commercial security requirements remain future hardening, not active
research gates. Reliability and observability are established before optional
standard BLE bonding. This exception does not permit secrets in Git/logs, public
exposure of unauthenticated mutation endpoints, or silent representation of an
open research link as production-secure.

## 1. Product and safety

1. The product MUST be described as exercise analysis/feedback, not as a medical
   device, injury-prevention guarantee, or replacement for a qualified coach.
2. Feedback MUST be non-blocking and must never control gym equipment.
3. A low-confidence pose, stale IMU, missing model, or synchronization failure MUST
   produce an explicit degraded state.
4. The UI MUST distinguish measured facts, model estimates, warnings, and missing
   data.
5. User-facing analysis MUST include the model/version that generated it.

## 2. Edge-first behavior

1. Rep detection, inference, feedback, and local save MUST work with the WAN
   disconnected.
2. Cloud calls MUST NOT run in a capture, fusion, rep, or inference callback.
3. Every high-rate queue MUST have a documented maximum size and overflow policy.
4. The vision path MUST prefer the newest frame and discard stale frames.
5. The IMU path MUST preserve sequence gaps; it MUST NOT fabricate missing samples.
6. A cloud backlog MUST be persisted in SQLite and retried with capped exponential
   backoff and jitter.
7. A process MUST have one clear hardware/resource owner.

## 3. Wireless and timing

1. ESP32-C3 to Pi transport MUST use local BLE for the product path unless a later
   approved hardware test disproves its reliability.
2. IMU packets MUST be binary, versioned, bounded, and include a sequence number
   and sensor monotonic timestamp.
3. Product control commands MUST be authenticated and replay-resistant. During the
   ADR-019 research ladder, an unencrypted link MAY carry only bounded harmless
   echo/start/stop/identify test commands; model-derived or privileged actions
   remain disabled until the selected research security mode is recorded.
4. Fusion MUST map sensor time into the Pi monotonic clock domain and handle counter
   wrap and device restart.
5. Fusion MUST use measurement timestamps, not packet arrival timestamps.
6. Initial active-mode goals are 50 Hz minimum, 100 Hz target, less than 0.5 percent
   sample loss over 30 minutes, and less than 20 ms alignment error. These are
   acceptance targets until measured on the final enclosure and mounting position.
7. Cloud MQTT and ESP-NOW MUST NOT be added to the critical loop without an approved
   architecture decision.

## 4. Vision and performance

1. Only the vision worker MAY own the camera and pose estimator.
2. Camera acquisition and pose inference MUST be decoupled with latest-frame
   semantics.
3. Video for the user interface MUST use hardware H.264 and direct WebRTC in the
   final architecture.
4. Pose overlay drawing SHOULD run in the browser from landmark telemetry.
5. Per-frame Python JPEG encoding and server-side skeleton drawing MUST be removed
   before the product release gate.
6. Every performance change MUST have before/after measurements using a person in
   frame and the same scenario.
7. The Pi MUST pass the thermal soak gate without throttling under the supported
   ambient temperature and enclosure.

## 5. Model and data integrity

1. Live, replay, API, and test inference MUST share one canonical feature builder.
2. The exact input shape, feature order, units, coordinate system, preprocessing,
   threshold, labels, and missing-data policy MUST be versioned as one model
   contract.
3. A feature-contract mismatch MUST fail closed; padding/truncating a production
   vector is forbidden.
4. A missing model or preprocessing artifact MUST fail readiness in production.
5. Random/mock predictions MUST never be persisted as user analysis.
6. The production Pi runtime MUST use a model composed of built-in LiteRT/TFLite
   operators unless an approved benchmark justifies a Flex dependency.
7. Model replacement requires parity evaluation on a sealed test set plus Pi
   latency and memory evidence.
8. Raw training data, split definitions, model manifests, and artifact hashes MUST
   remain traceable.

## 6. API and application design

1. HTTP/WebSocket handlers MUST authenticate, validate, delegate, and format
   responses; they MUST NOT own hardware or reproduce domain calculations.
2. Public request/response schemas and error codes MUST be versioned and tested.
3. Mutation endpoints MUST be authorized and protected from replay and cross-site
   abuse.
4. CORS MUST be an explicit allow-list in production.
5. Health endpoints MUST report `starting`, `ready`, or `degraded` per component and
   MUST expose whether real or simulated adapters are active without leaking
   credentials.
6. Internal class attributes MUST NOT be used as an API between components.
7. Graceful shutdown MUST stop sessions safely, flush local transactions, close
   BLE/camera resources, and leave recoverable state.

## 7. Persistence and cloud

1. SQLite is the on-device system of record for sessions and the durable upload
   outbox.
2. Schema changes MUST use numbered, forward-only migrations with backup and
   rollback instructions.
3. Writes MUST use transactions and foreign keys; high-rate raw samples MUST be
   batched or stored as bounded compressed chunks when retention is enabled.
4. Firestore MUST be reached through an authenticated backend gateway. The Pi MUST
   NOT hold Firebase Admin credentials.
5. Cloud records MUST be idempotent by device/session/event ID.
6. Video and raw IMU upload MUST be opt-in, purpose-limited, size-bounded, and
   retention-controlled.
7. Successful cloud upload MUST NOT delete the only local copy until retention and
   recovery rules are implemented and tested.

## 8. Security

1. Secrets MUST never enter Git, logs, examples, test snapshots, model metadata, or
   firmware source.
2. Each physical device MUST have a unique identity and credential.
3. TLS certificate verification MUST remain enabled in production.
4. Commercial BLE MUST use bonding/encryption plus application-level authenticated
   session establishment for a headless device. Under ADR-019, plain BLE is allowed
   for controlled research and standard BLE bonding is optional after functional
   reliability passes; custom application cryptography is deferred.
5. Commercial firmware and software updates MUST be signed and support rollback.
   Research firmware MUST at minimum have a frozen, hash-recorded rollback binary.
6. Services MUST run as an unprivileged dedicated user with the minimum Linux
   groups and filesystem access.
7. Local sockets, data files, and secret files MUST have least-privilege ownership
   and permissions.
8. Security-sensitive failures MUST fail closed and emit a redacted audit event.
9. Dependencies and container/base images MUST be pinned and scanned before a
   release.

## 9. Code quality

1. New domain code MUST be typed at public boundaries and documented where intent
   or invariants are not obvious.
2. Prefer small modules with one responsibility and explicit dependency injection.
3. Do not add a framework, broker, database, or daemon when the standard library or
   an existing approved dependency satisfies the measured need.
4. No broad `except Exception` at a system boundary without classification,
   logging, and a defined state transition.
5. Time, randomness, hardware, and network dependencies MUST be injectable for
   deterministic tests.
6. Logs MUST be structured and include component, event, device/session correlation
   IDs, and severity.
7. Production paths MUST NOT mutate `sys.path` at runtime after the packaging
   migration.
8. Dead and historical implementations MUST be archived only after behavioral
   parity and rollback evidence exist.

## 10. Tests and evidence

1. Every work package MUST identify its tests and evidence before implementation.
2. A bug fix MUST include a failing regression test unless it is purely hardware or
   visual and the reason is recorded.
3. Unit tests MUST be deterministic and offline.
4. Hardware tests MUST identify the Pi, ESP32 firmware, IMU, camera, model, power
   supply, cooling, enclosure, mounting, and test duration.
5. Mock-mode success MUST NOT satisfy a hardware or release gate.
6. Performance claims MUST report scenario, sample count, percentile, temperature,
   throttling state, and relevant versions.
7. `git diff --check` and relevant tests MUST pass after the final edit.
8. Validation duration MUST be proportional to the scoped failure mechanism: small
   documentation, UI, parser, schema, or isolated logic changes MUST NOT trigger a
   hardware soak without a stated sustained-risk reason.
9. A 30/60-minute soak MUST be reserved for a gate candidate or a change that can
   affect sustained timing, loss, memory, thermal/power, radio, or recovery behavior.
   Short and extended checks MUST pass before starting it.
10. Prior soak evidence MAY be reused only when the measured hardware, artifacts,
    configuration, and affected critical path are unchanged. A critical-path change
    MUST receive one final integrated soak before its milestone gate closes.

## 11. Git and delivery

1. Preserve user-owned modified and untracked files.
2. Do not perform destructive cleanup or history rewriting without explicit owner
   approval.
3. Keep changes scoped to one work package or a documented set of dependent
   packages.
4. A commit message SHOULD reference the plan work-package ID.
5. Do not claim deployed, secure, production-ready, or complete without the
   corresponding evidence gate.
6. Update the current-state document when code reality changes and the decision log
   when architecture changes.
