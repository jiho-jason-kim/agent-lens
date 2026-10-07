"""Verify world rules and the boundary between global and local data."""

from dataclasses import FrozenInstanceError, asdict

import pytest

from app.environment.grid_world import GridWorld


@pytest.mark.parametrize("direction,expected", [
    ("north", (3, 2)), ("south", (3, 4)),
    ("east", (4, 3)), ("west", (2, 3)),
])
def test_movement(direction, expected):
    world = GridWorld(start=(3, 3))
    assert world.move(direction).success
    assert world.snapshot().position == expected
    assert world.snapshot().turn == 1


@pytest.mark.parametrize("start,direction", [
    ((0, 0), "north"), ((0, 0), "west"),
    ((7, 7), "south"), ((7, 7), "east"),
    ((3, 3), "up"), ((3, 3), None), ((3, 3), []),
])
def test_invalid_movement_preserves_world_except_turn(start, direction):
    world = GridWorld(start=start)
    before = asdict(world.snapshot())
    assert not world.move(direction).success
    before["turn"] = 1
    assert asdict(world.snapshot()) == before


def test_collect_removes_one_resource_and_prevents_duplicate_collection():
    world = GridWorld(resources=((0, 0), (4, 4)))
    assert world.collect().success
    assert world.snapshot().inventory == 1
    assert world.snapshot().resources == ((4, 4),)
    assert not world.collect().success
    assert world.snapshot().inventory == 1
    assert world.snapshot().turn == 2


def test_collect_empty_cell():
    world = GridWorld(resources=())
    assert not world.collect().success
    assert world.snapshot().inventory == 0


def test_wait_only_advances_turn():
    world = GridWorld()
    before = asdict(world.snapshot())
    assert world.wait().success
    before["turn"] = 1
    assert asdict(world.snapshot()) == before


@pytest.mark.parametrize("start,count", [((3, 3), 13), ((0, 0), 6), ((7, 7), 6)])
def test_observation_uses_manhattan_radius_two(start, count):
    observation = GridWorld(start=start).observe()
    expected = {
        (x, y) for x in range(8) for y in range(8)
        if abs(x - start[0]) + abs(y - start[1]) <= 2
    }
    assert {cell.position for cell in observation.cells} == expected
    assert len(observation.cells) == count


def test_hidden_world_changes_cannot_be_detected_in_observation():
    # Both worlds have identical local cells but different hidden resources and homes.
    first = GridWorld(resources=((3, 4), (7, 7)), home=(0, 0), start=(3, 3))
    second = GridWorld(resources=((3, 4), (0, 7)), home=(7, 0), start=(3, 3))
    assert first.snapshot() != second.snapshot()
    assert first.observe() == second.observe()
    assert not hasattr(first.observe(), "resources")
    assert not hasattr(first.observe(), "home")


def test_visible_resource_and_home_flags():
    observation = GridWorld(resources=((2, 0), (3, 0))).observe()
    cells = {cell.position: cell for cell in observation.cells}
    assert cells[(0, 0)].home
    assert cells[(2, 0)].resource
    assert (3, 0) not in cells


def test_observations_and_snapshots_are_immutable_copies():
    world = GridWorld(resources=((0, 0),))
    observation, state = world.observe(), world.snapshot()
    with pytest.raises(FrozenInstanceError):
        observation.inventory = 99
    with pytest.raises(FrozenInstanceError):
        observation.cells[0].resource = False
    world.collect()
    assert observation.inventory == state.inventory == 0
    assert state.resources == ((0, 0),)
    assert observation.cells[0].resource


def test_goal_requires_three_resources_and_return_home():
    world = GridWorld(resources=((1, 0), (2, 0), (3, 0)))
    for _ in range(3):
        world.move("east")
        world.collect()
        assert not world.goal_complete
    for _ in range(3):
        world.move("west")
    assert world.goal_complete
    assert world.observe().goal_complete
    assert world.snapshot().goal_complete


def test_home_without_three_resources_is_incomplete():
    assert not GridWorld().goal_complete


@pytest.mark.parametrize("kwargs", [
    {"home": (-1, 0)}, {"start": (8, 0)}, {"resources": ((0, 8),)},
    {"resources": ((1, 1), (1, 1))}, {"start": (True, 0)},
    {"start": (1.5, 0)}, {"home": [0, 0]},
])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        GridWorld(**kwargs)
