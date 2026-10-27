# Digital Spotter security baseline

> **Active research profile (ADR-019, 2026-08-27):** The current deliverable is a
> controlled research system. Reliability is built first from the passing Arduino
> BLE baseline. The mandatory controls for this phase are no secrets in Git/logs,
> no MQTT or WAN dependency in the sensor loop, expected-device checks on the Pi,
> bounded harmless commands, and no public exposure of unauthenticated mutation
> APIs. Standard BLE pairing/bonding is optional after the functional ladder is
> stable. HMAC/HKDF, device claims, controller binding, Secure Boot, flash
> encryption, eFuses, signed OTA, and commercial hostile-device testing are
> deferred. The detailed controls below remain future product-hardening guidance
> and must not be represented as current research gates.

**Status:** Target controls plus current release blockers
**Last reviewed:** 2026-09-15

Security is a product gate, not a deployment checkbox. This system observes human
movement, stores workout/possibly biometric-adjacent data, controls local feedback
devices, accepts wireless commands, and may synchronize to cloud accounts.

## 1. Current critical actions

### SEC-001 Revoke the exposed MQTT credential

A working-looking broker password was committed in `.env.example`. The tracked file
has been sanitized, but the credential must be treated as compromised.

Required owner actions:

1. Revoke/delete the old broker credential.
2. Create a unique, least-privilege temporary credential only if the MQTT prototype
   must remain usable during migration.
3. Review broker connections/logs and topic ACLs for unexpected access.
4. Store the replacement outside Git.
5. Run a repository/history secret scan.
6. Decide explicitly whether to rewrite published Git history; do not rewrite it
   automatically because that is destructive coordination work.

On 2026-08-26 an ignored/untracked legacy firmware `secrets.h` was also found with
real-looking Wi-Fi and MQTT values. Git history contains no tracked copy. The
entire legacy MQTT firmware directory and that local file were permanently removed
with owner approval on 2026-08-28, but deletion is not revocation: the Wi-Fi and
broker values must still be rotated.

This blocker is complete only when the old credential is confirmed invalid.

### SEC-002 Keep insecure TLS out of active firmware

The deleted legacy MQTT firmware called `setInsecure()`, disabling broker
certificate verification. It remains only in older Git history and must never be
restored as an active product path. R9 contains no Wi-Fi/MQTT dependency. Any future
HTTPS/MQTT/OTA path must validate the chain, hostname, time policy, and approved
trust roots.

### SEC-003 Protect the local API

M6-D02's opt-in synthetic demo exposes reference-only probabilities on a separate
private research route, not live Workout scoring. Keep the loopback listener and
exact Origin plus `X-DS-Demo: 1` mutation guard. Requests select only whitelisted
frozen fixtures; arbitrary features, chosen predictions and load overrides are
rejected. No participant data, credentials, actuator command or persisted workout
analysis is created. This is private research access, not production auth, and
does not remove the outstanding credential-rotation or live feature gates.

The active FastAPI prototype allows wildcard CORS and unauthenticated mutation
endpoints. Until M6, it must be treated as development-only and isolated from
untrusted networks.

The temporary research session-status viewer added on 2026-09-30 is separate:
it binds HTTP to `127.0.0.1`, exposes one read-only status route, adds no CORS or
browser mutation endpoint, and never publishes V5 probabilities while live
feature provenance is unresolved. Access from another machine requires an
explicit private SSH tunnel. It is not an authenticated production interface.
An explicit research CLI option can invoke frozen V5 inference in reference-only
shadow mode. It reports only execution/unavailable state to the terminal and
does not publish probabilities/classes, persist analysis, or send wearable
feedback. This is a development diagnostic, not a relaxation of the live
feature-parity or production authorization gates.

