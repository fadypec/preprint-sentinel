"""Tests for the FastAPI pipeline sidecar."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from pipeline.api import create_app


@pytest.fixture
def mock_scheduler():
    scheduler = MagicMock()
    scheduler.get_status.return_value = {
        "running": True,
        "paused": False,
        "next_run_time": "2026-04-01T06:00:00+00:00",
        "last_run_time": None,
        "last_run_stats": None,
    }
    scheduler.trigger_run = AsyncMock(return_value=MagicMock(
        papers_ingested=10,
        papers_adjudicated=2,
        errors=[],
    ))
    scheduler.pause = AsyncMock()
    scheduler.resume = AsyncMock()
    scheduler.update_schedule = AsyncMock()
    return scheduler


@pytest.fixture
def app(mock_scheduler):
    return create_app(scheduler=mock_scheduler, api_secret="test-secret")


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


HEADERS = {"Authorization": "Bearer test-secret"}


async def test_status_returns_scheduler_state(client, mock_scheduler):
    resp = await client.get("/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["running"] is True
    assert data["paused"] is False
    mock_scheduler.get_status.assert_called_once()


async def test_status_rejects_missing_auth(client):
    resp = await client.get("/status")
    assert resp.status_code == 401


async def test_status_rejects_wrong_secret(client):
    resp = await client.get("/status", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


async def test_run_triggers_pipeline(client, mock_scheduler):
    resp = await client.post("/run", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.trigger_run.assert_awaited_once()


async def test_pause_calls_scheduler(client, mock_scheduler):
    resp = await client.post("/pause", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.pause.assert_awaited_once()


async def test_resume_calls_scheduler(client, mock_scheduler):
    resp = await client.post("/resume", headers=HEADERS)
    assert resp.status_code == 200
    mock_scheduler.resume.assert_awaited_once()


async def test_update_schedule(client, mock_scheduler):
    resp = await client.put("/schedule", headers=HEADERS, json={"hour": 8, "minute": 30})
    assert resp.status_code == 200
    mock_scheduler.update_schedule.assert_awaited_once_with(8, 30)


async def test_update_schedule_validates_hour(client):
    resp = await client.put("/schedule", headers=HEADERS, json={"hour": 25})
    assert resp.status_code == 422
