import ast
import torch
import numpy as np
import json
from typing import Optional
from app.core.environment import GridWorldEnv
from app.algorithms.factory import create_algorithm
from app.core.config import settings
from app.core.database import async_session
from app.models.models import Experiment, Evaluation, Checkpoint, Environment
from sqlalchemy import select


def _safe_parse_json(value):
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return {}
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return {}
    return {}


async def run_evaluation(experiment_id: int, num_episodes: int = 10) -> dict:
    async with async_session() as session:
        exp = await session.get(Experiment, experiment_id)
        if not exp:
            raise ValueError(f"Experiment {experiment_id} not found")

        env_row = await session.get(Environment, exp.environment_id)
        if not env_row:
            raise ValueError(f"Environment {exp.environment_id} not found")

        ckpts = await session.execute(
            select(Checkpoint).where(Checkpoint.experiment_id == experiment_id)
            .order_by(Checkpoint.episode.desc()).limit(1)
        )
        latest_ckpt = ckpts.scalars().first()
        if not latest_ckpt:
            raise ValueError(f"No checkpoint found for experiment {experiment_id}")

        algo_config = _safe_parse_json(exp.hyperparams)
        if "algorithm" not in algo_config:
            algo_config["algorithm"] = exp.algorithm
        env_data = {
            "map_config": _safe_parse_json(env_row.map_config),
            "max_steps": env_row.max_steps,
            "obs_range": env_row.obs_range,
            "action_space": env_row.action_space,
            "collision_rule": env_row.collision_rule,
            "resource_refresh": env_row.resource_refresh,
            "resource_refresh_interval": env_row.resource_refresh_interval,
            "agent_count": env_row.agent_count,
            "team_config": _safe_parse_json(env_row.team_config),
            "reward_goal": env_row.reward_goal,
            "reward_resource": env_row.reward_resource,
            "reward_collision": env_row.reward_collision,
            "reward_wall": env_row.reward_wall,
            "reward_step": env_row.reward_step,
            "reward_catch_predator": env_row.reward_catch_predator,
            "reward_catch_prey": env_row.reward_catch_prey,
            "reward_timeout": env_row.reward_timeout,
        }

    rewards = {
        "goal": env_data.get("reward_goal", 10.0),
        "resource": env_data.get("reward_resource", 5.0),
        "collision": env_data.get("reward_collision", -2.0),
        "wall": env_data.get("reward_wall", -1.0),
        "step": env_data.get("reward_step", -0.1),
        "catch_predator": env_data.get("reward_catch_predator", 20.0),
        "catch_prey": env_data.get("reward_catch_prey", -20.0),
        "timeout": env_data.get("reward_timeout", -5.0),
    }

    env = GridWorldEnv(
        map_config=env_data["map_config"],
        max_steps=env_data["max_steps"],
        obs_range=env_data["obs_range"],
        action_space=env_data["action_space"],
        collision_rule=env_data["collision_rule"],
        resource_refresh=env_data["resource_refresh"],
        resource_refresh_interval=env_data["resource_refresh_interval"],
        rewards=rewards,
        agent_count=env_data["agent_count"],
        team_config=env_data["team_config"],
    )

    obs_shape = env.get_obs_shape()
    n_actions = env.action_space
    n_agents = env.agent_count

    algorithm = create_algorithm(algo_config["algorithm"], n_agents, obs_shape, n_actions, algo_config)
    state_dict = torch.load(latest_ckpt.filepath, map_location="cpu")
    algorithm.load_state_dict(state_dict)

    episode_data = []
    total_rewards = []
    total_successes = 0
    total_collisions = 0
    total_steps = []

    for ep in range(num_episodes):
        obs = env.reset()
        ep_data = {"steps": []}
        ep_reward = 0.0
        done = False
        step_count = 0
        ep_collisions = 0

        while not done:
            actions = algorithm.select_actions(obs, evaluate=True)
            step_info = {
                "step": step_count,
                "agent_positions": [list(p) for p in env.agent_positions],
                "actions": [int(a) for a in actions],
                "q_values": [],
            }
            for i in range(n_agents):
                q = algorithm.get_q_values(i, obs[i])
                step_info["q_values"].append(q.tolist())

            next_obs, rewards_list, done, info = env.step(actions)
            step_info["rewards"] = rewards_list
            for r in rewards_list:
                if r < -1.5:
                    ep_collisions += 1

            ep_data["steps"].append(step_info)
            ep_reward += sum(rewards_list)
            obs = next_obs
            step_count += 1

        ep_data["total_reward"] = ep_reward
        ep_data["steps_count"] = step_count
        ep_data["collisions"] = ep_collisions
        ep_data["success"] = ep_reward > 0

        episode_data.append(ep_data)
        total_rewards.append(ep_reward)
        if ep_reward > 0:
            total_successes += 1
        total_collisions += ep_collisions
        total_steps.append(step_count)

    avg_reward = np.mean(total_rewards)
    success_rate = total_successes / num_episodes
    collision_rate = total_collisions / max(sum(total_steps), 1)
    avg_steps = np.mean(total_steps)

    async with async_session() as session:
        evaluation = Evaluation(
            experiment_id=experiment_id,
            num_episodes=num_episodes,
            avg_reward=avg_reward,
            success_rate=success_rate,
            collision_rate=collision_rate,
            avg_steps=avg_steps,
            episode_data=episode_data,
        )
        session.add(evaluation)
        await session.commit()
        await session.refresh(evaluation)

    return {
        "id": evaluation.id,
        "avg_reward": avg_reward,
        "success_rate": success_rate,
        "collision_rate": collision_rate,
        "avg_steps": avg_steps,
        "episode_data": episode_data,
    }
