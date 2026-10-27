# M1-04 deterministic replay evidence

**Date:** 2026-08-26
**Environment:** E1 synthetic test environment
**Status:** DONE for deterministic contract replay

## Delivered

- a versioned, bounded JSON fixture schema with synthetic-only provenance and an
  explicit no-person-data consent state;
- a three-frame, 4-by-4 monochrome YUV4MPEG stream made entirely from synthetic
  byte values, hash-bound to its fixture and assigned exact monotonic capture times;
- aligned synthetic IMU, pose landmark, rep-phase/completion, and expected-analysis
  envelopes using the M1-02 contracts;
- exact length-prefixed MessagePack event-stream digests, expected phase sequence,
  analysis labels, gap count, and clock-reset count;
- a no-sleep replay clock and adapter permanently reporting `mode=replay`,
  `is_real=false`, `is_simulated=true`, and `persistence_allowed=false`;
- committed normal, same-boot sequence-gap, new-boot clock-reset, and corrupt event
  fixtures;
- failure checks for contradictory gap claims, implicit reboot state, duplicate
  event IDs, backward time, expectation tampering, path traversal, missing media,
  and media hash mismatch.

The visual fixture is deliberately abstract and is sufficient to exercise media
identity, synchronization metadata, and replay security. It does not replace a
consented person-in-frame golden dataset or demonstrate pose/model accuracy.

## Acceptance evidence

```text
.venv/bin/python -m pytest tests/unit tests/contract tests/replay -q
41 passed in 2.70s
```

Repeated normal replays produce the exact digest:

```text
90620503de89823e0e63822fa82bb530910817ddd1680c22f0a68ab72c55a046
```

The loss fixture reports exactly two missing packets. The reboot fixture reports
exactly one clock reset. The corrupt fixture is rejected before any event can be
used. No fixture can be surfaced as real or used to authorize durable product data.

## Limitations carried forward

- No consented person video or real lower-back MPU6050 capture exists yet.
- The compatibility model is not invoked by this replay adapter because M1-03 found
  unresolved sensor-unit/provenance/readiness blockers.
- Golden live inference/parity evidence belongs to the gated M3/M4 hardware work.

## Rollback

The replay package, tests, and fixtures are additive. Removing them restores the
prior package without changing prototype runtime behavior, model bytes, or real
device data.
