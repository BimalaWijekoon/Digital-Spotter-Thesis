# M1-02 event and time contract evidence

**Date:** 2026-08-26
**Environment:** E0/E1
**Status:** DONE

## Delivered

- v1 common event envelope with UUIDv7 event identity, source, device/session/trace
  correlation, quality, capture/create times, and typed payload;
- bounded `IMUSample`, `PoseSample`, `FusedSample`, `RepEvent`, `AnalysisEvent`, and
  component `HealthState` models;
- stable event/source/quality/reason/clock/rep/health enums;
- statically distinct `MonotonicNanoseconds` and `UtcMilliseconds` types plus
  injectable clock protocols;
- RFC 9562 UUIDv7 generation with injectable time/random bits for deterministic
  tests;
- MessagePack round-trip codec with a 64 KiB serialized limit, bounded maps/arrays/
  strings/binary fields, strict map keys, and classified decode errors;
- cross-field checks for event-type/payload agreement, envelope/payload quality and
  capture agreement, monotonic ordering, rep phase semantics, numeric finiteness,
  identifier/range/list/map bounds, and exact schema version.

Camera frames do not enter this envelope. The models are frozen and reject unknown
fields so parsed data cannot be mutated or silently widened inside the process.

## Acceptance evidence

```text
.venv/bin/python -m pytest tests/unit tests/contract -q
20 passed in 1.35s
```

The contract suite covers round trips for all six payload kinds, malformed and
oversized input, wrong schema, non-UUIDv7 event IDs, event/payload mismatch,
quality/timestamp mismatch, NaN vectors, inverted clocks, phase invariants, and
deterministic UUID generation. It also checks that the monotonic and UTC clock
protocols expose different `NewType` return types.

## Limitations and next consumers

- Only schema `0x0100` is accepted. A compatible minor-version policy will be added
  when a real second implementation needs it; the current decoder does not guess.
- UDS framing/peer credentials and backpressure are M2/M3 integration work.
- The exact ESP BLE 20-byte packet is a separate firmware/wire contract in M2; an
  `IMUSample` is the validated, scaled Pi-domain event after parsing and clock map.
- Model-manifest and database/outbox contracts are M1-03/M1-05.

## Rollback

The contracts are additive and have no live consumers yet. Removing the modules
does not alter the prototype, database, Pi, or firmware.
