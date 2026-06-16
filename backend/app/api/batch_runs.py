import ast
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    ExperimentTemplate as TemplateModel,
    BatchRun as BatchRunModel,
    Experiment as ExpModel,
    Environment,
)
from app.schemas.schemas import (
    BatchRunCreate,
    BatchRunResponse,
    BatchRunPreviewResponse,
)
from app.services.batch_run import (
    batch_run_manager,
    generate_grid_combinations,
    validate_param_variables,
    MAX_COMBINATIONS,
)

router = APIRouter(prefix="/api/batch-runs", tags=["batch-runs"])


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


@router.post("", response_model=BatchRunResponse)
async def create_batch_run(data: BatchRunCreate, db: AsyncSession = Depends(get_db)):
    try:
        batch_run = await batch_run_manager.create_batch_run(
            template_id=data.template_id,
            name=data.name,
            db=db,
        )
        return batch_run
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("", response_model=list[BatchRunResponse])
async def list_batch_runs(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BatchRunModel).order_by(BatchRunModel.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{batch_run_id}", response_model=BatchRunResponse)
async def get_batch_run(batch_run_id: int, db: AsyncSession = Depends(get_db)):
    batch_run = await db.get(BatchRunModel, batch_run_id)
    if not batch_run:
        raise HTTPException(404, "Batch run not found")
    return batch_run


@router.post("/{batch_run_id}/start")
async def start_batch_run(batch_run_id: int, db: AsyncSession = Depends(get_db)):
    batch_run = await db.get(BatchRunModel, batch_run_id)
    if not batch_run:
        raise HTTPException(404, "Batch run not found")

    try:
        await batch_run_manager.start_batch_run(batch_run_id)
        return {"status": "started", "batch_run_id": batch_run_id}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{batch_run_id}/cancel")
async def cancel_batch_run(batch_run_id: int):
    try:
        await batch_run_manager.cancel_batch_run(batch_run_id)
        return {"status": "cancelled"}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{batch_run_id}/stats")
async def get_batch_run_stats(batch_run_id: int, db: AsyncSession = Depends(get_db)):
    try:
        stats = await batch_run_manager.get_batch_stats(batch_run_id, db)
        return stats
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/preview", response_model=BatchRunPreviewResponse)
async def preview_batch_run(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    template_id = data.get("template_id")
    if not template_id:
        raise HTTPException(400, "template_id is required")

    template = await db.get(TemplateModel, template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    env = await db.get(Environment, template.environment_id)
    if not env:
        raise HTTPException(400, f"Environment {template.environment_id} not found")

    param_variables = _safe_parse_json(template.param_variables)

    errors = validate_param_variables(template, param_variables)
    if errors:
        raise HTTPException(400, "参数变量校验失败: " + "; ".join(errors))

    combinations = generate_grid_combinations(param_variables)
    if len(combinations) > MAX_COMBINATIONS:
        raise HTTPException(
            400,
            f"参数组合总数不能超过 {MAX_COMBINATIONS} 个，当前为 {len(combinations)} 个",
        )

    return {
        "total_combinations": len(combinations),
        "param_combinations": combinations,
    }


@router.get("/template/{template_id}")
async def list_batch_runs_by_template(
    template_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BatchRunModel)
        .where(BatchRunModel.template_id == template_id)
        .order_by(BatchRunModel.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