The separate 2026-10-03 Pi-hosted Step 1 shell serves only static research UI
assets on `127.0.0.1:8766`. Access from the owner's PC uses SSH forwarding; the
static server has no research/session mutation API or model-result route. It
must not be rebound to LAN/Tailscale or represented as authenticated product UI.
For the bounded Step 2 camera check, RTSP/WHEP/ICE-TCP listeners were also bound
to Pi loopback and forwarded only through SSH. This is temporary private-bench
access, not an authenticated video entitlement or authority to enable LAN video.
The follow-up on-demand research relay keeps those same three listeners on Pi
loopback, with a single explicit browser origin. The UI no longer asks for a
camera URL, but that does not add authentication: anyone with local access to
the Pi listener or the private SSH tunnel can request video. Do not expose the
relay on a LAN or reuse it as the product stream endpoint.
The later fixed-input V5 calculation is a separate, explicit Pi command that
publishes only non-personal fitted-state numbers as a static file for the
Devices → Analysis **Test input** card. The browser rejects any file that
claims `live=true`, lacks `reference_only=true`, has the wrong model version,
or has an inconsistent class/threshold. The live research status route and
Workout Feedback still expose no V5 probability or class. This does not make
the local page an authenticated product dashboard or establish live scoring.
The subsequent isolated Pi status copy replaces the static-only server on the
same loopback port with the existing read-only `research_status_v1` endpoint.
An additional bounded read-only IMU-window route on that loopback listener
feeds the two browser plots. It contains only recent motion vectors, no secret,
user identity, video, or model output; it is still private-bench telemetry and
must not be exposed on LAN without an authenticated product API.
It creates a separate summary-only local research session but adds no browser
mutation route, CORS grant, model result, or public listener. The on-demand
camera hook shares one owner between H.264 and pose events. The BLE agent
requests no pairing and leaves an undiscovered wearable unavailable. This
remains private-bench access through an owner's SSH tunnel, not authenticated
product access.

The optional person-pose diagnostic replaces the static-only loopback server
with a narrow, research-only POST start action. It requires the exact forwarded
browser Origin and a non-simple header, accepts no body, allows one test at a
time, and saves only aggregate counts/timing under the isolated Pi research
directory. It is not product authentication or a LAN-safe mutation API; do not
expose port 8766 beyond loopback/SSH or save raw video for this test.

M6-R02's latest-pose route is also research-only and loopback/SSH-only. It
exposes at most one fresh 33-landmark pose with capture timing, unchanged quality
and no identity. Participant-sensitive landmarks remain transient in memory;
do not add request-body/response logging, disk retention, CORS or LAN exposure.
The guide does not authorize a workout score or relax production access checks.

M6-D11 is a narrow owner-approved exception for the current research appliance.
On 2026-10-26 the owner explicitly accepted exposing its unauthenticated UI/API,
WHEP and ICE surfaces to devices authorized in the private tailnet, while
forbidding public Funnel access. UI/API, WHEP and RTSP listeners stay on loopback
behind Tailscale Serve. ICE-TCP binds only to the configured Tailscale IPv4 so
WebRTC SDP does not advertise loopback; no LAN or wildcard bind is used. The exact
HTTPS MagicDNS Origin and custom mutation headers are still required. This does
not constitute application authentication, production
authorization or permission for LAN/public exposure. Any authorized tailnet
device can reach these research surfaces, and the Pi device hostname is recorded
in public certificate-transparency logs. Roll back by resetting Serve and
restoring the prior loopback-only environment/release.

## 2. Assets

- device identities, pairing secrets, update signing trust roots;
- local account/session tokens and cloud device credentials;
- workout/session/rep/model-analysis data;
- any raw video, landmarks, or IMU evidence;
- model artifacts, thresholds, preprocessing, and firmware;
- local SQLite state and durable cloud outbox;
- camera, BLE sensor, buzzer/RGB feedback, update channel;
- operational logs, diagnostics, and cloud audit trails.

## 3. Threat actors and conditions

