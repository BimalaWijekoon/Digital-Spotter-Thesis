"""Fail-closed startup gates shared by future core service entry points."""

from __future__ import annotations

from digital_spotter.config import ProductSettings, RuntimeProfile
from digital_spotter.contracts.model import ModelManifest, validate_model_package


class StartupValidationError(RuntimeError):
    """Raised before service readiness when a mandatory product gate fails."""


def require_model_package(settings: ProductSettings) -> ModelManifest:
    """Validate every manifested artifact and enforce profile readiness.

    Development/test may use the explicitly compatibility-only package for parity.
    Production requires the stronger signed/evaluated/operator-safe state from the
    same validator and therefore rejects the current package.
    """
    if settings.model_manifest_path is None:
        raise StartupValidationError("model manifest is not configured")
    production = settings.profile is RuntimeProfile.PRODUCTION
    result = validate_model_package(settings.model_manifest_path, production=production)
    ready = result.production_ready if production else result.compatibility_ready
    if not ready or result.manifest is None:
        reasons = result.errors or ("model package is not ready for this profile",)
        raise StartupValidationError("; ".join(reasons))
    return result.manifest
