"""Ordered product database migrations."""

from digital_spotter.persistence.migrations.v0001_core import MIGRATION as V0001
from digital_spotter.persistence.migrations.v0002_outbox import MIGRATION as V0002
from digital_spotter.persistence.migrations.v0003_session_runtime import (
    MIGRATION as V0003,
)


MIGRATIONS = (V0001, V0002, V0003)

__all__ = ["MIGRATIONS"]
