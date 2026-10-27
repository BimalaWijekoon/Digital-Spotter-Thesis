from __future__ import annotations

import asyncio
import os

from digital_spotter.feedback import DemoCue
from digital_spotter.feedback.uds import UnixWearableCueClient, UnixWearableCueServer


def test_feedback_uds_round_trip_is_same_uid_and_bounded(tmp_path):
    async def scenario() -> None:
        observed: list[DemoCue] = []

        async def apply(cue: DemoCue) -> bytes:
            observed.append(cue)
            return b"ok:demo_" + (b"stop" if cue is DemoCue.COMPLETE else cue.value.encode())

        socket_path = tmp_path / "wearable-cues.sock"
        server = UnixWearableCueServer(
            socket_path=socket_path,
            on_cue=apply,
            allowed_uids=frozenset({os.getuid()}),
        )
        await server.start()
        client = UnixWearableCueClient(socket_path)

        await client.emit(DemoCue.START)
        await client.emit(DemoCue.BAD)
        await client.emit(DemoCue.COMPLETE)

        assert observed == [DemoCue.START, DemoCue.BAD, DemoCue.COMPLETE]
        assert socket_path.stat().st_mode & 0o777 == 0o600
        await client.close()
        await server.close()
        assert not socket_path.exists()

    asyncio.run(scenario())
