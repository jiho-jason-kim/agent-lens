"""Verify all endpoints, saved replay, and HTTP error responses."""

import pytest
from fastapi.testclient import TestClient

from app.agent.mock_agent import MockAgent
from app.environment.grid_world import GridWorld
from app.main import create_app
from app.storage.json_store import RunStore


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(RunStore(tmp_path))) as client:
        yield client


def test_all_five_endpoints(client, tmp_path):
    assert client.get("/runs").json() == []
    response = client.post("/runs")
    assert response.status_code == 201
    metadata = response.json()
    assert metadata["status"] == "goal_complete"
    run_id = metadata["run_id"]
    assert response.headers["location"] == f"/runs/{run_id}"
    assert client.get("/runs").json() == [metadata]
    detail = client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    recording = detail.json()
    assert recording["metadata"] == metadata
    for part in ("events", "states"):
        result = client.get(f"/runs/{run_id}/{part}")
        assert result.status_code == 200
        assert result.json() == recording[part]
    assert recording == RunStore(tmp_path).load(run_id).model_dump(mode="json")
    assert len(recording["states"]) == metadata["turns"] + 1


def test_configured_turn_limit_and_list_order(client):
    first = client.post("/runs", json={"agent": "mock", "max_turns": 1}).json()
    second = client.post("/runs", json={}).json()
    assert first["status"] == "turn_limit"
    assert first["turns"] == 1
    assert first["run_id"] != second["run_id"]
    assert client.get("/runs").json() == [second, first]


@pytest.mark.parametrize("payload", [
    {"agent": "unknown"}, {"max_turns": 0}, {"max_turns": 51},
    {"max_turns": True}, {"max_turns": 2.5}, {"max_turns": "2"},
    {"position": [7, 7]}, {"max_turns": None},
])
def test_invalid_requests_do_not_create_recordings(client, payload):
    assert client.post("/runs", json=payload).status_code == 422
    assert client.get("/runs").json() == []


@pytest.mark.parametrize("suffix", ["", "/events", "/states"])
def test_missing_and_invalid_run_ids(client, suffix):
    assert client.get(f"/runs/run-missing{suffix}").status_code == 404
    assert client.get(f"/runs/invalid_id{suffix}").status_code == 422


def test_reads_never_execute_simulation_and_survive_app_restart(client, tmp_path, monkeypatch):
    run_id = client.post("/runs").json()["run_id"]

    def forbidden(*args, **kwargs):
        pytest.fail("A read endpoint executed simulation code.")

    monkeypatch.setattr(MockAgent, "decide", forbidden)
    monkeypatch.setattr(GridWorld, "__init__", forbidden)
    with TestClient(create_app(RunStore(tmp_path))) as restarted:
        for path in ("/runs", f"/runs/{run_id}", f"/runs/{run_id}/events", f"/runs/{run_id}/states"):
            assert restarted.get(path).status_code == 200


@pytest.mark.parametrize("damage", ["malformed", "missing", "wrong_id"])
def test_corrupt_recordings_return_controlled_error(client, tmp_path, damage):
    run_id = client.post("/runs").json()["run_id"]
    directory = tmp_path / run_id
    if damage == "malformed":
        (directory / "events.json").write_text("broken-json", encoding="utf-8")
    elif damage == "missing":
        (directory / "states.json").unlink()
    else:
        metadata = directory / "metadata.json"
        metadata.write_text(metadata.read_text().replace(run_id, "run-different"), encoding="utf-8")
    for path in ("/runs", f"/runs/{run_id}", f"/runs/{run_id}/events", f"/runs/{run_id}/states"):
        response = client.get(path)
        assert response.status_code == 500
        assert str(tmp_path) not in response.text


def test_storage_failure_returns_controlled_error(client, monkeypatch):
    def cannot_save(*args):
        raise PermissionError("private filesystem path")

    monkeypatch.setattr(client.app.state.run_store, "save", cannot_save)
    response = client.post("/runs")
    assert response.status_code == 500
    assert response.json() == {"detail": "Run could not be saved."}


def test_list_ignores_unpublished_directories(client, tmp_path):
    (tmp_path / ".pending-example").mkdir()
    assert client.get("/runs").json() == []


def test_openapi_describes_all_endpoints(client):
    schema = client.get("/openapi.json").json()
    assert set(schema["paths"]["/runs"]) == {"get", "post"}
    for suffix in ("", "/events", "/states"):
        assert "get" in schema["paths"][f"/runs/{{run_id}}{suffix}"]
