# M0-02 exposed credential rotation evidence

**Status:** BLOCKED on credential-owner action
**Prepared:** 2026-08-26
**Historical introduction:** commit `8b763f3` (`.env.example`)
**Additional local exposure:** ignored/untracked firmware `secrets.h`; not found in
Git history, sanitized 2026-08-26

Do not paste a credential, broker export, screenshot containing secrets, or access
token into this file, an issue, a commit, or chat. Record only identifiers and
outcomes that are safe to disclose.

## Current repository containment

- `.env.example` contains only the invalid host `mqtt.example.invalid` and
  `replace_me` placeholders.
- Real `.env` files and `firmware/esp32_c3_imu/secrets.local.h` are ignored.
- The tracked/fail-closed `secrets.h` template contains placeholders only. The
  prior ignored local file held real-looking Wi-Fi and MQTT values; Git log/search
  found no commit for that file, but the values were visible to workspace tooling
  and must be treated as exposed.
- The legacy MQTT path is disabled in the documented baseline.
- The historical credential remains in Git history until the owner makes a
  separate, explicitly approved history-rewrite decision.

Containment is not rotation. The package cannot be marked `DONE` until the broker
rejects the old credential.

## Owner action in the HiveMQ Cloud console

1. Identify the credential that was present in commit `8b763f3` without copying it
   into a terminal transcript or this repository.
2. Revoke or delete that credential.
3. Inspect broker access logs from 2026-06-29 onward for unexpected clients,
   source addresses, topic access, or publish/subscribe activity.
4. Preserve the audit result in the broker/provider system. Record only the safe
   result fields below.
5. Do not create a replacement unless the legacy MQTT prototype is still needed.
   The product sensor path is BLE. If a temporary replacement is necessary, give
   it a unique identity and the narrowest topic permissions, and store it only in
   an ignored local secret file or runtime secret store.

## Owner action for the exposed Wi-Fi network

1. Change the exposed Wi-Fi password through the router/access-point owner flow.
2. Reconnect only authorized devices using the new value.
3. Review the router client list/logs for unknown clients to the extent supported.
4. Store any temporary legacy firmware copy only in ignored `secrets.local.h`.
5. Do not put the new SSID/password or a router screenshot in chat, Git, or evidence.

## Safe completion record

Fill these fields without secret values:

```text
Credential owner: PENDING
Revoked at (UTC): PENDING
Provider credential identifier suffix: PENDING
Old credential connection attempt rejected at (UTC): PENDING
Broker audit-log review window: PENDING
Unexpected activity found: PENDING
Incident reference if applicable: PENDING
Replacement created: no / yes, legacy-only
Wi-Fi credential owner: PENDING
Wi-Fi password changed at (UTC): PENDING
Router client/log review completed: PENDING
Verified by: PENDING
```

## Verification and gate

M0-02 is complete only when all of the following are true:

- the old credential is confirmed invalid by the provider or a bounded rejected
  connection attempt;
- the audit-log review is recorded;
- the exposed Wi-Fi password is changed and authorized clients are reconnected;
- the current tree contains placeholders only;
- a repository and Git-history secret scan has run;
- any decision to rewrite published history has separate owner approval and a
  collaborator-coordination plan.

History rewriting is not required to revoke a secret and must not delay rotation.
It is destructive to commit identities and clones, so it is outside this checklist.
