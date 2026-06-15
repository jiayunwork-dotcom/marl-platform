import ast
import json
import numpy as np
import torch
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.models import Experiment, TrainingLog, Evaluation, Environment, Checkpoint
from app.schemas.schemas import ComparisonRequest
from app.services.report import generate_comparison_report
from app.core.environment import GridWorldEnv
from app.algorithms.factory import create_algorithm

router = APIRouter(prefix="/api/visualization", tags=["visualization"])


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


@router.get("/{exp_id}/trajectory-heatmap")
async def get_trajectory_heatmap(exp_id: int, db: AsyncSession = Depends(get_db)):
    exp = await db.get(Experiment, exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    env_row = await db.get(Environment, exp.environment_id)
    if not env_row:
        raise HTTPException(404, "Environment not found")

    map_config = env_row.map_config if isinstance(env_row.map_config, dict) else json.loads(env_row.map_config)
    width, height = map_config["width"], map_config["height"]
    n_agents = env_row.agent_count

    heatmaps = [np.zeros((height, width)) for _ in range(n_agents)]

    evals = await db.execute(
        select(Evaluation).where(Evaluation.experiment_id == exp_id)
    )
    evaluations = evals.scalars().all()

    for ev in evaluations:
        ep_data = ev.episode_data if isinstance(ev.episode_data, list) else []
        for ep in ep_data:
            for step in ep.get("steps", []):
                positions = step.get("agent_positions", [])
                for i, pos in enumerate(positions):
                    if i < n_agents:
                        y, x = pos[0], pos[1]
                        if 0 <= y < height and 0 <= x < width:
                            heatmaps[i][y][x] += 1

    for i in range(n_agents):
        mx = heatmaps[i].max()
        if mx > 0:
            heatmaps[i] = heatmaps[i] / mx

    return {
        "heatmaps": [h.tolist() for h in heatmaps],
        "width": width, "height": height, "n_agents": n_agents,
    }


@router.get("/{exp_id}/q-value-map")
async def get_q_value_map(exp_id: int, agent_id: int = 0, db: AsyncSession = Depends(get_db)):
    exp = await db.get(Experiment, exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    env_row = await db.get(Environment, exp.environment_id)
    if not env_row:
        raise HTTPException(404, "Environment not found")

    ckpts = await db.execute(
        select(Checkpoint).where(Checkpoint.experiment_id == exp_id)
        .order_by(Checkpoint.episode.desc()).limit(1)
    )
    latest_ckpt = ckpts.scalars().first()
    if not latest_ckpt:
        raise HTTPException(404, "No checkpoint found")

    map_config = _safe_parse_json(env_row.map_config)
    algo_config = _safe_parse_json(exp.hyperparams)
    if "algorithm" not in algo_config:
        algo_config["algorithm"] = exp.algorithm

    width, height = map_config["width"], map_config["height"]

    env = GridWorldEnv(
        map_config=map_config,
        max_steps=env_row.max_steps,
        obs_range=env_row.obs_range,
        action_space=env_row.action_space,
        collision_rule=env_row.collision_rule,
        resource_refresh=env_row.resource_refresh,
        resource_refresh_interval=env_row.resource_refresh_interval,
        agent_count=env_row.agent_count,
        team_config=_safe_parse_json(env_row.team_config),
    )

    obs_shape = env.get_obs_shape()
    n_actions = env.action_space
    n_agents = env.agent_count

    algorithm = create_algorithm(algo_config.get("algorithm", exp.algorithm), n_agents, obs_shape, n_actions, algo_config)
    state = torch.load(latest_ckpt.filepath, map_location="cpu")
    algorithm.load_state_dict(state)

    q_map = np.zeros((height, width))
    obs = env.reset()
    for y in range(height):
        for x in range(width):
            env.agent_positions[agent_id] = (y, x)
            obs_data = env._get_obs()
            q_vals = algorithm.get_q_values(agent_id, obs_data[agent_id])
            q_map[y][x] = np.max(q_vals)

    mx = q_map.max()
    if mx > 0:
        q_map = q_map / mx

    return {"q_map": q_map.tolist(), "width": width, "height": height}


@router.post("/comparison")
async def compare_experiments(data: ComparisonRequest, db: AsyncSession = Depends(get_db)):
    return await generate_comparison_report(data.experiment_ids)


@router.get("/{exp_id}/learning-curves")
async def get_learning_curves(
    exp_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(0, ge=0, le=100000),
    db: AsyncSession = Depends(get_db),
):
    count_q = select(func.count(TrainingLog.id)).where(
        TrainingLog.experiment_id == exp_id
    )
    total_result = await db.execute(count_q)
    total_count = total_result.scalar() or 0

    q = (
        select(TrainingLog)
        .where(TrainingLog.experiment_id == exp_id)
        .order_by(TrainingLog.episode)
    )
    if limit > 0:
        q = q.offset(offset).limit(limit)

    logs = await db.execute(q)
    log_list = logs.scalars().all()

    episodes = [l.episode for l in log_list]
    total_rewards = [l.total_reward for l in log_list]
    steps = [l.steps for l in log_list]
    win_rates = [l.win_rate for l in log_list]
    agent_rewards = [_safe_parse_json(l.agent_rewards) for l in log_list]

    return {
        "total_count": total_count,
        "episodes": episodes,
        "total_rewards": total_rewards,
        "steps": steps,
        "win_rates": win_rates,
        "agent_rewards": agent_rewards,
    }


@router.get("/compare-curves")
async def compare_learning_curves(
    exp_ids: str = Query(..., description="Comma-separated experiment IDs"),
    db: AsyncSession = Depends(get_db),
):
    ids = [int(x.strip()) for x in exp_ids.split(",")]
    results = {}
    for eid in ids:
        logs = await db.execute(
            select(TrainingLog).where(TrainingLog.experiment_id == eid)
            .order_by(TrainingLog.episode)
        )
        log_list = logs.scalars().all()
        exp = await db.get(Experiment, eid)
        results[eid] = {
            "name": exp.name if exp else f"Exp {eid}",
            "algorithm": exp.algorithm if exp else "Unknown",
            "episodes": [l.episode for l in log_list],
            "total_rewards": [l.total_reward for l in log_list],
            "win_rates": [l.win_rate for l in log_list],
        }
    return results
