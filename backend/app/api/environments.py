import json
import os
import torch
import numpy as np
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Environment as EnvModel
from app.schemas.schemas import (
    EnvironmentCreate, EnvironmentResponse, PresetScenarioRequest,
)
from app.core.presets import PRESET_GENERATORS
from app.core.config import settings

router = APIRouter(prefix="/api/environments", tags=["environments"])


@router.post("", response_model=EnvironmentResponse)
async def create_environment(data: EnvironmentCreate, db: AsyncSession = Depends(get_db)):
    map_config = data.map_config.model_dump()
    env = EnvModel(
        name=data.name,
        description=data.description,
        map_config=map_config,
        width=map_config["width"],
        height=map_config["height"],
        max_steps=data.max_steps,
        obs_range=data.obs_range,
        action_space=data.action_space,
        collision_rule=data.collision_rule,
        resource_refresh=data.resource_refresh,
        resource_refresh_interval=data.resource_refresh_interval,
        reward_goal=data.reward_goal,
        reward_resource=data.reward_resource,
        reward_collision=data.reward_collision,
        reward_wall=data.reward_wall,
        reward_step=data.reward_step,
        reward_catch_predator=data.reward_catch_predator,
        reward_catch_prey=data.reward_catch_prey,
        reward_timeout=data.reward_timeout,
        scenario_type=data.scenario_type,
        agent_count=data.agent_count,
        team_config=data.team_config,
    )
    db.add(env)
    await db.commit()
    await db.refresh(env)
    return env


@router.get("", response_model=list[EnvironmentResponse])
async def list_environments(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EnvModel).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{env_id}", response_model=EnvironmentResponse)
async def get_environment(env_id: int, db: AsyncSession = Depends(get_db)):
    env = await db.get(EnvModel, env_id)
    if not env:
        raise HTTPException(404, "Environment not found")
    return env


@router.put("/{env_id}", response_model=EnvironmentResponse)
async def update_environment(env_id: int, data: EnvironmentCreate, db: AsyncSession = Depends(get_db)):
    env = await db.get(EnvModel, env_id)
    if not env:
        raise HTTPException(404, "Environment not found")
    map_config = data.map_config.model_dump()
    for key, value in data.model_dump().items():
        if key == "map_config":
            setattr(env, key, map_config)
        else:
            setattr(env, key, value)
    env.width = map_config["width"]
    env.height = map_config["height"]
    await db.commit()
    await db.refresh(env)
    return env


@router.delete("/{env_id}")
async def delete_environment(env_id: int, db: AsyncSession = Depends(get_db)):
    env = await db.get(EnvModel, env_id)
    if not env:
        raise HTTPException(404, "Environment not found")
    await db.delete(env)
    await db.commit()
    return {"status": "deleted"}


@router.post("/preset")
async def create_preset(data: PresetScenarioRequest, db: AsyncSession = Depends(get_db)):
    generator = PRESET_GENERATORS.get(data.scenario_type)
    if not generator:
        raise HTTPException(400, f"Unknown scenario: {data.scenario_type}")
    map_config = generator(data.map_size, data.agent_count, data.team_config)
    env = EnvModel(
        name=f"Preset: {data.scenario_type}",
        description=f"Auto-generated {data.scenario_type} scenario",
        map_config=map_config,
        width=data.map_size,
        height=data.map_size,
        scenario_type=data.scenario_type,
        agent_count=data.agent_count,
        team_config=data.team_config or {},
    )
    db.add(env)
    await db.commit()
    await db.refresh(env)
    return env


@router.post("/{env_id}/save-map")
async def save_map(env_id: int, db: AsyncSession = Depends(get_db)):
    env = await db.get(EnvModel, env_id)
    if not env:
        raise HTTPException(404, "Environment not found")
    filepath = os.path.join(settings.MAP_SAVE_DIR, f"env_{env_id}_map.json")
    with open(filepath, "w") as f:
        json.dump(env.map_config, f, indent=2)
    return {"filepath": filepath, "status": "saved"}


@router.post("/load-map")
async def load_map(filepath: str = Query(...), db: AsyncSession = Depends(get_db)):
    if not os.path.exists(filepath):
        raise HTTPException(404, "Map file not found")
    with open(filepath) as f:
        map_config = json.load(f)
    return {"map_config": map_config}
