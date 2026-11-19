from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest

from services.backend import main
from services.backend.database import DetectionRow, TaggedObjectRow


@pytest.mark.parametrize("table", [DetectionRow, TaggedObjectRow, None])
async def test_delete_detection_removes_requested_row(monkeypatch, table):
    detection_id = uuid4()
    row = object() if table else None
    session = AsyncMock()
    session.get.side_effect = lambda model, key: (
        row if model is table and key == detection_id else None
    )
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(main, "SessionLocal", Mock(return_value=context))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://test"
    ) as client:
        response = await client.delete(f"/api/v1/detections/{detection_id}")
    if table is None:
        assert response.status_code == 404
        session.delete.assert_not_awaited()
        session.commit.assert_not_awaited()
    else:
        assert response.status_code == 204
        session.delete.assert_awaited_once_with(row)
        session.commit.assert_awaited_once()