- another person on the gym LAN;
- nearby BLE attacker or accidentally paired customer sensor;
- stolen/lost Pi or ESP device/SD card;
- malicious or compromised browser/client;
- compromised dependency/update/cloud credential;
- replayed/spoofed sensor or session commands;
- tenant/user authorization bug in cloud APIs;
- curious operator accessing excessive video/biometric-adjacent data;
- accidental outage, disk exhaustion, power loss, clock jump, or corrupted update.

Physical possession cannot be made risk-free, but unique keys, encryption,
least-privilege storage, reset/revocation, and minimized retained data reduce impact.

## 4. Trust boundaries

| Boundary | Required controls |
|---|---|
| ESP32-C3 to Pi BLE | provisioned identity, encryption/bonding, authenticated session/commands, nonce/replay checks, strict parser |
| Client to local Pi | physical pairing, device identity pinning, TLS/WSS, short-lived authorization, explicit origins, rate limits |
| Pi process boundary | dedicated user/group, UDS permissions/peer credentials, size/schema limits, minimal device access |
| Pi to cloud | verified TLS, unique device credential, token rotation/revocation, idempotency, request limits |
| Cloud gateway to Firebase | workload identity/IAM, no static Admin key on edge/client, validation, tenant ownership, audit logs |
| Update to Pi/ESP/model | signed manifest/artifacts, version/rollback policy, health gate, anti-downgrade policy |

## 5. Device identity and provisioning

### Pi identity

- Generate a unique device key during trusted provisioning.
- Prefer a hardware-backed key where product cost permits; otherwise protect the
  private key with owner-only filesystem permissions and encryption-at-rest policy.
- Encode device ID and public-key fingerprint in the physical QR/onboarding record.
- Cloud registration binds the device identity to an authorized owner/account.
- Support rotation, revocation, ownership transfer, and factory reset.

### ESP32-C3 identity

- Provision a unique device secret/key; never a fleet-wide default.
- Store it in encrypted NVS and enable ESP Secure Boot v2 plus release-mode flash
  encryption for production after recovery/manufacturing tests. Ordinary NVS is
  not directly protected by flash encryption, so the production partition table
  includes a separate encrypted `nvs_keys` partition and enables ESP-IDF NVS
  encryption.
- Pair only during a short physical-action provisioning window.
- Bind the ESP identity to the intended Pi/owner and show identity in the UI.
- Factory reset destroys bonds/session keys and requires new provisioning.

### Headless BLE authentication

BLE `Just Works` alone does not establish strong human-verified identity. The
application performs a challenge-response using the provisioned key, derives a
session key, authenticates state-changing commands, and rejects nonce/command replay.
BLE bonding/encryption remains required to protect the link and privacy.

These controls are not active R9 behavior. R9 deliberately runs open research BLE
with bounded harmless controls and no persistent application secret, pairing,
bonding, or controller binding. The abandoned ESP-IDF security experiment and its
local provisioning artifacts are not retained recovery points. If product
hardening resumes, implement and validate this section as a new isolated stage;
do not copy the deleted recovery state machine or claim its former bench results.
The future manufacturing/recovery design remains in `WEARABLE_PROVISIONING.md`.

## 6. Local client authentication

The final method depends on ADR-013, but it must provide:

- a physical pairing mode that expires automatically;
- verification/pinning of the Pi device public key through a QR/onboarding proof;
- TLS/WSS for local traffic;
- short-lived tokens scoped to owner/reader/session operations;
- token expiry, logout, revocation, and device reset;
- explicit allowed origins and CSRF protection where cookies are used;
- request IDs, idempotency keys, replay limits, body limits, and rate limits;
- no unauthenticated state-changing endpoint, WebSocket, video URL, or support API.

Discovery metadata must expose no secrets. The device should not rely on a fixed IP.

The M3-04 Step 1 MediaMTX WHEP listener is development-only and is not an approved
product-facing video endpoint. Its RTSP publisher input is restricted to loopback,
but the current WHEP surface has no implemented Digital Spotter client grant. Do
not expose it beyond a controlled local bench. Product use remains blocked until
the authenticated `GET /api/v1/stream-config` flow, TLS/origin policy, and host
firewall rule are implemented and tested.

