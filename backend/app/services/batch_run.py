import asyncio
import copy
import itertools
import logging
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import async_session
from app.models.models import (
    ExperimentTemplate as TemplateModel,
    BatchRun as BatchRunModel,
    Experiment as ExpModel,
    Environment,
    TrainingLog,
)
from app.services.training import TrainingTask, training_manager

logger = logging.getLogger(__name__)

MAX_COMBINATIONS = 50
MAX_VALUES_PER_VAR = 10


def _get_nested_value(d: dict, path: str) -> Optional[Any]:
    keys = path.split("/")
    current = d
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_nested_value(d: dict, path: str, value: any):
    keys = path.split("/")
    current = d
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def validate_param_variables(template: TemplateModel, param_variables: dict) -> list[str]:
    errors = []
    hyperparams = template.hyperparams if isinstance(template.hyperparams, dict) else {}

    for path, values in param_variables.items():
        if not isinstance(values, list):
            errors.append(f"变量 {path} 的值必须是列表")
            continue

        if len(values) > MAX_VALUES_PER_VAR:
            errors.append(f"变量 {path} 的候选值数量不能超过 {MAX_VALUES_PER_VAR} 个")

        if _get_nested_value(hyperparams, path) is None:
            errors.append(f"变量路径 {path} 在模板超参数中不存在")

    return errors


def generate_grid_combinations(param_variables: dict) -> list[dict]:
    if not param_variables:
        return [{}]

    keys = list(param_variables.keys())
    value_lists = list(param_variables.values())

    combinations = []
    for values in itertools.product(*value_lists):
        combination = {}
        for i, key in enumerate(keys):
            combination[key] = values[i]
        combinations.append(combination)

    return combinations


def apply_params_to_hyperparams(hyperparams: dict, param_combination: dict) -> dict:
    result = copy.deepcopy(hyperparams)
    for path, value in param_combination.items():
        _set_nested_value(result, path, value)
    return result


