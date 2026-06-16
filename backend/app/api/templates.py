import ast
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.dialects.postgresql import JSONB

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
    TemplateRollbackRequest,
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


def _safe_parse_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            try:
                return ast.literal_eval(value)
            except (ValueError, SyntaxError):
                return []
    return []


@router.post("", response_model=ExperimentTemplateResponse)
async def create_template(data: ExperimentTemplateCreate, db: AsyncSession = Depends(get_db)):
    env = await db.get(Environment, data.environment_id)
    if not env:
        raise HTTPException(404, f"Environment {data.environment_id} not found")

    template = TemplateModel(
        name=data.name,
        description=data.description,
        tags=data.tags,
        algorithm=data.algorithm,
        hyperparams=data.hyperparams,
        communication_enabled=data.communication_enabled,
        environment_id=data.environment_id,
        agent_count=data.agent_count,
        total_episodes=data.total_episodes,
        param_variables=data.param_variables,
        version_number=1,
        is_current_version=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("", response_model=list[ExperimentTemplateResponse])
async def list_templates(
    skip: int = 0,
    limit: int = 50,
    tags: str = Query(None),
    keyword: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(TemplateModel).where(TemplateModel.is_current_version == True)

    if keyword:
        like_pattern = f"%{keyword}%"
        query = query.where(
            or_(
                TemplateModel.name.ilike(like_pattern),
                TemplateModel.description.ilike(like_pattern),
            )
        )

    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            try:
                from sqlalchemy import func
                for tag in tag_list:
                    query = query.where(func.jsonb_path_exists(TemplateModel.tags, f'$[*] ? (@ == "{tag}")'))
            except Exception:
                pass

    query = query.order_by(TemplateModel.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{template_id}", response_model=ExperimentTemplateResponse)
async def get_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return template


@router.get("/{template_id}/versions", response_model=list[ExperimentTemplateResponse])
async def get_template_versions(template_id: int, db: AsyncSession = Depends(get_db)):
    current = await db.get(TemplateModel, template_id)
    if not current:
        raise HTTPException(404, "Template not found")

    if current.parent_template_id:
        root_id = current.parent_template_id
    else:
        root_id = template_id

    result = await db.execute(
        select(TemplateModel)
        .where(
            or_(
                TemplateModel.id == root_id,
                TemplateModel.parent_template_id == root_id,
            )
        )
        .order_by(TemplateModel.version_number.desc())
    )
    return result.scalars().all()


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
    if not update_data:
        return template

    if template.parent_template_id:
        root_id = template.parent_template_id
        current_root = await db.get(TemplateModel, root_id)
    else:
        root_id = template_id
        current_root = template

    if current_root:
        current_root.is_current_version = False

    result = await db.execute(
        select(TemplateModel).where(
            or_(
                TemplateModel.id == root_id,
                TemplateModel.parent_template_id == root_id,
            )
        )
    )
    all_versions = result.scalars().all()
    max_version = max((v.version_number for v in all_versions), default=0)

    new_template = TemplateModel(
        name=update_data.get("name", template.name),
        description=update_data.get("description", template.description),
        tags=update_data.get("tags", _safe_parse_list(template.tags)),
        algorithm=update_data.get("algorithm", template.algorithm),
        hyperparams=update_data.get("hyperparams", _safe_parse_json(template.hyperparams)),
        communication_enabled=update_data.get("communication_enabled", template.communication_enabled),
        environment_id=update_data.get("environment_id", template.environment_id),
        agent_count=update_data.get("agent_count", template.agent_count),
        total_episodes=update_data.get("total_episodes", template.total_episodes),
        param_variables=update_data.get("param_variables", _safe_parse_json(template.param_variables)),
        version_number=max_version + 1,
        is_current_version=True,
        parent_template_id=root_id,
    )
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)
    return new_template


@router.post("/{template_id}/rollback")
async def rollback_template(
    template_id: int,
    data: TemplateRollbackRequest,
    db: AsyncSession = Depends(get_db),
):
    current = await db.get(TemplateModel, template_id)
    if not current:
        raise HTTPException(404, "Template not found")

    if current.parent_template_id:
        root_id = current.parent_template_id
    else:
        root_id = template_id

    target_version = await db.get(TemplateModel, data.version_id)
    if not target_version:
        raise HTTPException(404, "Target version not found")

    is_valid_version = (
        target_version.id == root_id
        or target_version.parent_template_id == root_id
    )
    if not is_valid_version:
        raise HTTPException(400, "Target version does not belong to this template")

    result = await db.execute(
        select(TemplateModel).where(
            or_(
                TemplateModel.id == root_id,
                TemplateModel.parent_template_id == root_id,
            )
        )
    )
    all_versions = result.scalars().all()
    for v in all_versions:
        v.is_current_version = False

    max_version = max((v.version_number for v in all_versions), default=0)

    new_template = TemplateModel(
        name=target_version.name,
        description=target_version.description,
        tags=_safe_parse_list(target_version.tags),
        algorithm=target_version.algorithm,
        hyperparams=_safe_parse_json(target_version.hyperparams),
        communication_enabled=target_version.communication_enabled,
        environment_id=target_version.environment_id,
        agent_count=target_version.agent_count,
        total_episodes=target_version.total_episodes,
        param_variables=_safe_parse_json(target_version.param_variables),
        version_number=max_version + 1,
        is_current_version=True,
        parent_template_id=root_id,
    )
    db.add(new_template)
    await db.commit()
    await db.refresh(new_template)
    return ExperimentTemplateResponse.model_validate(new_template)


@router.delete("/{template_id}")
async def delete_template(template_id: int, db: AsyncSession = Depends(get_db)):
    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    if template.parent_template_id:
        root_id = template.parent_template_id
    else:
        root_id = template_id

    result = await db.execute(
        select(TemplateModel).where(
            or_(
                TemplateModel.id == root_id,
                TemplateModel.parent_template_id == root_id,
            )
        )
    )
    all_versions = result.scalars().all()
    for v in all_versions:
        await db.delete(v)

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
        tags=[],
        algorithm=exp.algorithm,
        hyperparams=hyperparams,
        communication_enabled=exp.communication_enabled,
        environment_id=exp.environment_id,
        agent_count=agent_count,
        total_episodes=exp.total_episodes,
        param_variables={},
        version_number=1,
        is_current_version=True,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template
