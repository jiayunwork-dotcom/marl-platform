import asyncio
import ast
import json
import logging
import time
import numpy as np
import torch
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import settings
from app.core.environment import GridWorldEnv
from app.algorithms.factory import create_algorithm
from app.models.models import PolicyService, InferenceLog, Checkpoint, Experiment, Environment
from app.core.database import async_session

logger = logging.getLogger(__name__)


def _safe_parse_json(value):
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


class DeployedPolicy:
    def __init__(self, policy_id: int, algorithm, env_config: dict, algo_config: dict, n_agents: int, obs_shape: tuple, n_actions: int):
        self.policy_id = policy_id
        self.algorithm = algorithm
        self.env_config = env_config
        self.algo_config = algo_config
        self.n_agents = n_agents
        self.obs_shape = obs_shape
        self.n_actions = n_actions
        self.health_check_failures = 0
        self.last_health_check_time: Optional[datetime] = None
        self.last_error: Optional[str] = None

    def infer(self, observations: list, communication_context=None) -> dict:
        obs_list = []
        for obs in observations:
            arr = np.array(obs, dtype=np.float32)
            obs_list.append(arr)

        actions = self.algorithm.select_actions(obs_list, evaluate=True)

        q_values = None
        try:
            q_vals = []
            for i, obs in enumerate(obs_list):
                q = self.algorithm.get_q_values(i, obs)
                q_vals.append(q.tolist() if hasattr(q, 'tolist') else list(q))
            q_values = q_vals
        except Exception:
            pass

        return {"actions": actions, "q_values": q_values}

    def health_check(self) -> bool:
        try:
            dummy_obs = []
            for _ in range(self.n_agents):
                shape = self.obs_shape
                dummy = np.zeros(shape, dtype=np.float32)
                dummy_obs.append(dummy)
            result = self.infer(dummy_obs)
            return len(result["actions"]) == self.n_agents
        except Exception as e:
            self.last_error = str(e)
            return False


