# M1-01 canonical package evidence

**Date:** 2026-08-26
**Environment:** E1, WSL2 x86_64 and aarch64 dependency-resolution target
**Status:** DONE

## Delivered

- `pyproject.toml` with Python `3.12.*`, exact direct dependency versions, a
  PEP 517 wheel build, and the `dsctl` entry point;
- universal hash-bearing `uv.lock`;
- canonical `src/digital_spotter/` package and target component skeleton;
- versioned TOML plus explicit environment override loader;
- development, test, and production profiles;
- production validation that rejects missing provisioned identity/model/TLS files,
  simulated/replay hardware, relative mutable paths, unsigned-model policy,
  wildcard/non-HTTPS origins, unknown configuration keys, and unsafe identifiers;
- safe configuration summary that exposes state rather than secret/key contents;
- `config.example.toml` containing no secrets;
- unit tests under the new `tests/unit/` layout.

The prototype remains in place and continues to use its migration requirements and
launcher until its behavior is moved behind the new package contracts.

## Commands and results

```text
UV_CACHE_DIR=/tmp/digital-spotter-uv-cache uv lock --python 3.12
Resolved 11 packages

UV_CACHE_DIR=/tmp/digital-spotter-uv-cache uv sync --frozen
Built and installed digital-spotter-edge 0.1.0 as editable

.venv/bin/python -m pytest tests/unit -q
7 passed

UV_CACHE_DIR=/tmp/digital-spotter-uv-cache uv lock --check
lock current
```

The core runtime requirements were exported without the project/dev group and
resolved with binary wheels for `CPython 3.12` on
`aarch64-manylinux_2_28`. The plan contained five compatible packages, including
the aarch64 `msgpack` and `pydantic-core` wheels; nothing was installed by that dry
run.

A wheel was then built and installed into a new temporary Python 3.12 environment
that did not contain the repository's test/runtime environment:

```text
digital_spotter_edge-0.1.0-py3-none-any.whl built
six runtime packages installed into fresh environment
import/version/config assertion passed: 0.1.0
installed dsctl config check passed
```

No package or test mutates `sys.path`. The package is imported through editable or
wheel installation.

## Security and limitations

- Private-key contents are never parsed or printed by the configuration layer; M1-03
  adds signed model-manifest validation.
- The lock covers the new canonical core package. Heavy legacy vision/Flex runtime
  dependencies remain in the migration requirements until M3/M5 select and measure
  their product replacements.
- A dependency resolution is not a real Pi runtime pass. Pi installation/import is
  still required before a product release.
- Configuration validation is a foundation, not local API authorization or TLS
  provisioning; those remain M6 work.

## Rollback

The package is additive. Remove the new package files and continue using the
documented prototype launcher; no database, service, firmware, or user data changed.
