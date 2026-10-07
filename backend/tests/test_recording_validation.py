"""Reject damaged recordings before serving replay data."""

import json

import pytest
from pydantic import ValidationError

from app.agent.mock_agent import MockAgent
from app.simulation.runner import run_simulation
from app.storage.json_store import RunStore


@pytest.mark.parametrize("damage", ["payload", "duplicate", "input", "effect", "run_id", "snapshot", "count"])
def test_corrupt_recordings_are_rejected(tmp_path, damage):
    store = RunStore(tmp_path)
    run = run_simulation(MockAgent(), store=store)
    directory = tmp_path / run.metadata.run_id
    events = json.loads((directory / "events.json").read_text())
    states = json.loads((directory / "states.json").read_text())
    if damage == "payload":
        events[0]["payload"] = {}
    elif damage == "duplicate":
        events[1]["event_id"] = events[0]["event_id"]
    elif damage == "input":
        events[1]["input_refs"] = ["missing"]
    elif damage == "effect":
        events[0]["effect_refs"] = []
    elif damage == "run_id":
        events[0]["run_id"] = "run-other"
    elif damage == "snapshot":
        states[1]["turn"] = 9
    else:
        states.pop()
    (directory / "events.json").write_text(json.dumps(events))
    (directory / "states.json").write_text(json.dumps(states))
    with pytest.raises(ValidationError):
        store.load(run.metadata.run_id)
