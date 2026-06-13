from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import Evaluation as EvalModel, Experiment
from app.schemas.schemas import EvaluationCreate, EvaluationResponse
from app.services.evaluation import run_evaluation

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


@router.post("", response_model=EvaluationResponse)
async def create_evaluation(data: EvaluationCreate, db: AsyncSession = Depends(get_db)):
    exp = await db.get(Experiment, data.experiment_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    if exp.status != "completed":
        raise HTTPException(400, "Experiment must be completed before evaluation")

    result = await run_evaluation(data.experiment_id, data.num_episodes)
    return result


@router.get("", response_model=list[EvaluationResponse])
async def list_evaluations(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(EvalModel).offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{eval_id}", response_model=EvaluationResponse)
async def get_evaluation(eval_id: int, db: AsyncSession = Depends(get_db)):
    ev = await db.get(EvalModel, eval_id)
    if not ev:
        raise HTTPException(404, "Evaluation not found")
    return ev


@router.get("/{eval_id}/replay/{episode_idx}")
async def get_replay_data(eval_id: int, episode_idx: int, db: AsyncSession = Depends(get_db)):
    ev = await db.get(EvalModel, eval_id)
    if not ev:
        raise HTTPException(404, "Evaluation not found")

    episode_data = ev.episode_data if isinstance(ev.episode_data, list) else []
    if episode_idx < 0 or episode_idx >= len(episode_data):
        raise HTTPException(400, f"Episode index {episode_idx} out of range")

    return episode_data[episode_idx]
