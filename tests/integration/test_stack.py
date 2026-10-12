"""Black-box integration checks. Run with GRIDEYE_INTEGRATION=1 after compose up."""

import asyncio
import json
import os
from uuid import uuid4

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("GRIDEYE_INTEGRATION") != "1", reason="requires compose stack"
)


@pytest.mark.integration
async def test_uwb_reaches_backend() -> None:
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        for _ in range(30):
            response = await client.get("/api/v1/drone/position")
            if response.json().get("position"):
                return
            await asyncio.sleep(0.5)
    pytest.fail("no UWB position reached backend")


@pytest.mark.integration
async def test_confirmed_detection_is_persisted() -> None:
    import paho.mqtt.publish as publish

    detection_id = str(uuid4())
    payload = {
        "schema_version": "1.0",
        "detection_id": detection_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "class_name": "package",
        "number": "4712",
        "world": {"x_m": 1, "y_m": 2},
        "grid": {"cell": "C2", "column": 2, "row": 1},
        "confidence": 0.9,
        "mission_id": None,
        "image_reference": None,
    }
    publish.single("grideye/detection/confirmed", json.dumps(payload), hostname="localhost", qos=1)
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        for _ in range(20):
            if (await client.get(f"/api/v1/detections/{detection_id}")).status_code == 200:
                return
            await asyncio.sleep(0.5)
    pytest.fail("confirmed detection was not persisted")


@pytest.mark.integration
async def test_websocket_receives_live_event() -> None:
    import websockets

    async with websockets.connect("ws://localhost:8000/ws/live") as socket:
        event = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
        assert event["type"] in {
            "simulation.telemetry",
            "uwb.position",
            "flight.attitude",
            "flight.battery",
            "flight.mode",
            "service.status",
        }
