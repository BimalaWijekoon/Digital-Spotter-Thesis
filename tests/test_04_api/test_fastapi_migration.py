"""Smoke tests for the active FastAPI migration application."""

import asyncio

import httpx

from scripts.dashboard.main import app


def test_fastapi_health_smoke():
    async def request_health():
        # The ASGI transport intentionally skips hardware-heavy lifespan startup.
        # Real startup is covered by a Pi service smoke; this E1 check verifies the
        # canonical FastAPI route without constructing MediaPipe in a test thread.
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    payload = response.json()
    assert payload["features"] == 40
    assert payload["sequence_length"] == 4
    assert "model_mock" in payload
    assert "imu_mock" in payload
