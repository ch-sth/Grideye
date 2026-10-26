from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copytree

import httpx
import pytest

from grideye_shared.config import files
from grideye_shared.schemas import ServiceState, ServiceStatus
from services.backend.main import app
from services.backend.state import RuntimeState


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    directory = tmp_path / "config"
    copytree(files.CONFIG_DIR, directory)
    monkeypatch.setattr(files, "CONFIG_DIR", directory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api


async def test_dashboard_deep_link(client):
    response = await client.get("/services/tracking")
    assert response.status_code == 200
    assert 'id="settings-form"' in response.text


async def test_dashboard_root_redirect(client):
    response = await client.get("/")
    assert response.status_code == 307
    assert response.headers["location"] == "/?ansicht=neu"
    response = await client.get("/", follow_redirects=True)
    assert response.status_code == 200
    assert response.url.query == b"ansicht=neu"
    assert "Flugfeld & Missionspfad" in response.text
    assert "no-store" in response.headers["cache-control"]


async def test_config_validation_and_persistence(client):
    original = (await client.get("/api/v1/config")).json()["grid"]
    original_mode = (files.CONFIG_DIR / "grid.yaml").stat().st_mode
    changed = {**original, "rows": 10}
    response = await client.put("/api/v1/config/grid", json=changed)
    assert response.status_code == 200
    assert (await client.get("/api/v1/grid")).json()["rows"] == 10
    assert files.read_config("grid")["rows"] == 10
    assert (files.CONFIG_DIR / "grid.yaml").stat().st_mode == original_mode
    for invalid in [{**changed, "rows": 0}, {**changed, "unknown": 2}]:
        assert (await client.put("/api/v1/config/grid", json=invalid)).status_code == 422
        assert files.read_config("grid")["rows"] == 10
    assert not list(files.CONFIG_DIR.glob("*.tmp"))
    assert (await client.put("/api/v1/config/../secret", json={})).status_code == 404
    assert (await client.put("/api/v1/config/unknown", json={})).status_code == 404


async def test_saved_service_settings(client):
    response = await client.put("/api/v1/config/tracking", json={"proximity_m": 0.8})
    assert response.json()["restart_required"] is True
    assert files.read_config("tracking")["proximity_m"] == 0.8


def test_expired_heartbeat_does_not_modify_source():
    state = RuntimeState()
    state.services["tracking"] = ServiceStatus(
        service="tracking",
        status=ServiceState.ONLINE,
        timestamp=datetime.now(UTC) - timedelta(seconds=20),
    )
    assert state.service_snapshot(15)[0]["status"] == "offline"
    assert state.services["tracking"].status == ServiceState.ONLINE


async def test_simulation_api_and_configuration_guard(client, monkeypatch):
    from services.backend.mission_api import configure_manager
    from services.mission.models import MissionPlan, Point

    manager = configure_manager()
    monkeypatch.setattr(app.state, "mission_manager", manager, raising=False)
    response = await client.post("/missions/snap", json={})
    assert response.status_code == 404
    response = await client.post(
        "/api/v1/missions/snap",
        json={
            "point": {"x": 0.31, "y": 0.31},
            "mode": "center",
        },
    )
    assert response.status_code == 200
    assert response.json()["x"] == pytest.approx(0.3)
    assert (
        await client.post(
            "/api/v1/missions/snap",
            json={
                "point": {"x": -0.1, "y": 0.31},
                "mode": "free",
            },
        )
    ).status_code == 422
    plan = MissionPlan(
        name="Guard",
        start=Point(x=0.1, y=0.1),
        waypoints=[Point(x=0.3, y=0.3)],
        end=Point(x=0.1, y=0.1),
    )
    manager.start("unit", plan)
    before = files.read_config("safety")
    assert (await client.put("/api/v1/config/safety", json=before)).status_code == 409
    response = await client.post("/api/v1/simulation/input", json={"quality": 0.1})
    assert response.status_code == 200
    for _ in range(3):
        manager.tick(0.1)
    assert (await client.get("/api/v1/simulation")).json()["failsafe"] is True
    assert (await client.post("/api/v1/simulation/reset")).status_code == 409
    await client.post("/api/v1/simulation/input", json={"quality": 0.96})
    for _ in range(10):
        manager.tick(0.1)
    assert (await client.post("/api/v1/simulation/reset")).status_code == 200


async def test_camera_config_switch_and_preview_api(client, monkeypatch):
    from services.camera.live import LiveCamera

    camera = LiveCamera()
    monkeypatch.setattr(app.state, "camera", camera, raising=False)
    config = (await client.get("/api/v1/config")).json()["camera"]
    config["stream"]["rtsp_url"] = "192.168.1.50:554/live"
    result = await client.put("/api/v1/config/camera", json=config)
    assert result.status_code == 200
    assert result.json()["restart_required"] is False
    assert files.read_config("camera")["stream"]["rtsp_url"] == "rtsp://192.168.1.50:554/live"
    assert (await client.get("/api/v1/camera/status")).json()["status"] == "starting"
    assert (await client.get("/api/v1/camera/frame.jpg")).status_code == 503
    revision = camera.status()["revision"]
    camera._publish(revision, "online", "Livebild", b"jpeg")
    response = await client.get("/api/v1/camera/frame.jpg")
    assert response.content == b"jpeg"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"
    config["stream"]["rtsp_url"] = "192.168.1.60/live"
    assert (await client.put("/api/v1/config/camera", json=config)).status_code == 200
    assert (await client.get("/api/v1/camera/frame.jpg")).status_code == 503
    config["stream"]["rtsp_url"] = "file:///etc/passwd"
    assert (await client.put("/api/v1/config/camera", json=config)).status_code == 422
    assert files.read_config("camera")["stream"]["rtsp_url"] == "rtsp://192.168.1.60/live"
    config["stream"]["rtsp_url"] = ""
    assert (await client.put("/api/v1/config/camera", json=config)).status_code == 200
    assert (await client.get("/api/v1/camera/status")).json()["configured"] is False


async def test_camera_page_contains_preview(client):
    response = await client.get("/services/camera")
    assert 'id="camera-preview"' in response.text
    assert 'id="camera-image"' in response.text
