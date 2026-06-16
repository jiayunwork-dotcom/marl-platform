import ast
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

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
    BatchRunStatsResponse,
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
            max_parallel=data.max_parallel,
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


@router.post("/{batch_run_id}/resume")
async def resume_batch_run(batch_run_id: int, db: AsyncSession = Depends(get_db)):
    batch_run = await db.get(BatchRunModel, batch_run_id)
    if not batch_run:
        raise HTTPException(404, "Batch run not found")

    try:
        await batch_run_manager.resume_batch_run(batch_run_id)
        return {"status": "resumed", "batch_run_id": batch_run_id}
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
async def get_batch_run_stats(
    batch_run_id: int,
    heatmap_var_a: str = Query(None),
    heatmap_var_b: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        stats = await batch_run_manager.get_batch_stats(batch_run_id, db, heatmap_var_a, heatmap_var_b)
        return stats
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/preview", response_model=BatchRunPreviewResponse)
async def preview_batch_run(
    data: dict,
    db: AsyncSession = Depends(get_db),
):
    template_id = data.get("template_id")
    max_parallel = data.get("max_parallel", 1)
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

    estimated_duration = None
    try:
        from sqlalchemy import func

        result = await db.execute(
            select(ExpModel).where(
                ExpModel.status == "completed",
                ExpModel.total_episodes == template.total_episodes,
                ExpModel.started_at.isnot(None),
                ExpModel.finished_at.isnot(None),
            ).limit(100)
        )
        recent_exps = result.scalars().all()

        if recent_exps:
            total_seconds = 0.0
            count = 0
            for exp in recent_exps:
                if isinstance(exp.started_at, datetime) and isinstance(exp.finished_at, datetime):
                    delta = (exp.finished_at - exp.started_at).total_seconds()
                    if delta > 0:
                        total_seconds += delta
                        count += 1
            if count > 0:
                avg_seconds = total_seconds / count
                max_parallel_val = max(1, min(int(max_parallel), 4))
                estimated_duration = avg_seconds * len(combinations) / max_parallel_val
    except Exception as e:
        pass

    return {
        "total_combinations": len(combinations),
        "param_combinations": combinations,
        "estimated_duration_seconds": estimated_duration,
    }


@router.get("/template/{template_id}")
async def list_batch_runs_by_template(
    template_id: int,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    current = await db.get(TemplateModel, template_id)
    if not current:
        raise HTTPException(404, "Template not found")

    if current.parent_template_id:
        root_id = current.parent_template_id
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
    all_version_ids = [v.id for v in all_versions]

    result = await db.execute(
        select(BatchRunModel)
        .where(BatchRunModel.template_id.in_(all_version_ids))
        .order_by(BatchRunModel.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
