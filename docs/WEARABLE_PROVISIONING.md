# Wearable provisioning and recovery

**Status:** Deferred product-hardening design; no active R9 provisioning workflow

This runbook separates ordinary owner onboarding from trusted manufacturing. It
contains no credential values. The normal gym link remains BLE; USB is used only
at a trusted manufacturing or recovery bench.

## 1. Roles and artifacts

- A trusted manufacturing station creates one random 32-byte key per wearable and
  one random 16-byte claim nonce. There is no fleet/default key.
- The wearable identity is `dsimu-` plus the lowercase 12-hex-digit ESP Bluetooth
  base MAC already defined by the firmware contract.
- The manufacturing station writes the identity and device key into encrypted NVS,
  creates one confidential `DSIMU1:` claim, and records only its non-secret
  fingerprint in inventory/audit data.
- The confidential claim may be rendered as a covered QR or transferred once over
  another approved local channel. It is equivalent to a password and must never be
  logged, placed on a command line, photographed for support, or stored in Git.
- The Pi imports the claim into its owner-only identity directory. It never receives
  an ESP flash-encryption key or release-signing private key.

## 2. Future production firmware security profile

The active R9 Arduino firmware does not implement provisioning, Secure Boot,
flash encryption, encrypted NVS, or signed updates. The earlier ESP-IDF candidate
and its build defaults were removed with explicit owner approval. If commercial
hardening resumes, create a new reviewed implementation and reproducible build;
do not follow a command that assumes deleted files.

That future profile should require Secure Boot v2, release-mode flash encryption,
encrypted NVS with a dedicated key partition, isolated signing, and only signed
production artifacts.

Building is safe. Flashing and first boot can permanently burn eFuses, disable
debug/download paths, and make an incorrectly signed device unbootable. Before any
production-device first boot:

1. verify ESP32-C3 revision 0.3 or newer and stable power;
2. archive the exact signed bootloader, partition table, app, public verification
   key, build manifest, hashes, ESP-IDF version, and device inventory record;
3. verify the recovery/update image with the same signing trust;
4. have a second operator compare the intended eFuse plan with a read-only eFuse
   summary;
5. obtain the product owner's explicit authorization for the manufacturing batch;
6. flash one sacrificial device first, inspect secure-boot/flash-encryption status,
   prove signed update and recovery, then authorize the remaining batch.

Never commit or copy the Secure Boot private key to a Pi, customer device, source
checkout, CI log, or support bundle.

## 3. Future owner onboarding on the Pi

The operator opens a local trusted terminal and imports the claim from a protected
file or standard input. The secret itself is never a command-line argument:

```bash
dsctl wearable provision \
  --claim-file /run/digital-spotter/onboarding/wearable.claim \
  --identity-dir /var/lib/digital-spotter/identity
```

For an interactive scanner that writes only to standard input:

```bash
dsctl wearable provision --claim-file - \
  --identity-dir /var/lib/digital-spotter/identity
```

Import fails closed for malformed/non-canonical claims, wrong permissions,
symlinks, existing identity files, all-zero keys, and integrity failures. On
success, delete/shred the transient claim according to the approved onboarding
station policy and retain only the receipt fingerprint. File deletion policy for
customer systems requires the privacy/retention decision; do not improvise it.

## 4. Future physical Pi binding

The following is a design target, not an available R9 operation:

1. Place the provisioned wearable next to the intended Pi.
2. Hold the ESP32-C3 BOOT button for 2 to 3 seconds, then release. Eight seconds is
   reserved for factory reset.
3. A 900 ms cyan/blue pulse with two short 2.5 kHz buzzer pulses confirms that
   the pairing window opened. The window remains open for 120 seconds. If that
   acknowledgement does not occur, release the button and do not start pairing.
4. Start the Pi IMU agent. BLE Secure Connections encryption must complete, then
   the application HMAC challenge must prove the unique device key.
5. Only after both checks pass does the wearable store that controller identity.
6. Reconnect without reopening the window and verify that the stored controller is
   accepted. A different controller remains rejected.

The physical window never bypasses application authentication. Possession of an
old BLE bond without the unique device key is insufficient to claim a wearable.

## 5. Factory reset and recovery

Factory reset is destructive and must be an explicit, sustained physical action.
The final implementation must atomically destroy the application device key,
controller allow-list, session/replay state, and all NimBLE bonds; it must then
restart into `unprovisioned`. It must not erase calibration or other product data
unless that additional scope is explicitly approved and documented.

R9 has no product factory-reset/provisioning state machine. Before implementing
and exercising a future destructive reset on the bench:

1. verify the owner-only recovery identity/key and original 4 MB device backup;
2. stage the exact firmware/NVS restore commands without printing secrets;
3. obtain explicit owner approval for erasing this wearable's key, controller, and
   BLE bonds;
4. hold BOOT for 8 seconds, verify old authorization and bond fail, restore through
   the trusted USB bench, re-import/re-bind, and verify normal reconnect;
5. record only artifact hashes, state transitions, and pass/fail results.

Customer recovery must issue a new unique key/claim. A reset key is never reused
and no support backdoor or shared recovery secret is allowed.

## 6. Release evidence

A product batch cannot pass the security gate without evidence of:

- secure-boot, flash-encryption, and encrypted-NVS state on a sacrificial unit;
- unsigned, modified, corrupt, and rollback images being rejected as designed;
- valid signed update and recovery;
- one-Pi controller binding and unknown-controller rejection;
- captured command replay and wrong-key rejection;
- destructive reset invalidating the old key/bond, followed by successful recovery;
- logs, repository, artifacts, and support output containing no secrets.
