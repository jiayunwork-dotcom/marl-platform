import asyncio
import ast
import json
import os
import logging
import torch
import numpy as np
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.config import settings
from app.core.environment import GridWorldEnv
from app.algorithms.factory import create_algorithm
from app.algorithms.communication.comm import CommModule
from app.models.models import Experiment, TrainingLog, Checkpoint, Environment
from app.core.database import async_session

logger = logging.getLogger(__name__)


def _safe_parse_json(value):
    """Robust JSON parsing with Python repr fallback."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return {}
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            try:
                return ast.literal_eval(s)
            except (ValueError, SyntaxError):
                return {}
    return {}


class TrainingTask:
    def __init__(self, experiment_id: int, env_config: dict, algorithm_config: dict, total_episodes: int):
        self.experiment_id = experiment_id
        self.env_config = env_config
        self.algorithm_config = algorithm_config
        self.total_episodes = total_episodes
        self.status = "queued"
        self.current_episode = 0
        self.algorithm = None
        self.env = None
        self._should_stop = False
        self._should_pause = False
        self.episode_data = []

    def stop(self):
        self._should_stop = True

    def pause(self):
        self._should_pause = True

    def resume(self):
        self._should_pause = False


class TrainingManager:
    def __init__(self):
        self.queue: list[TrainingTask] = []
        self.active_tasks: dict[int, TrainingTask] = {}
        self.max_concurrent = settings.MAX_CONCURRENT_TRAINING
        self._lock = asyncio.Lock()
        self._running = False

    async def submit_task(self, task: TrainingTask):
        async with self._lock:
            self.queue.append(task)
        if not self._running:
            asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        self._running = True
        while True:
            async with self._lock:
                available = self.max_concurrent - len(self.active_tasks)
                while available > 0 and self.queue:
                    task = self.queue.pop(0)
                    task.status = "running"
                    self.active_tasks[task.experiment_id] = task
                    asyncio.create_task(self._run_task(task))
                    available -= 1

            await asyncio.sleep(1)

            async with self._lock:
                finished = [eid for eid, t in self.active_tasks.items() if t.status in ("completed", "stopped", "error")]
                for eid in finished:
                    del self.active_tasks[eid]

                if not self.active_tasks and not self.queue:
                    self._running = False
                    break

    async def _run_task(self, task: TrainingTask):
        try:
            env_config = task.env_config or {}
            algo_config = _safe_parse_json(task.algorithm_config)

            # --- Resolve algorithm name with multiple fallbacks ---
            async with async_session() as session:
                exp_for_name = await session.get(Experiment, task.experiment_id)
            stored_algorithm = exp_for_name.algorithm if exp_for_name else None
            algorithm_name = (
                algo_config.get("algorithm")
                or algo_config.get("algo")
                or stored_algorithm
            )
            if not algorithm_name:
                raise ValueError(
                    f"No algorithm name could be resolved for experiment {task.experiment_id}. "
                    f"algo_config keys: {list(algo_config.keys())}, "
                    f"stored.algorithm={stored_algorithm!r}"
                )
            # Make the algorithm name visible to the algorithm class (e.g. epsilon logic)
            algo_config.setdefault("algorithm", algorithm_name)

            logger.info(
                "Starting training task exp=%s algo=%s total_episodes=%s",
                task.experiment_id, algorithm_name, task.total_episodes,
            )

            rewards = {
                "goal": env_config.get("reward_goal", 10.0),
                "resource": env_config.get("reward_resource", 5.0),
                "collision": env_config.get("reward_collision", -2.0),
                "wall": env_config.get("reward_wall", -1.0),
                "step": env_config.get("reward_step", -0.1),
                "catch_predator": env_config.get("reward_catch_predator", 20.0),
                "catch_prey": env_config.get("reward_catch_prey", -20.0),
                "timeout": env_config.get("reward_timeout", -5.0),
            }

            # --- Resolve env map_config from DB as fallback ---
            if "map_config" not in env_config or not env_config.get("map_config"):
                if exp_for_name:
                    async with async_session() as session:
                        env_row = await session.get(Environment, exp_for_name.environment_id)
                        if env_row:
                            env_config["map_config"] = _safe_parse_json(env_row.map_config)
                            env_config.setdefault("agent_count", env_row.agent_count)
                            env_config.setdefault("max_steps", env_row.max_steps)
                            env_config.setdefault("obs_range", env_row.obs_range)
                            env_config.setdefault("action_space", env_row.action_space)

            map_config = env_config.get("map_config")
            if not map_config or not isinstance(map_config, dict):
                raise ValueError(
                    f"Invalid map_config for experiment {task.experiment_id}: {map_config!r}"
                )

            env = GridWorldEnv(
                map_config=map_config,
                max_steps=env_config.get("max_steps", 100),
                obs_range=env_config.get("obs_range", -1),
                action_space=env_config.get("action_space", 5),
                collision_rule=env_config.get("collision_rule", "both_stay"),
                resource_refresh=env_config.get("resource_refresh", "fixed_interval"),
                resource_refresh_interval=env_config.get("resource_refresh_interval", 10),
                rewards=rewards,
                agent_count=env_config.get("agent_count", 2),
                team_config=env_config.get("team_config", {}),
            )
            task.env = env

            obs_shape = env.get_obs_shape()
            n_actions = env.action_space
            n_agents = env.agent_count

            algorithm = create_algorithm(algorithm_name, n_agents, obs_shape, n_actions, algo_config)
            task.algorithm = algorithm

            comm_enabled = algo_config.get("communication_enabled", False)
            comm_module = None
            if comm_enabled and algorithm_name in ("QMIX", "MAPPO"):
                comm_dim = algo_config.get("comm_dim", 8)
                comm_module = CommModule(obs_shape, n_agents, comm_dim).to(algorithm.device)

            async with async_session() as session:
                exp = await session.get(Experiment, task.experiment_id)
                if exp:
                    exp.status = "running"
                    exp.started_at = datetime.utcnow()
                    await session.commit()

            for episode in range(task.total_episodes):
                if task._should_stop:
                    task.status = "stopped"
                    break

                while task._should_pause:
                    await asyncio.sleep(0.5)
                    if task._should_stop:
                        task.status = "stopped"
                        break

                obs = env.reset()
                episode_rewards = [0.0] * n_agents
                episode_steps = 0
                done = False

                while not done:
                    if algorithm_name == "MAPPO":
                        actions = algorithm.select_actions(obs)
                        next_obs, rewards_list, done, info = env.step(actions)
                        algorithm.collect_trajectory(obs, actions, rewards_list, next_obs, done)
                    else:
                        actions = algorithm.select_actions(obs)
                        next_obs, rewards_list, done, info = env.step(actions)
                        algorithm.store_transition(obs, actions, rewards_list, next_obs, done)

                    for i in range(n_agents):
                        episode_rewards[i] += rewards_list[i]
                    obs = next_obs
                    episode_steps += 1

                if algorithm_name == "MAPPO":
                    algorithm.update()
                else:
                    for _ in range(n_agents):
                        algorithm.update()

                task.current_episode = episode + 1

                goal_reached = any(r > 0 and abs(r) > 5 for r in episode_rewards)
                total_reward = sum(episode_rewards)

                recent_wins = 0
                if len(task.episode_data) >= 10:
                    recent_wins = sum(1 for d in task.episode_data[-10:] if d["goal_reached"])
                win_rate = recent_wins / min(10, len(task.episode_data) + 1)

                ep_data = {
                    "episode": episode + 1,
                    "total_reward": total_reward,
                    "agent_rewards": {str(i): r for i, r in enumerate(episode_rewards)},
                    "steps": episode_steps,
                    "goal_reached": goal_reached,
                    "win_rate": win_rate,
                    "agent_positions": [list(p) for p in env.agent_positions],
                }
                task.episode_data.append(ep_data)

                async with async_session() as session:
                    log = TrainingLog(
                        experiment_id=task.experiment_id,
                        episode=episode + 1,
                        total_reward=total_reward,
                        agent_rewards={str(i): r for i, r in enumerate(episode_rewards)},
                        steps=episode_steps,
                        goal_reached=goal_reached,
                        win_rate=win_rate,
                    )
                    session.add(log)
                    await session.commit()

                if (episode + 1) % settings.CHECKPOINT_INTERVAL == 0:
                    await self._save_checkpoint(task, episode + 1)

            if task.status != "stopped":
                task.status = "completed"
                await self._save_final(task)

            summary = await self._compute_summary(task)

            async with async_session() as session:
                exp = await session.get(Experiment, task.experiment_id)
                if exp:
                    exp.status = task.status
                    exp.current_episode = task.current_episode
                    exp.finished_at = datetime.utcnow()
                    exp.summary = summary
                    await session.commit()

        except Exception as e:
            task.status = "error"

            summary = None
            if len(task.episode_data) >= 50:
                summary = await self._compute_summary(task)

            async with async_session() as session:
                exp = await session.get(Experiment, task.experiment_id)
                if exp:
                    exp.status = "error"
                    exp.finished_at = datetime.utcnow()
                    exp.summary = summary
                    await session.commit()
            import traceback
            traceback.print_exc()

    async def _save_checkpoint(self, task: TrainingTask, episode: int):
        if task.algorithm is None:
            return
        exp_name = f"exp_{task.experiment_id}"
        filename = f"{exp_name}_ep{episode}.pt"
        filepath = os.path.join(settings.CHECKPOINT_DIR, filename)

        state = task.algorithm.state_dict()
        state["episode"] = episode
        state["env_config"] = task.env_config
        state["algo_config"] = task.algorithm_config
        torch.save(state, filepath)

        async with async_session() as session:
            checkpoints = await session.execute(
                select(Checkpoint).where(Checkpoint.experiment_id == task.experiment_id)
            )
            existing = checkpoints.scalars().all()
            if len(existing) >= settings.MAX_CHECKPOINTS:
                oldest = sorted(existing, key=lambda c: c.episode)[0]
                if os.path.exists(oldest.filepath):
                    os.remove(oldest.filepath)
                await session.delete(oldest)

            ckpt = Checkpoint(
                experiment_id=task.experiment_id,
                episode=episode,
                filepath=filepath,
            )
            session.add(ckpt)
            await session.commit()

    async def _save_final(self, task: TrainingTask):
        if task.algorithm is None:
            return
        exp_name = f"exp_{task.experiment_id}"
        filename = f"{exp_name}_final.pt"
        filepath = os.path.join(settings.CHECKPOINT_DIR, filename)

        state = task.algorithm.state_dict()
        state["episode"] = task.current_episode
        state["env_config"] = task.env_config
        state["algo_config"] = task.algorithm_config
        torch.save(state, filepath)

    async def _compute_summary(self, task: TrainingTask) -> dict:
        async with async_session() as session:
            total_q = await session.execute(
                select(func.count(TrainingLog.id)).where(
                    TrainingLog.experiment_id == task.experiment_id
                )
            )
            total_logs = total_q.scalar() or 0

            if total_logs < 50:
                return {}

            logs_q = await session.execute(
                select(TrainingLog)
                .where(TrainingLog.experiment_id == task.experiment_id)
                .order_by(TrainingLog.episode.desc())
                .limit(50)
            )
            recent_logs = list(reversed(logs_q.scalars().all()))

            last_50_rewards = [l.total_reward for l in recent_logs]
            final_avg_reward = float(np.mean(last_50_rewards))

            all_logs_q = await session.execute(
                select(TrainingLog.total_reward)
                .where(TrainingLog.experiment_id == task.experiment_id)
                .order_by(TrainingLog.episode)
            )
            all_rewards = [r for (r,) in all_logs_q.all()]
            max_reward = float(max(all_rewards)) if all_rewards else 0.0

            convergence_episode = None
            threshold = final_avg_reward * 0.8
            n_total = len(all_rewards)
            if n_total >= 20:
                for start in range(n_total - 19):
                    window = all_rewards[start:start + 20]
                    window_avg = float(np.mean(window))
                    if window_avg >= threshold:
                        convergence_episode = start + 1
                        break

            exp = await session.get(Experiment, task.experiment_id)
            total_duration = None
            if exp and exp.started_at and exp.finished_at:
                total_duration = (exp.finished_at - exp.started_at).total_seconds()

        return {
            "final_avg_reward": round(final_avg_reward, 4),
            "max_episode_reward": round(max_reward, 4),
            "convergence_episode": convergence_episode,
            "total_duration_seconds": total_duration,
        }

    def get_task(self, experiment_id: int) -> Optional[TrainingTask]:
        if experiment_id in self.active_tasks:
            return self.active_tasks[experiment_id]
        for t in self.queue:
            if t.experiment_id == experiment_id:
                return t
        return None


training_manager = TrainingManager()
