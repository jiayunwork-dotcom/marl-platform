import ast
import json
import torch
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Experiment as ExpModel, TrainingLog, Checkpoint, Environment
from app.schemas.schemas import ExperimentCreate, ExperimentResponse, TrainingLogResponse
from app.services.training import TrainingManager, TrainingTask, training_manager

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _safe_parse_json(value):
    """Robust JSON parsing that also handles Python dict repr (single quotes)."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
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


@router.post("", response_model=ExperimentResponse)
async def create_experiment(data: ExperimentCreate, db: AsyncSession = Depends(get_db)):
    env = await db.get(Environment, data.environment_id)
    if not env:
        raise HTTPException(404, "Environment not found")

    algo_config = data.algorithm_config.model_dump()
    exp = ExpModel(
        name=data.name,
        environment_id=data.environment_id,
        algorithm=algo_config["algorithm"],
        hyperparams=algo_config,
        communication_enabled=algo_config.get("communication_enabled", False),
        total_episodes=data.total_episodes,
    )
    db.add(exp)
    await db.commit()
    await db.refresh(exp)
    return exp


@router.get("", response_model=list[ExperimentResponse])
async def list_experiments(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ExpModel).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{exp_id}", response_model=ExperimentResponse)
async def get_experiment(exp_id: int, db: AsyncSession = Depends(get_db)):
    exp = await db.get(ExpModel, exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return exp


@router.post("/{exp_id}/start")
async def start_training(exp_id: int, db: AsyncSession = Depends(get_db)):
    exp = await db.get(ExpModel, exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp.status in ("running", "queued"):
        raise HTTPException(400, f"Experiment already {exp.status}")

    env = await db.get(Environment, exp.environment_id)
    if not env:
        raise HTTPException(404, "Environment not found")

    env_config = {
        "map_config": _safe_parse_json(env.map_config),
        "max_steps": env.max_steps,
        "obs_range": env.obs_range,
        "action_space": env.action_space,
        "collision_rule": env.collision_rule,
        "resource_refresh": env.resource_refresh,
        "resource_refresh_interval": env.resource_refresh_interval,
        "agent_count": env.agent_count,
        "team_config": _safe_parse_json(env.team_config),
        "reward_goal": env.reward_goal,
        "reward_resource": env.reward_resource,
        "reward_collision": env.reward_collision,
        "reward_wall": env.reward_wall,
        "reward_step": env.reward_step,
        "reward_catch_predator": env.reward_catch_predator,
        "reward_catch_prey": env.reward_catch_prey,
        "reward_timeout": env.reward_timeout,
    }

    algo_config = _safe_parse_json(exp.hyperparams)
    if "algorithm" not in algo_config:
        algo_config["algorithm"] = exp.algorithm

    task = TrainingTask(exp_id, env_config, algo_config, exp.total_episodes)
    exp.status = "queued"
    await db.commit()

    await training_manager.submit_task(task)
    return {"status": "started", "experiment_id": exp_id}


@router.post("/{exp_id}/pause")
async def pause_training(exp_id: int):
    task = training_manager.get_task(exp_id)
    if not task:
        raise HTTPException(404, "Training task not found")
    task.pause()
    return {"status": "paused"}


@router.post("/{exp_id}/resume")
async def resume_training(exp_id: int):
    task = training_manager.get_task(exp_id)
    if not task:
        raise HTTPException(404, "Training task not found")
    task.resume()
    return {"status": "resumed"}


@router.post("/{exp_id}/stop")
async def stop_training(exp_id: int):
    task = training_manager.get_task(exp_id)
    if not task:
        raise HTTPException(404, "Training task not found")
    task.stop()
    return {"status": "stopped"}


@router.get("/{exp_id}/logs", response_model=list[TrainingLogResponse])
async def get_training_logs(exp_id: int, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TrainingLog).where(TrainingLog.experiment_id == exp_id)
        .order_by(TrainingLog.episode).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{exp_id}/progress")
async def get_training_progress(exp_id: int):
    task = training_manager.get_task(exp_id)
    if task:
        return {
            "status": task.status,
            "current_episode": task.current_episode,
            "total_episodes": task.total_episodes,
            "recent_data": task.episode_data[-5:] if task.episode_data else [],
        }
    return {"status": "not_found", "current_episode": 0, "total_episodes": 0, "recent_data": []}


@router.get("/{exp_id}/checkpoints")
async def get_checkpoints(exp_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Checkpoint).where(Checkpoint.experiment_id == exp_id)
        .order_by(Checkpoint.episode)
    )
    ckpts = result.scalars().all()
    return [{"id": c.id, "episode": c.episode, "filepath": c.filepath, "created_at": c.created_at.isoformat()} for c in ckpts]
