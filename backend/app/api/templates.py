import ast
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    ExperimentTemplate as TemplateModel,
    Experiment as ExpModel,
    Environment,
)
from app.schemas.schemas import (
    ExperimentTemplateCreate,
    ExperimentTemplateUpdate,
    ExperimentTemplateResponse,
    CreateTemplateFromExperimentRequest,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


def _safe_parse_json(value):
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


@router.post("", response_model=ExperimentTemplateResponse)
async def create_template(data: ExperimentTemplateCreate, db: AsyncSession = Depends(get_db)):
    env = await db.get(Environment, data.environment_id)
    if not env:
        raise HTTPException(404, f"Environment {data.environment_id} not found")

    template = TemplateModel(
        name=data.name,
        description=data.description,
        algorithm=data.algorithm,
        hyperparams=data.hyperparams,
        communication_enabled=data.communication_enabled,
        environment_id=data.environment_id,
        agent_count=data.agent_count,
        total_episodes=data.total_episodes,
        param_variables=data.param_variables,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("", response_model=list[ExperimentTemplateResponse])
async def list_templates(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TemplateModel).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{template_id}", response_model=ExperimentTemplateResponse)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return template


@router.put("/{template_id}", response_model=ExperimentTemplateResponse)
async def update_template(
    template_id: int,
    data: ExperimentTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    await db.delete(template)
    await db.commit()
    return {"status": "deleted"}


@router.post("/from-experiment", response_model=ExperimentTemplateResponse)
async def create_template_from_experiment(
    data: CreateTemplateFromExperimentRequest,
    db: AsyncSession = Depends(get_db),
):
    exp = await db.get(ExpModel, data.experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    hyperparams = _safe_parse_json(exp.hyperparams)
    if "algorithm" not in hyperparams:
        hyperparams["algorithm"] = exp.algorithm

    env = await db.get(Environment, exp.environment_id)
    agent_count = env.agent_count if env else 2

    template = TemplateModel(
        name=data.name,
        description=data.description,
        algorithm=exp.algorithm,
        hyperparams=hyperparams,
        communication_enabled=exp.communication_enabled,
        environment_id=exp.environment_id,
        agent_count=agent_count,
        total_episodes=exp.total_episodes,
        param_variables={},
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template
