"""Typed failures shared by real vision adapters and the worker."""

from __future__ import annotations

from digital_spotter.contracts import ReasonCode


class VisionAdapterError(RuntimeError):
    """A real vision adapter failed with a machine-readable reason."""

    reason_code = ReasonCode.INTERNAL_ERROR


class CameraUnavailableError(VisionAdapterError):
    """The configured camera/helper cannot currently provide frames."""

    reason_code = ReasonCode.CAMERA_UNAVAILABLE


class CameraProtocolError(VisionAdapterError):
    """The local camera helper violated its bounded frame protocol."""

    reason_code = ReasonCode.PROTOCOL_MISMATCH


class PoseUnavailableError(VisionAdapterError):
    """The configured real pose runtime cannot be initialized."""

    reason_code = ReasonCode.MODEL_UNAVAILABLE


class PoseProcessingError(VisionAdapterError):
    """The real pose runtime failed while evaluating a camera frame."""

    reason_code = ReasonCode.INTERNAL_ERROR
