import asyncio
import json
import os
import torch
import numpy as np
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.environment import GridWorldEnv
from app.algorithms.factory import create_algorithm
from app.algorithms.communication.comm import CommModule
from app.models.models import Experiment, TrainingLog, Checkpoint, Environment
from app.core.database import async_session


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
            env_config = task.env_config
            algo_config = task.algorithm_config
            algorithm_name = algo_config["algorithm"]

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

            env = GridWorldEnv(
                map_config=env_config["map_config"],
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

            async with async_session() as session:
                exp = await session.get(Experiment, task.experiment_id)
                if exp:
                    exp.status = task.status
                    exp.current_episode = task.current_episode
                    exp.finished_at = datetime.utcnow()
                    await session.commit()

        except Exception as e:
            task.status = "error"
            async with async_session() as session:
                exp = await session.get(Experiment, task.experiment_id)
                if exp:
                    exp.status = "error"
                    exp.finished_at = datetime.utcnow()
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

    def get_task(self, experiment_id: int) -> Optional[TrainingTask]:
        if experiment_id in self.active_tasks:
            return self.active_tasks[experiment_id]
        for t in self.queue:
            if t.experiment_id == experiment_id:
                return t
        return None


training_manager = TrainingManager()