The isolated browser wrapper accepts an HTTP(S) WHEP URL without embedded
credentials, query, or fragment and passes an optional bounded token separately to
MediaMTX's supported reader. Error states never include reader error text or the
token. This reduces accidental credential leakage but is not authentication: no
token issuer, authorization endpoint, TLS identity, origin decision, or WHEP
firewall policy exists yet.

The `research-preview.html` diagnostic is explicitly loopback-only and stops
after two minutes. Its vendored official v1.12.3 reader has no bearer-token
support; the research factory rejects nonempty tokens rather than ignoring them.
The separate `ui-preview/` camera option reuses this same reader but has an
explicit viewer-controlled lifetime instead of the diagnostic's two-minute deadline,
requires an explicit user action, and additionally requires the page itself to
be served from `http://127.0.0.1`. It is still an unauthenticated private-bench
diagnostic, not a product video entitlement. Do not open it from a LAN-hosted
preview or expose the WHEP listener beyond the private tunnel.
Its new pose/clock research bridge is likewise loopback-only and temporary. A
same-origin check on clock POST is **not** authentication; it must not be bound
to LAN/Tailscale or installed as a product service. Pose landmarks are
participant-sensitive, so use only an approved controlled bench and do not
retain them by default. M6 still owns authenticated delivery.
It must not serve as an authenticated product reader. Browser/server compatibility
was measured against v1.9.1 through a private SSH tunnel; no public/LAN video
listener, static bearer credential or production endpoint was introduced.

## 7. Cloud authentication and authorization

- Human identity uses Firebase Authentication or an approved equivalent.
- Device identity is separate from human identity and bound to an owner/account by
  the gateway.
- Pi uses a unique short-lived/revocable credential or signed exchange, not a
  Firebase Admin service-account JSON file.
- Cloud Run uses workload identity and least-privilege IAM to access Firestore,
  Storage, logs, and secrets.
- Every request validates tenant/user/device ownership server-side.
- Firestore security rules deny unintended direct client writes; Admin/server SDK
  access is controlled by IAM and application authorization.
- App Check can add abuse protection for supported clients but never replaces auth.

Separate development, staging, and production projects/credentials. Production
data must not be copied into development.

## 8. Secret storage and rotation

### Repository

Only placeholders and secret names are committed. CI scans the current tree and
history. Test credentials are synthetic and unmistakably invalid.

### Raspberry Pi

- `/etc/digital-spotter/secrets.env`, root-owned, mode `0600`, is the temporary
  baseline for runtime secrets.
- systemd loads it through `EnvironmentFile`; application logs never print values.
- device private keys and database encryption material live under a protected
  `/var/lib/digital-spotter/identity/` path with narrower access where possible.
- support bundles redact environment, tokens, local paths/usernames, Wi-Fi, and IDs.

### Cloud

Use Secret Manager, workload identity, audit logs, expiration/rotation, and separate
service accounts per component/environment.

For every credential define owner, purpose, privileges, location, creation,
rotation, revocation, and incident procedure.

## 9. Data protection and privacy

Data classes:

| Class | Default handling |
|---|---|
| Device health/versions | local + minimal cloud operations data |
| Session/rep summaries | local; selected cloud sync after authorization |
| Derived pose/landmarks | local/bounded; cloud only with approved purpose |
| Raw IMU | no cloud upload by default; bounded diagnostic retention if approved |
| Raw video/audio | no continuous retention/upload by default; audio not required |
| Account/contact data | cloud identity system; not duplicated unnecessarily on Pi |

Requirements:

- consent/purpose before collection beyond core operation;
- documented retention by class and environment;
- encryption in transit and approved at-rest protection;
- export and deletion behavior across local/outbox/cloud copies;
- redaction of logs, crash dumps, fixtures, and analytics;
- no face recognition or identity inference from camera data;
- access/audit review for operator tools.