class PolicyDeploymentManager:
    def __init__(self):
        self.deployed: dict[int, DeployedPolicy] = {}
        self._health_task: Optional[asyncio.Task] = None
        self._running = False

    async def load_model(self, policy_id: int) -> DeployedPolicy:
        async with async_session() as session:
            policy = await session.get(PolicyService, policy_id)
            if not policy:
                raise ValueError(f"PolicyService {policy_id} not found")

            checkpoint = await session.get(Checkpoint, policy.checkpoint_id)
            if not checkpoint:
                raise ValueError(f"Checkpoint {policy.checkpoint_id} not found")

            experiment = await session.get(Experiment, policy.experiment_id)
            if not experiment:
                raise ValueError(f"Experiment {policy.experiment_id} not found")

            environment = await session.get(Environment, experiment.environment_id)
            if not environment:
                raise ValueError(f"Environment {experiment.environment_id} not found")

        state = torch.load(checkpoint.filepath, map_location="cpu", weights_only=False)

        env_config = state.get("env_config", {})
        algo_config = state.get("algo_config", {})

        if not env_config:
            env_config = {
                "map_config": _safe_parse_json(environment.map_config),
                "max_steps": environment.max_steps,
                "obs_range": environment.obs_range,
                "action_space": environment.action_space,
                "collision_rule": environment.collision_rule,
                "resource_refresh": environment.resource_refresh,
                "resource_refresh_interval": environment.resource_refresh_interval,
                "agent_count": environment.agent_count,
                "team_config": _safe_parse_json(environment.team_config),
                "reward_goal": environment.reward_goal,
                "reward_resource": environment.reward_resource,
                "reward_collision": environment.reward_collision,
                "reward_wall": environment.reward_wall,
                "reward_step": environment.reward_step,
                "reward_catch_predator": environment.reward_catch_predator,
                "reward_catch_prey": environment.reward_catch_prey,
                "reward_timeout": environment.reward_timeout,
            }

        if not algo_config or "algorithm" not in algo_config:
            algo_config = _safe_parse_json(experiment.hyperparams)
            algo_config.setdefault("algorithm", experiment.algorithm)

        map_config = env_config.get("map_config", _safe_parse_json(environment.map_config))
        env = GridWorldEnv(
            map_config=map_config,
            max_steps=env_config.get("max_steps", environment.max_steps),
            obs_range=env_config.get("obs_range", environment.obs_range),
            action_space=env_config.get("action_space", environment.action_space),
            collision_rule=env_config.get("collision_rule", environment.collision_rule),
            resource_refresh=env_config.get("resource_refresh", environment.resource_refresh),
            resource_refresh_interval=env_config.get("resource_refresh_interval", environment.resource_refresh_interval),
            rewards={
                "goal": env_config.get("reward_goal", environment.reward_goal),
                "resource": env_config.get("reward_resource", environment.reward_resource),
                "collision": env_config.get("reward_collision", environment.reward_collision),
                "wall": env_config.get("reward_wall", environment.reward_wall),
                "step": env_config.get("reward_step", environment.reward_step),
                "catch_predator": env_config.get("reward_catch_predator", environment.reward_catch_predator),
                "catch_prey": env_config.get("reward_catch_prey", environment.reward_catch_prey),
                "timeout": env_config.get("reward_timeout", environment.reward_timeout),
            },
            agent_count=env_config.get("agent_count", environment.agent_count),
            team_config=env_config.get("team_config", _safe_parse_json(environment.team_config)),
        )

        obs_shape = env.get_obs_shape()
        n_actions = env.action_space
        n_agents = env.agent_count

        algorithm_name = algo_config.get("algorithm", experiment.algorithm)
        algorithm = create_algorithm(algorithm_name, n_agents, obs_shape, n_actions, algo_config)

        algorithm.load_state_dict({k: v for k, v in state.items() if k not in ("episode", "env_config", "algo_config")})
        algorithm.eval() if hasattr(algorithm, 'eval') else None

        deployed = DeployedPolicy(
            policy_id=policy_id,
            algorithm=algorithm,
            env_config=env_config,
            algo_config=algo_config,
            n_agents=n_agents,
            obs_shape=obs_shape,
            n_actions=n_actions,
        )
        self.deployed[policy_id] = deployed
        return deployed

    def unload_model(self, policy_id: int):
        if policy_id in self.deployed:
            del self.deployed[policy_id]

    def get_deployed(self, policy_id: int) -> Optional[DeployedPolicy]:
        return self.deployed.get(policy_id)

    def start_health_checks(self):
        if not self._running:
            self._running = True
            self._health_task = asyncio.create_task(self._health_check_loop())

    def stop_health_checks(self):
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            self._health_task = None

    async def _health_check_loop(self):
        while self._running:
            try:
                policy_ids = list(self.deployed.keys())
                for pid in policy_ids:
                    deployed = self.deployed.get(pid)
                    if deployed is None:
                        continue

                    try:
                        loop = asyncio.get_event_loop()
                        ok = await loop.run_in_executor(None, deployed.health_check)
                    except Exception as e:
                        ok = False
                        deployed.last_error = str(e)

                    deployed.last_health_check_time = datetime.utcnow()

                    if ok:
                        deployed.health_check_failures = 0
                    else:
                        deployed.health_check_failures += 1
                        logger.warning(
                            "Health check failed for policy %s (%d/%d)",
                            pid, deployed.health_check_failures, settings.POLICY_HEALTH_CHECK_FAILURE_THRESHOLD,
                        )

                    if deployed.health_check_failures >= settings.POLICY_HEALTH_CHECK_FAILURE_THRESHOLD:
                        async with async_session() as session:
                            policy = await session.get(PolicyService, pid)
                            if policy and policy.status == "running":
                                policy.status = "error"
                                policy.error_reason = deployed.last_error or "Health check failed consecutively"
                                await session.commit()
                        logger.error("Policy %s marked as error after %d consecutive health check failures", pid, deployed.health_check_failures)
                        self.unload_model(pid)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check loop error: %s", str(e))

            await asyncio.sleep(settings.POLICY_HEALTH_CHECK_INTERVAL)


deployment_manager = PolicyDeploymentManager()
