"""Live simulation API checks; require the Compose stack, never real hardware."""

import asyncio
import os
import time

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("GRIDEYE_INTEGRATION") != "1", reason="requires compose stack"
)


async def wait_landed(client, mission_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snapshot = (await client.get("/api/v1/simulation")).json()
        if snapshot["mission"]["id"] == mission_id and snapshot["mission_state"] == "LANDED":
            return snapshot
        await asyncio.sleep(0.1)
    pytest.fail("mission did not land")


@pytest.mark.integration
async def test_plan_executes_and_can_restart():
    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=10) as client:
        snapshot = (await client.get("/api/v1/simulation")).json()
        assert snapshot["mode"] == "SIMULATION"
        assert not snapshot["mission"]["active"], "simulation must be idle before this test"
        plan = {
            "name": "TEST – API-Missionsprüfung",
            "start": {"x": -0.1, "y": 0.1},
            "waypoints": [{"x": 0.3, "y": 0.3}],
            "end": {"x": 0.5, "y": 0.3},
            "hover_time": 0.2,
            "altitude": 0.1,
            "speed": 1,
            "snap": "center",
        }
        created = await client.post("/api/v1/missions", json=plan)
        created.raise_for_status()
        mission_id = created.json()["id"]
        try:
            for _ in range(2):
                response = await client.post(f"/api/v1/missions/{mission_id}/start")
                response.raise_for_status()
                landed = await wait_landed(client, mission_id)
                assert landed["mission"]["status"] == "completed"
                assert landed["position"]["z"] == 0
            saved = (await client.get(f"/api/v1/missions/{mission_id}")).json()
            assert saved["plan"] == plan
            invalid = {**plan, "waypoints": [{"x": -0.1, "y": 0.1}]}
            assert (
                await client.put(f"/api/v1/missions/{mission_id}", json=invalid)
            ).status_code == 422
            assert (await client.get(f"/api/v1/missions/{mission_id}")).json()["plan"] == plan
        finally:
            status = (await client.get("/api/v1/simulation")).json()
            if status["mission"]["id"] == mission_id and status["mission"]["active"]:
                await client.post(f"/api/v1/missions/{mission_id}/abort")
                await wait_landed(client, mission_id)
            deleted = await client.delete(f"/api/v1/missions/{mission_id}")
            assert deleted.status_code == 204
            assert (await client.get(f"/api/v1/missions/{mission_id}")).json()["plan"] is None