class BatchRunManager:
    def __init__(self):
        self._running_batches: dict[int, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def create_batch_run(
        self,
        template_id: int,
        name: str,
        db: AsyncSession,
    ) -> BatchRunModel:
        template = await db.get(TemplateModel, template_id)
        if not template:
            raise ValueError("Template not found")

        env = await db.get(Environment, template.environment_id)
        if not env:
            raise ValueError(f"Environment {template.environment_id} not found")

        param_variables = template.param_variables if isinstance(template.param_variables, dict) else {}
        errors = validate_param_variables(template, param_variables)
        if errors:
            raise ValueError("参数变量校验失败: " + "; ".join(errors))

        combinations = generate_grid_combinations(param_variables)
        if len(combinations) > MAX_COMBINATIONS:
            raise ValueError(f"参数组合总数不能超过 {MAX_COMBINATIONS} 个，当前为 {len(combinations)} 个")

        batch_run = BatchRunModel(
            name=name,
            template_id=template_id,
            status="pending",
            experiment_ids=[],
            current_index=0,
            param_combinations=combinations,
        )
        db.add(batch_run)
        await db.commit()
        await db.refresh(batch_run)

        hyperparams = template.hyperparams if isinstance(template.hyperparams, dict) else {}
        exp_ids = []
        for i, combo in enumerate(combinations):
            exp_hyperparams = apply_params_to_hyperparams(hyperparams, combo)
            exp_name = f"{name} - #{i + 1}"
            if combo:
                params_str = ", ".join(f"{k.split('/')[-1]}={v}" for k, v in combo.items())
                exp_name = f"{name} - {params_str}"

            exp = ExpModel(
                name=exp_name,
                environment_id=template.environment_id,
                algorithm=template.algorithm,
                hyperparams=exp_hyperparams,
                communication_enabled=template.communication_enabled,
                total_episodes=template.total_episodes,
                batch_run_id=batch_run.id,
            )
            db.add(exp)
            await db.flush()
            exp_ids.append(exp.id)

        batch_run.experiment_ids = exp_ids
        await db.commit()
        await db.refresh(batch_run)

        return batch_run

    async def start_batch_run(self, batch_run_id: int):
        async with self._lock:
            if batch_run_id in self._running_batches:
                raise ValueError("Batch run already started")

            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if not batch_run:
                    raise ValueError("Batch run not found")
                if batch_run.status not in ("pending",):
                    raise ValueError(f"Cannot start batch run with status: {batch_run.status}")

                batch_run.status = "running"
                batch_run.started_at = datetime.utcnow()
                await session.commit()

            task = asyncio.create_task(self._run_batch(batch_run_id))
            self._running_batches[batch_run_id] = task
            task.add_done_callback(lambda t: self._on_batch_done(batch_run_id, t))

    async def _run_batch(self, batch_run_id: int):
        try:
            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if not batch_run:
                    return

                template = await session.get(TemplateModel, batch_run.template_id)
                if not template:
                    raise ValueError("Template not found")

                env = await session.get(Environment, template.environment_id)
                if not env:
                    raise ValueError(f"Environment {template.environment_id} not found")

                experiment_ids = batch_run.experiment_ids if isinstance(batch_run.experiment_ids, list) else []
                param_combinations = batch_run.param_combinations if isinstance(batch_run.param_combinations, list) else []

                env_config = {
                    "map_config": env.map_config if isinstance(env.map_config, dict) else {},
                    "max_steps": env.max_steps,
                    "obs_range": env.obs_range,
                    "action_space": env.action_space,
                    "collision_rule": env.collision_rule,
                    "resource_refresh": env.resource_refresh,
                    "resource_refresh_interval": env.resource_refresh_interval,
                    "agent_count": env.agent_count,
                    "team_config": env.team_config if isinstance(env.team_config, dict) else {},
                    "reward_goal": env.reward_goal,
                    "reward_resource": env.reward_resource,
                    "reward_collision": env.reward_collision,
                    "reward_wall": env.reward_wall,
                    "reward_step": env.reward_step,
                    "reward_catch_predator": env.reward_catch_predator,
                    "reward_catch_prey": env.reward_catch_prey,
                    "reward_timeout": env.reward_timeout,
                }

            for i, exp_id in enumerate(experiment_ids):
                async with async_session() as session:
                    batch_run = await session.get(BatchRunModel, batch_run_id)
                    if not batch_run or batch_run.is_cancelled:
                        break

                    batch_run.current_index = i
                    await session.commit()

                async with async_session() as session:
                    exp = await session.get(ExpModel, exp_id)
                    if not exp:
                        continue

                    combo = param_combinations[i] if i < len(param_combinations) else {}

                    hyperparams = exp.hyperparams if isinstance(exp.hyperparams, dict) else {}
                    if "algorithm" not in hyperparams:
                        hyperparams["algorithm"] = exp.algorithm

                task = TrainingTask(exp_id, env_config, hyperparams, exp.total_episodes)
                await training_manager.submit_task(task)

                while True:
                    await asyncio.sleep(2)
                    current_task = training_manager.get_task(exp_id)
                    if not current_task:
                        break
                    if current_task.status in ("completed", "stopped", "error"):
                        if current_task.status == "error":
                            async with async_session() as session:
                                batch_run = await session.get(BatchRunModel, batch_run_id)
                                if batch_run:
                                    batch_run.status = "failed"
                                    batch_run.error_message = f"Experiment {exp_id} failed"
                                    batch_run.finished_at = datetime.utcnow()
                                    await session.commit()
                            return
                        break

            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if batch_run and not batch_run.is_cancelled:
                    batch_run.status = "completed"
                    batch_run.finished_at = datetime.utcnow()
                    await session.commit()

        except Exception as e:
            logger.exception("Batch run failed")
            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if batch_run:
                    batch_run.status = "failed"
                    batch_run.error_message = str(e)
                    batch_run.finished_at = datetime.utcnow()
                    await session.commit()

    def _on_batch_done(self, batch_run_id: int, task: asyncio.Task):
        async def _cleanup():
            async with self._lock:
                if batch_run_id in self._running_batches:
                    del self._running_batches[batch_run_id]
        asyncio.create_task(_cleanup())

    async def cancel_batch_run(self, batch_run_id: int):
        async with async_session() as session:
            batch_run = await session.get(BatchRunModel, batch_run_id)
            if not batch_run:
                raise ValueError("Batch run not found")

            batch_run.is_cancelled = True
            if batch_run.status == "running":
                batch_run.status = "failed"
                batch_run.error_message = "Cancelled by user"
                batch_run.finished_at = datetime.utcnow()
            await session.commit()

            experiment_ids = batch_run.experiment_ids if isinstance(batch_run.experiment_ids, list) else []
            current_index = batch_run.current_index

            for i in range(current_index + 1, len(experiment_ids)):
                exp_id = experiment_ids[i]
                exp = await session.get(ExpModel, exp_id)
                if exp and exp.status in ("created", "queued"):
                    exp.status = "stopped"
            await session.commit()

    async def get_batch_stats(self, batch_run_id: int, db: AsyncSession) -> dict:
        batch_run = await db.get(BatchRunModel, batch_run_id)
        if not batch_run:
            raise ValueError("Batch run not found")

        experiment_ids = batch_run.experiment_ids if isinstance(batch_run.experiment_ids, list) else []
        param_combinations = batch_run.param_combinations if isinstance(batch_run.param_combinations, list) else []
        param_variables = {}

        template = await db.get(TemplateModel, batch_run.template_id)
        if template:
            param_variables = template.param_variables if isinstance(template.param_variables, dict) else {}

        experiments = []
        completed_count = 0
        running_count = 0
        failed_count = 0
        pending_count = 0

        for i, exp_id in enumerate(experiment_ids):
            exp = await db.get(ExpModel, exp_id)
            if not exp:
                continue

            combo = param_combinations[i] if i < len(param_combinations) else {}
            summary = exp.summary if isinstance(exp.summary, dict) else {}

            exp_data = {
                "id": exp.id,
                "name": exp.name,
                "status": exp.status,
                "params": combo,
                "final_reward": summary.get("final_avg_reward"),
                "max_reward": summary.get("max_episode_reward"),
                "current_episode": exp.current_episode,
                "total_episodes": exp.total_episodes,
            }
            experiments.append(exp_data)

            if exp.status == "completed":
                completed_count += 1
            elif exp.status == "running":
                running_count += 1
            elif exp.status in ("error", "stopped"):
                failed_count += 1
            else:
                pending_count += 1

        group_stats = []
        for var_path in param_variables.keys():
            var_name = var_path.split("/")[-1]
            groups = {}
            for exp_data in experiments:
                if exp_data["final_reward"] is None:
                    continue
                val = exp_data["params"].get(var_path)
                if val not in groups:
                    groups[val] = []
                groups[val].append(exp_data["final_reward"])

            group_stat = []
            for val, rewards in groups.items():
                avg_reward = sum(rewards) / len(rewards) if rewards else 0
                group_stat.append({
                    "variable": var_name,
                    "value": val,
                    "avg_reward": round(avg_reward, 4),
                    "count": len(rewards),
                })
            group_stats.append({"variable": var_name, "groups": group_stat})

        best_combination = None
        completed_exps = [e for e in experiments if e["final_reward"] is not None]
        if completed_exps:
            best = max(completed_exps, key=lambda x: x["final_reward"])
            best_combination = {
                "experiment_id": best["id"],
                "params": best["params"],
                "final_reward": best["final_reward"],
            }

        total_duration = None
        if batch_run.started_at and batch_run.finished_at:
            total_duration = (batch_run.finished_at - batch_run.started_at).total_seconds()

        return {
            "batch_run_id": batch_run.id,
            "status": batch_run.status,
            "total_experiments": len(experiment_ids),
            "completed_count": completed_count,
            "running_count": running_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "experiments": experiments,
            "group_stats": group_stats,
            "best_combination": best_combination,
            "total_duration_seconds": total_duration,
        }


batch_run_manager = BatchRunManager()
