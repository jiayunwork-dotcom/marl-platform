import asyncio
import copy
import itertools
import logging
from datetime import datetime, timedelta
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
STALE_THRESHOLD_MINUTES = 5


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


def estimate_duration(template: TemplateModel, total_combinations: int, max_parallel: int, db: AsyncSession) -> Optional[float]:
    return None


class BatchRunManager:
    def __init__(self):
        self._running_batches: dict[int, asyncio.Task] = {}
        self._active_experiments: dict[int, set[int]] = {}
        self._lock = asyncio.Lock()

    async def _get_current_template_version(self, template_id: int, db: AsyncSession) -> int:
        result = await db.execute(
            select(TemplateModel).where(
                TemplateModel.id == template_id,
                TemplateModel.is_current_version == True,
            )
        )
        current = result.scalar_one_or_none()
        return current.version_number if current else 1

    async def create_batch_run(
        self,
        template_id: int,
        name: str,
        db: AsyncSession,
        max_parallel: int = 1,
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

        max_parallel = max(1, min(max_parallel, 4))
        template_version = await self._get_current_template_version(template_id, db)

        batch_run = BatchRunModel(
            name=name,
            template_id=template_id,
            template_version=template_version,
            status="pending",
            max_parallel=max_parallel,
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
                batch_run.last_progress_at = datetime.utcnow()
                await session.commit()

            self._active_experiments[batch_run_id] = set()
            task = asyncio.create_task(self._run_batch_parallel(batch_run_id))
            self._running_batches[batch_run_id] = task
            task.add_done_callback(lambda t: self._on_batch_done(batch_run_id, t))

    async def resume_batch_run(self, batch_run_id: int):
        async with self._lock:
            if batch_run_id in self._running_batches:
                raise ValueError("Batch run already running")

            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if not batch_run:
                    raise ValueError("Batch run not found")
                if batch_run.status == "completed":
                    raise ValueError("Batch run already completed")
                if batch_run.is_cancelled:
                    raise ValueError("Batch run was cancelled")

                batch_run.status = "running"
                batch_run.last_progress_at = datetime.utcnow()
                if not batch_run.started_at:
                    batch_run.started_at = datetime.utcnow()
                await session.commit()

            self._active_experiments[batch_run_id] = set()
            task = asyncio.create_task(self._run_batch_parallel(batch_run_id))
            self._running_batches[batch_run_id] = task
            task.add_done_callback(lambda t: self._on_batch_done(batch_run_id, t))

    async def _run_batch_parallel(self, batch_run_id: int):
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
                max_parallel = batch_run.max_parallel or 1

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

            start_index = batch_run.current_index if batch_run.current_index > 0 else 0
            next_index = start_index
            completed_count = 0
            failed_count = 0

            async with self._lock:
                for idx in range(start_index, min(start_index + max_parallel, len(experiment_ids))):
                    if idx < len(experiment_ids):
                        await self._submit_experiment(batch_run_id, idx, experiment_ids[idx], param_combinations, env_config)
                        next_index = idx + 1

            while True:
                await asyncio.sleep(2)

                async with async_session() as session:
                    batch_run = await session.get(BatchRunModel, batch_run_id)
                    if not batch_run or batch_run.is_cancelled:
                        break

                finished_experiments = []
                async with self._lock:
                    active_set = self._active_experiments.get(batch_run_id, set())
                    for exp_idx in list(active_set):
                        if exp_idx < len(experiment_ids):
                            exp_id = experiment_ids[exp_idx]
                            task = training_manager.get_task(exp_id)
                            if not task or task.status in ("completed", "stopped", "error"):
                                finished_experiments.append((exp_idx, exp_id, task.status if task else "completed"))

                    for exp_idx, exp_id, status in finished_experiments:
                        self._active_experiments[batch_run_id].discard(exp_idx)
                        if status == "error":
                            failed_count += 1
                        else:
                            completed_count += 1

                    if next_index < len(experiment_ids):
                        while len(self._active_experiments.get(batch_run_id, set())) < max_parallel and next_index < len(experiment_ids):
                            await self._submit_experiment(batch_run_id, next_index, experiment_ids[next_index], param_combinations, env_config)
                            next_index += 1

                async with async_session() as session:
                    batch_run = await session.get(BatchRunModel, batch_run_id)
                    if batch_run:
                        batch_run.current_index = next_index - 1 if next_index > 0 else 0
                        batch_run.last_progress_at = datetime.utcnow()
                        await session.commit()

                if failed_count > 0:
                    async with async_session() as session:
                        batch_run = await session.get(BatchRunModel, batch_run_id)
                        if batch_run:
                            batch_run.status = "failed"
                            batch_run.error_message = f"Experiment failed"
                            batch_run.finished_at = datetime.utcnow()
                            await session.commit()
                    return

                if next_index >= len(experiment_ids) and len(self._active_experiments.get(batch_run_id, set())) == 0:
                    break

            async with async_session() as session:
                batch_run = await session.get(BatchRunModel, batch_run_id)
                if batch_run and not batch_run.is_cancelled:
                    batch_run.status = "completed"
                    batch_run.current_index = len(experiment_ids) - 1
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

    async def _submit_experiment(self, batch_run_id: int, idx: int, exp_id: int, param_combinations: list, env_config: dict):
        async with async_session() as session:
            exp = await session.get(ExpModel, exp_id)
            if not exp or exp.status in ("completed", "error", "stopped"):
                return

            combo = param_combinations[idx] if idx < len(param_combinations) else {}

            hyperparams = exp.hyperparams if isinstance(exp.hyperparams, dict) else {}
            if "algorithm" not in hyperparams:
                hyperparams["algorithm"] = exp.algorithm

            task = TrainingTask(exp_id, env_config, hyperparams, exp.total_episodes)
            await training_manager.submit_task(task)
            self._active_experiments.setdefault(batch_run_id, set()).add(idx)

    def _on_batch_done(self, batch_run_id: int, task: asyncio.Task):
        async def _cleanup():
            async with self._lock:
                if batch_run_id in self._running_batches:
                    del self._running_batches[batch_run_id]
                if batch_run_id in self._active_experiments:
                    del self._active_experiments[batch_run_id]
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

    async def get_batch_stats(self, batch_run_id: int, db: AsyncSession, heatmap_var_a: Optional[str] = None, heatmap_var_b: Optional[str] = None) -> dict:
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

        parallel_coords_data = None
        if completed_exps:
            var_keys = list(param_variables.keys())
            var_names = [k.split("/")[-1] for k in var_keys]
            coords = []
            best_reward = max(e["final_reward"] for e in completed_exps) if completed_exps else 0
            for exp_data in completed_exps:
                item = {}
                for i, key in enumerate(var_keys):
                    val = exp_data["params"].get(key)
                    if isinstance(val, (int, float)):
                        item[var_names[i]] = float(val)
                    else:
                        item[var_names[i]] = str(val)
                item["reward"] = exp_data["final_reward"]
                item["is_best"] = exp_data["final_reward"] == best_reward
                item["experiment_id"] = exp_data["id"]
                coords.append(item)
            parallel_coords_data = coords

        heatmap_data = None
        if completed_exps and len(param_variables) >= 2:
            var_keys = list(param_variables.keys())
            if heatmap_var_a and heatmap_var_a in param_variables:
                var_a_path = heatmap_var_a
            else:
                var_a_path = var_keys[0]
            if heatmap_var_b and heatmap_var_b in param_variables:
                var_b_path = heatmap_var_b
            else:
                var_b_path = var_keys[1] if len(var_keys) > 1 else var_keys[0]

            var_a_name = var_a_path.split("/")[-1]
            var_b_name = var_b_path.split("/")[-1]

            a_values = sorted(param_variables.get(var_a_path, []), key=lambda x: (not isinstance(x, (int, float)), x))
            b_values = sorted(param_variables.get(var_b_path, []), key=lambda x: (not isinstance(x, (int, float)), x))

            cells = {}
            for exp_data in completed_exps:
                a_val = exp_data["params"].get(var_a_path)
                b_val = exp_data["params"].get(var_b_path)
                if a_val is not None and b_val is not None and exp_data["final_reward"] is not None:
                    key = (str(a_val), str(b_val))
                    if key not in cells:
                        cells[key] = []
                    cells[key].append(exp_data["final_reward"])

            matrix = []
            for a_val in a_values:
                row = []
                for b_val in b_values:
                    key = (str(a_val), str(b_val))
                    rewards = cells.get(key, [])
                    avg = sum(rewards) / len(rewards) if rewards else None
                    row.append(round(avg, 4) if avg is not None else None)
                matrix.append(row)

            heatmap_data = {
                "var_a": var_a_name,
                "var_b": var_b_name,
                "var_a_path": var_a_path,
                "var_b_path": var_b_path,
                "a_values": [str(v) for v in a_values],
                "b_values": [str(v) for v in b_values],
                "matrix": matrix,
                "available_variables": [{"path": k, "name": k.split("/")[-1]} for k in param_variables.keys()],
            }

        is_stale = False
        if batch_run.status == "running" and batch_run.last_progress_at:
            stale_time = datetime.utcnow() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
            if batch_run.last_progress_at < stale_time:
                is_stale = True

        return {
            "batch_run_id": batch_run.id,
            "status": batch_run.status,
            "max_parallel": batch_run.max_parallel,
            "template_version": batch_run.template_version,
            "total_experiments": len(experiment_ids),
            "completed_count": completed_count,
            "running_count": running_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "experiments": experiments,
            "group_stats": group_stats,
            "best_combination": best_combination,
            "total_duration_seconds": total_duration,
            "parallel_coords_data": parallel_coords_data,
            "heatmap_data": heatmap_data,
            "is_stale": is_stale,
            "last_progress_at": batch_run.last_progress_at.isoformat() if batch_run.last_progress_at else None,
        }

    async def is_batch_stale(self, batch_run_id: int, db: AsyncSession) -> bool:
        batch_run = await db.get(BatchRunModel, batch_run_id)
        if not batch_run:
            return False
        if batch_run.status != "running":
            return False
        if not batch_run.last_progress_at:
            return True
        stale_time = datetime.utcnow() - timedelta(minutes=STALE_THRESHOLD_MINUTES)
        return batch_run.last_progress_at < stale_time


batch_run_manager = BatchRunManager()
