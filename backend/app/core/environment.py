import numpy as np
import json
from typing import Optional
from copy import deepcopy

EMPTY = 0
OBSTACLE = 1
RESOURCE = 2
SPAWN = 3
TARGET = 4

CELL_NAMES = {EMPTY: "empty", OBSTACLE: "obstacle", RESOURCE: "resource", SPAWN: "spawn", TARGET: "target"}

ACTION_UP = 0
ACTION_DOWN = 1
ACTION_LEFT = 2
ACTION_RIGHT = 3
ACTION_STAY = 4

DIRECTIONS = {
    ACTION_UP: (-1, 0),
    ACTION_DOWN: (1, 0),
    ACTION_LEFT: (0, -1),
    ACTION_RIGHT: (0, 1),
    ACTION_STAY: (0, 0),
}


class GridWorldEnv:
    def __init__(
        self,
        map_config: dict,
        max_steps: int = 100,
        obs_range: int = -1,
        action_space: int = 5,
        collision_rule: str = "both_stay",
        resource_refresh: str = "fixed_interval",
        resource_refresh_interval: int = 10,
        rewards: Optional[dict] = None,
        agent_count: int = 2,
        team_config: Optional[dict] = None,
    ):
        self.width = map_config["width"]
        self.height = map_config["height"]
        self.max_steps = max_steps
        self.obs_range = obs_range
        self.action_space = action_space
        self.collision_rule = collision_rule
        self.resource_refresh = resource_refresh
        self.resource_refresh_interval = resource_refresh_interval
        self.agent_count = agent_count
        self.team_config = team_config or {}

        default_rewards = {
            "goal": 10.0, "resource": 5.0, "collision": -2.0,
            "wall": -1.0, "step": -0.1, "catch_predator": 20.0,
            "catch_prey": -20.0, "timeout": -5.0,
        }
        self.rewards = {**default_rewards, **(rewards or {})}

        self.grid = np.zeros((self.height, self.width), dtype=np.int32)
        self.spawn_positions = []
        self.target_positions = []
        self.resource_positions = []
        self.agent_positions = []
        self.agent_teams = []
        self._parse_map_config(map_config)

        self.step_count = 0
        self.resource_timers = {}
        self.resource_collected = set()
        self.done = False
        self.episode_rewards = []
        self._init_agents()

    def _parse_map_config(self, map_config: dict):
        cells = map_config.get("cells", [])
        for cell in cells:
            x, y, cell_type = cell["x"], cell["y"], cell["type"]
            type_map = {"empty": EMPTY, "obstacle": OBSTACLE, "resource": RESOURCE, "spawn": SPAWN, "target": TARGET}
            self.grid[y][x] = type_map.get(cell_type, EMPTY)
            if cell_type == "spawn":
                self.spawn_positions.append((y, x))
                team = cell.get("team", 0)
                if len(self.spawn_positions) > len(self.agent_teams):
                    self.agent_teams.append(team)
            elif cell_type == "target":
                self.target_positions.append((y, x))
            elif cell_type == "resource":
                self.resource_positions.append((y, x))

    def _init_agents(self):
        self.agent_positions = list(self.spawn_positions[:self.agent_count])
        while len(self.agent_positions) < self.agent_count:
            self.agent_positions.append((0, 0))
        while len(self.agent_teams) < self.agent_count:
            self.agent_teams.append(0)

    def reset(self):
        self.agent_positions = list(self.spawn_positions[:self.agent_count])
        while len(self.agent_positions) < self.agent_count:
            self.agent_positions.append((0, 0))
        while len(self.agent_teams) < self.agent_count:
            self.agent_teams.append(0)
        self.step_count = 0
        self.resource_timers = {}
        self.resource_collected = set()
        self.done = False
        self.episode_rewards = [0.0] * self.agent_count
        for pos in self.resource_positions:
            self.grid[pos[0]][pos[1]] = RESOURCE
        return self._get_obs()

    def _get_obs(self):
        observations = []
        for i, pos in enumerate(self.agent_positions):
            if self.obs_range == -1:
                obs = self._global_obs(i)
            else:
                obs = self._local_obs(i, pos)
            observations.append(obs)
        return observations

    def _global_obs(self, agent_id: int) -> np.ndarray:
        obs = np.zeros((self.height, self.width, 4), dtype=np.float32)
        obs[:, :, 0] = (self.grid == OBSTACLE).astype(np.float32)
        obs[:, :, 1] = (self.grid == RESOURCE).astype(np.float32)
        obs[:, :, 2] = (self.grid == TARGET).astype(np.float32)
        for j, apos in enumerate(self.agent_positions):
            if j != agent_id:
                obs[apos[0], apos[1], 3] = 1.0
        return obs

    def _local_obs(self, agent_id: int, pos: tuple) -> np.ndarray:
        r = self.obs_range
        obs_size = 2 * r + 1
        obs = np.full((obs_size, obs_size, 4), -1.0, dtype=np.float32)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = pos[0] + dy, pos[1] + dx
                oy, ox = dy + r, dx + r
                if 0 <= ny < self.height and 0 <= nx < self.width:
                    obs[oy, ox, 0] = float(self.grid[ny][nx] == OBSTACLE)
                    obs[oy, ox, 1] = float(self.grid[ny][nx] == RESOURCE)
                    obs[oy, ox, 2] = float(self.grid[ny][nx] == TARGET)
                    for j, apos in enumerate(self.agent_positions):
                        if j != agent_id and apos == (ny, nx):
                            obs[oy, ox, 3] = 1.0
        return obs

    def step(self, actions: list[int]):
        if self.done:
            return self._get_obs(), [0.0] * self.agent_count, True, {}

        rewards = [self.rewards["step"]] * self.agent_count
        proposed = []
        for i, action in enumerate(actions):
            if action >= self.action_space:
                action = ACTION_STAY
            dy, dx = DIRECTIONS.get(action, (0, 0))
            ny = np.clip(self.agent_positions[i][0] + dy, 0, self.height - 1)
            nx = np.clip(self.agent_positions[i][1] + dx, 0, self.width - 1)
            proposed.append((ny, nx))

        resolved = self._resolve_actions(proposed, actions)

        for i in range(self.agent_count):
            new_pos = resolved[i]
            old_pos = self.agent_positions[i]

            if new_pos != old_pos and self.grid[new_pos[0]][new_pos[1]] == OBSTACLE:
                rewards[i] += self.rewards["wall"]
                new_pos = old_pos

            if new_pos != old_pos and self.collision_rule == "bounce_back":
                for j in range(i):
                    if resolved[j] == new_pos and resolved[j] != self.agent_positions[j]:
                        rewards[i] += self.rewards["collision"]
                        rewards[j] += self.rewards["collision"]
                        new_pos = old_pos
                        break

            self.agent_positions[i] = new_pos

        if self.collision_rule == "both_stay":
            self._resolve_both_stay_collisions(proposed, rewards)

        for i in range(self.agent_count):
            pos = self.agent_positions[i]
            cell = self.grid[pos[0]][pos[1]]
            if cell == TARGET:
                rewards[i] += self.rewards["goal"]
            if cell == RESOURCE and pos not in self.resource_collected:
                rewards[i] += self.rewards["resource"]
                self.resource_collected.add(pos)
                self.resource_timers[pos] = self.resource_refresh_interval

        self._apply_predator_prey_rewards(rewards)
        self._refresh_resources()
        self.step_count += 1

        for i in range(self.agent_count):
            self.episode_rewards[i] += rewards[i]

        info = {"step": self.step_count, "agent_positions": list(self.agent_positions)}

        if self.step_count >= self.max_steps:
            for i in range(self.agent_count):
                rewards[i] += self.rewards["timeout"]
                self.episode_rewards[i] += self.rewards["timeout"]
            self.done = True

        return self._get_obs(), rewards, self.done, info

    def _resolve_actions(self, proposed: list, actions: list) -> list:
        resolved = list(proposed)
        target_counts = {}
        for i, pos in enumerate(resolved):
            target_counts[pos] = target_counts.get(pos, 0) + 1

        conflict_positions = {pos for pos, count in target_counts.items() if count > 1}
        for pos in conflict_positions:
            agents_to_pos = [i for i, p in enumerate(resolved) if p == pos]
            for i in agents_to_pos:
                resolved[i] = self.agent_positions[i]

        return resolved

    def _resolve_both_stay_collisions(self, proposed: list, rewards: list):
        for i in range(self.agent_count):
            for j in range(i + 1, self.agent_count):
                if (proposed[i] == self.agent_positions[j] and
                        proposed[j] == self.agent_positions[i]):
                    self.agent_positions[i] = self.agent_positions[i]
                    self.agent_positions[j] = self.agent_positions[j]
                    rewards[i] += self.rewards["collision"]
                    rewards[j] += self.rewards["collision"]

    def _apply_predator_prey_rewards(self, rewards: list):
        if not self.team_config:
            return
        predators = [i for i, t in enumerate(self.agent_teams) if t == 1]
        prey = [i for i, t in enumerate(self.agent_teams) if t == 0]
        if not predators or not prey:
            return

        for p_idx in prey:
            prey_pos = self.agent_positions[p_idx]
            adjacent_predators = 0
            for pred_idx in predators:
                pred_pos = self.agent_positions[pred_idx]
                dist = abs(pred_pos[0] - prey_pos[0]) + abs(pred_pos[1] - prey_pos[1])
                if dist <= 1:
                    adjacent_predators += 1
            if adjacent_predators >= 2:
                rewards[p_idx] += self.rewards["catch_prey"]
                for pred_idx in predators:
                    if abs(self.agent_positions[pred_idx][0] - prey_pos[0]) + abs(
                            self.agent_positions[pred_idx][1] - prey_pos[1]) <= 1:
                        rewards[pred_idx] += self.rewards["catch_predator"]

    def _refresh_resources(self):
        refreshed = []
        for pos, timer in list(self.resource_timers.items()):
            self.resource_timers[pos] -= 1
            if self.resource_timers[pos] <= 0:
                del self.resource_timers[pos]
                if self.resource_refresh == "fixed_interval":
                    self.grid[pos[0]][pos[1]] = RESOURCE
                    self.resource_collected.discard(pos)
                    refreshed.append(pos)
                elif self.resource_refresh == "random_position":
                    ry = np.random.randint(0, self.height)
                    rx = np.random.randint(0, self.width)
                    if self.grid[ry][rx] == EMPTY:
                        self.grid[ry][rx] = RESOURCE
                        self.resource_positions.append((ry, rx))
                        self.resource_collected.discard((ry, rx))

    def get_obs_shape(self):
        if self.obs_range == -1:
            return (self.height, self.width, 4)
        r = self.obs_range
        s = 2 * r + 1
        return (s, s, 4)

    def get_state_shape(self):
        return (self.height, self.width, 4)

    def get_global_state(self) -> np.ndarray:
        return self._global_obs(-1)