## 10. Service hardening

Pi services run as a dedicated unprivileged account. Systemd should apply, where
compatible and tested:

- `NoNewPrivileges=true`
- `PrivateTmp=true`
- `ProtectSystem=strict`
- `ProtectHome=true`
- explicit `ReadWritePaths=`
- explicit device/group access for camera, Bluetooth, GPIO as required
- restricted address families/capabilities
- bounded memory/tasks/files
- watchdog and restart-rate limits
- restrictive `UMask`

Do not copy these options blindly: validate camera, BlueZ DBus, GPIO, UDS, SQLite,
and update needs and document each exception.

Use a host firewall to expose only the approved local HTTPS/WebRTC paths. Internal
UDS and MediaMTX publishing inputs remain loopback/local. SSH is disabled or
key-only and operationally controlled for the product image.

## 11. Input and parser security

- Validate BLE packet size/version/flags/ranges before conversion.
- Validate all MessagePack/JSON depth, map/list count, string length, and numeric
  finiteness.
- Never use substring matching for authenticated commands.
- Reject path traversal, unsafe filenames, oversized uploads, invalid content type,
  and unexpected archive members.
- Use parameterized SQL and transaction boundaries.
- Treat model/firmware/config files as signed untrusted input before activation.
- Do not deserialize untrusted pickle/joblib artifacts from cloud/user input. Model
  packages are signed and provisioned through the trusted update channel.

## 12. Updates and supply chain

- Pin and lock dependencies for Raspberry Pi aarch64 and cloud images.
- Generate an SBOM and scan dependencies/secrets before release.
- Sign release, model, and firmware manifests; verify before unpack/activate.
- Reject downgrade below a security floor while preserving an emergency recovery
  process.
- Activate atomically, run health checks, and roll back automatically on failure.
- Protect signing keys outside the repo/build host and define revocation.
- Record source revision, build environment, artifact hashes, and signer in release
  evidence.

## 13. Logging, audit, and monitoring

For M5-R04, session metadata uses the explicitly loaded model version. The new
synthetic candidate is opt-in and reference-only; no score, readiness override,
feedback permission, public listener or logging-retention policy is enabled by
loading it. Package SHA256 inventories detect accidental drift, not malicious
replacement/signature authenticity. No credentials or training data are logged.

Structured logs may contain component, event code, severity, software/model
version, coarse timing, request/trace/session IDs, and numeric health counters.

They must not contain passwords, keys, authorization headers, Wi-Fi credentials,
full provisioning QR material, raw video, raw sensor streams, or unnecessary user
attributes.

Audit events cover provisioning, pairing, authorization failure, ownership/key
change, factory reset, update/rollback, retention/deletion, and privileged export.
Audit storage is bounded and tamper-evident to the practical level of the device.

## 14. Security verification gates

Before local-product gate G5:

- credential and dependency scans pass;
- unknown/replayed BLE device/command tests pass;
- unauthenticated/unauthorized local mutations, WebSockets, and streams fail;
- CORS/origin/CSRF and rate/body limits pass;
- service permissions and support-bundle redaction pass;
- update signature and rollback tests pass at their milestone.

Before cloud gate G6:

- cross-user/cross-device/unknown/revoked access tests pass;
- direct Firestore/Storage access follows approved rules;
- Admin credentials are absent from edge/client artifacts;
- duplicate/replayed/oversized/malformed upload tests pass;
- retention, export, deletion, audit, budgets, and alerts pass in staging.

## 15. Incident response minimum

1. Identify affected credential/device/version/data class.
2. Revoke credentials or disable upload without breaking local safety.
3. Preserve redacted logs/evidence and stop unnecessary collection.
4. Roll back or isolate affected release.
5. Assess user/data impact and required notification.
6. Patch, rotate, validate, and stage before redeployment.
7. Record root cause and preventive test/control.

The owner must define support contacts, notification obligations, and production
response times before G8.
