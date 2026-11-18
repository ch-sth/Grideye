import io
import json

import httpx
import pytest

from services.ai import model_store
from services.ai.model_store import ModelImportError, ModelStore
from services.backend.main import app
from services.camera.live import LiveCamera


class FakeDetector:
    names = {"0": "package"}

    def __init__(self, path):
        if path.read_bytes() != b"valid checkpoint":
            raise ValueError("invalid checkpoint")

    async def detect(self, frame):
        return []


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(model_store, "YoloDetector", FakeDetector)
    return ModelStore(tmp_path / "models")


def test_import_copies_activates_and_restores_on_restart(store, tmp_path):
    source = tmp_path / "best.pt"
    source.write_bytes(b"valid checkpoint")
    snapshot = store.import_path(str(source))
    model_id = snapshot["active_id"]
    entry = snapshot["models"][0]
    assert entry["name"] == "best.pt"
    assert entry["classes"] == {"0": "package"}
    assert source.read_bytes() == b"valid checkpoint"
    assert (store.directory / f"{model_id}.pt").read_bytes() == source.read_bytes()
    assert ModelStore(store.directory).snapshot()["active_id"] == model_id
    store.activate("aruco")
    assert ModelStore(store.directory).snapshot()["active_id"] == "aruco"
    store.activate(model_id)
    assert store.selection()[0] == model_id


def test_failed_import_leaves_previous_selection_unchanged(store):
    before = store.import_stream(io.BytesIO(b"valid checkpoint"), "original.pt")
    for name, content in [("bad.pt", b"corrupt"), ("empty.pt", b""), ("wrong.onnx", b"anything")]:
        with pytest.raises(ModelImportError):
            store.import_stream(io.BytesIO(content), name)
        assert store.snapshot() == before
    assert len(list(store.directory.glob("*.pt"))) == 1


def test_failed_manifest_write_rolls_back_new_model(store, monkeypatch):
    previous = store.import_stream(io.BytesIO(b"valid checkpoint"), "first.pt")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(model_store.os, "replace", fail)
    with pytest.raises(OSError):
        store.import_stream(io.BytesIO(b"valid checkpoint"), "second.pt")
    assert store.snapshot() == previous
    assert len(list(store.directory.glob("*.pt"))) == 1
    assert not list(store.directory.glob("*.tmp"))


def test_modified_model_cannot_be_activated(store):
    snapshot = store.import_stream(io.BytesIO(b"valid checkpoint"), "best.pt")
    model_id = snapshot["active_id"]
    store.activate("aruco")
    (store.directory / f"{model_id}.pt").write_bytes(b"changed")
    with pytest.raises(ModelImportError, match="verändert"):
        store.activate(model_id)
    assert store.snapshot()["active_id"] == "aruco"


def test_unloadable_saved_model_falls_back_to_aruco(store):
    snapshot = store.import_stream(io.BytesIO(b"valid checkpoint"), "best.pt")
    (store.directory / f"{snapshot['active_id']}.pt").unlink()
    recovered = ModelStore(store.directory).snapshot()
    assert recovered["active_id"] == "aruco"
    assert recovered["saved_active_id"] == snapshot["active_id"]
    assert recovered["error"]


def test_rejects_invalid_import_paths(store, tmp_path):
    for path in [tmp_path / "missing.pt", tmp_path / "wrong.onnx"]:
        with pytest.raises(ModelImportError):
            store.import_path(str(path))
    directory = tmp_path / "directory.pt"
    directory.mkdir()
    with pytest.raises(ModelImportError):
        store.import_path(str(directory))
    with pytest.raises(ModelImportError):
        store.activate("../../other")


def test_size_limit_and_cleanup(store, monkeypatch):
    monkeypatch.setattr(model_store, "MAX_MODEL_BYTES", 8)
    with pytest.raises(ModelImportError, match="512"):
        store.import_stream(io.BytesIO(b"x" * 9), "oversize.pt")
    assert store.snapshot()["models"] == []
    assert not list(store.directory.glob("*.pt"))


async def test_model_import_upload_and_activation_endpoints(store, monkeypatch, tmp_path):
    monkeypatch.setattr(app.state, "model_store", store, raising=False)
    camera = LiveCamera()
    monkeypatch.setattr(app.state, "camera", camera, raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        source = tmp_path / "best.pt"
        source.write_bytes(b"valid checkpoint")
        response = await api.post("/api/v1/ai/models/import", json={"path": str(source)})
        assert response.status_code == 200
        first = response.json()["active_id"]
        response = await api.post(
            "/api/v1/ai/models/upload?filename=pc.pt", content=b"valid checkpoint"
        )
        assert response.status_code == 200
        assert response.json()["models"][-1]["name"] == "pc.pt"
        second = response.json()["active_id"]
        assert second != first
        for invalid in [b"bad", b""]:
            response = await api.post("/api/v1/ai/models/upload?filename=bad.pt", content=invalid)
            assert response.status_code == 422
        assert (await api.get("/api/v1/ai/models")).json()["active_id"] == second
        response = await api.post("/api/v1/ai/models/activate", json={"model_id": first})
        assert response.status_code == 200
        assert response.json()["active_id"] == first
        response = await api.post("/api/v1/ai/models/activate", json={"model_id": "aruco"})
        assert response.json()["active_id"] == "aruco"
        response = await api.post("/api/v1/ai/models/upload?filename=bad.onnx", content=b"test")
        assert response.status_code == 422
        response = await api.get("/api/v1/ai/result")
        assert response.json()["status"] == "waiting"
        assert response.json()["detections"] == []
        assert 'id="model-path-form"' in (await api.get("/services/models")).text
    registry = json.loads((store.directory / "registry.json").read_text())
    assert registry["active_id"] == "aruco"
