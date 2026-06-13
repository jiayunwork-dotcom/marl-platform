import json
from app.core.environment import EMPTY, OBSTACLE, RESOURCE, SPAWN, TARGET
from app.schemas.schemas import MapConfig, CellConfig


def create_cooperative_navigation(map_size: int = 10, agent_count: int = 4, team_config: dict = None) -> dict:
    cells = []
    mid = map_size // 2
    for i in range(3):
        for j in range(3):
            if i == 1 and j == 1:
                continue
            cells.append({"x": mid - 1 + j, "y": mid - 1 + i, "type": "obstacle"})

    corners = [
        (1, 1), (1, map_size - 2),
        (map_size - 2, 1), (map_size - 2, map_size - 2),
        (1, map_size // 2), (map_size // 2, 1),
        (map_size - 2, map_size // 2), (map_size // 2, map_size - 2),
    ]
    opposite_corners = [
        (map_size - 2, map_size - 2), (map_size - 2, 1),
        (1, map_size - 2), (1, 1),
        (map_size - 2, map_size // 2), (map_size // 2, map_size - 2),
        (1, map_size // 2), (map_size // 2, 1),
    ]

    teams = team_config or {}
    for i in range(agent_count):
        sy, sx = corners[i % len(corners)]
        cells.append({"x": sx, "y": sy, "type": "spawn", "team": teams.get(str(i), 0)})
        ty, tx = opposite_corners[i % len(opposite_corners)]
        cells.append({"x": tx, "y": ty, "type": "target"})

    return {
        "width": map_size, "height": map_size, "cells": cells,
    }


def create_resource_competition(map_size: int = 10, agent_count: int = 4, team_config: dict = None) -> dict:
    cells = []
    mid = map_size // 2

    num_resources = max(2, agent_count // 2)
    for i in range(num_resources):
        angle = 2 * 3.14159 * i / num_resources
        rx = int(mid + (mid - 2) * 0.5 * __import__("math").cos(angle))
        ry = int(mid + (mid - 2) * 0.5 * __import__("math").sin(angle))
        rx = max(0, min(map_size - 1, rx))
        ry = max(0, min(map_size - 1, ry))
        cells.append({"x": rx, "y": ry, "type": "resource"})

    for i in range(3):
        cells.append({"x": mid, "y": mid - 1 + i, "type": "obstacle"})

    teams = team_config or {}
    for i in range(agent_count):
        side = i % 4
        if side == 0:
            sx, sy = 1, 1
        elif side == 1:
            sx, sy = map_size - 2, 1
        elif side == 2:
            sx, sy = 1, map_size - 2
        else:
            sx, sy = map_size - 2, map_size - 2
        cells.append({"x": sx, "y": sy, "type": "spawn", "team": teams.get(str(i), i % 2)})

    return {
        "width": map_size, "height": map_size, "cells": cells,
    }


def create_predator_prey(map_size: int = 10, agent_count: int = 4, team_config: dict = None) -> dict:
    cells = []
    mid = map_size // 2

    for wall_y in range(2, map_size - 2):
        if wall_y != mid:
            cells.append({"x": mid, "y": wall_y, "type": "obstacle"})
    for wall_x in range(2, map_size - 2):
        if wall_x != mid:
            cells.append({"x": wall_x, "y": mid, "type": "obstacle"})

    cells.append({"x": mid, "y": mid, "type": "spawn", "team": 0})

    teams = team_config or {"0": 0}
    num_prey = 1
    num_predators = agent_count - num_prey

    for i in range(num_predators):
        side = i % 4
        if side == 0:
            sx, sy = 1, 1
        elif side == 1:
            sx, sy = map_size - 2, 1
        elif side == 2:
            sx, sy = 1, map_size - 2
        else:
            sx, sy = map_size - 2, map_size - 2
        cells.append({"x": sx, "y": sy, "type": "spawn", "team": teams.get(str(num_prey + i), 1)})

    return {
        "width": map_size, "height": map_size, "cells": cells,
    }


PRESET_GENERATORS = {
    "cooperative_navigation": create_cooperative_navigation,
    "resource_competition": create_resource_competition,
    "predator_prey": create_predator_prey,
}
