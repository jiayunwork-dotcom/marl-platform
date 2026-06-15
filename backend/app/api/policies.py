import asyncio
import time
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.models import PolicyService, InferenceLog, Checkpoint, Experiment
from app.schemas.schemas import (
    PolicyServiceCreate,
    PolicyServiceResponse,
    InferenceRequest,
    InferenceResponse,
    InferenceLogResponse,
    InferenceStatsResponse,
)
from app.services.deployment import deployment_manager

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.post("", response_model=PolicyServiceResponse)
async def create_policy_service(data: PolicyServiceCreate, db: AsyncSession = Depends(get_db)):
    experiment = await db.get(Experiment, data.experiment_id)
    if not experiment:
        raise HTTPException(404, "Experiment not found")

    checkpoint = await db.get(Checkpoint, data.checkpoint_id)
    if not checkpoint:
        raise HTTPException(404, "Checkpoint not found")

    if checkpoint.experiment_id != data.experiment_id:
        raise HTTPException(400, "Checkpoint does not belong to the specified experiment")

    policy = PolicyService(
        name=data.name,
        experiment_id=data.experiment_id,
        checkpoint_id=data.checkpoint_id,
        max_concurrent=data.max_concurrent,
        timeout_ms=data.timeout_ms,
        status="created",
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


@router.get("", response_model=list[PolicyServiceResponse])
async def list_policy_services(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PolicyService).order_by(PolicyService.created_at.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/{policy_id}", response_model=PolicyServiceResponse)
async def get_policy_service(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")
    return policy


@router.post("/{policy_id}/start")
async def start_policy_service(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")
    if policy.status not in ("created", "stopped", "error"):
        raise HTTPException(400, f"Cannot start policy in {policy.status} state")

    policy.status = "deploying"
    policy.error_reason = None
    await db.commit()

    try:
        deployed = await deployment_manager.load_model(policy_id)
        policy.status = "running"
        policy.started_at = datetime.utcnow()
        policy.stopped_at = None
        await db.commit()
        deployment_manager.start_health_checks()
    except Exception as e:
        policy.status = "error"
        policy.error_reason = str(e)
        await db.commit()
        raise HTTPException(500, f"Failed to deploy model: {str(e)}")

    return {"status": "running", "policy_id": policy_id}


@router.post("/{policy_id}/stop")
async def stop_policy_service(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")
    if policy.status not in ("running", "error"):
        raise HTTPException(400, f"Cannot stop policy in {policy.status} state")

    deployment_manager.unload_model(policy_id)
    policy.status = "stopped"
    policy.stopped_at = datetime.utcnow()
    await db.commit()
    return {"status": "stopped", "policy_id": policy_id}


@router.delete("/{policy_id}")
async def delete_policy_service(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")

    if policy.status == "running":
        deployment_manager.unload_model(policy_id)

    await db.delete(policy)
    await db.commit()
    return {"status": "deleted", "policy_id": policy_id}


@router.post("/{policy_id}/infer", response_model=InferenceResponse)
async def infer_policy(policy_id: int, data: InferenceRequest, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")
    if policy.status != "running":
        raise HTTPException(400, f"Policy service is not running (status={policy.status})")

    deployed = deployment_manager.get_deployed(policy_id)
    if deployed is None:
        raise HTTPException(500, "Deployed model not found in memory")

    if len(data.observations) != deployed.n_agents:
        raise HTTPException(
            400,
            f"Expected {deployed.n_agents} agent observations, got {len(data.observations)}",
        )

    start_time = time.time()
    is_timeout = False
    actions = []
    q_values = None

    try:
        loop = asyncio.get_event_loop()
        timeout_sec = policy.timeout_ms / 1000.0
        result = await asyncio.wait_for(
            loop.run_in_executor(None, deployed.infer, data.observations, data.communication_context),
            timeout=timeout_sec,
        )
        actions = result["actions"]
        q_values = result.get("q_values")
    except asyncio.TimeoutError:
        is_timeout = True
        actions = [0] * deployed.n_agents
    except Exception as e:
        is_timeout = False
        actions = [0] * deployed.n_agents
        policy_db = await db.get(PolicyService, policy_id)
        if policy_db and policy_db.status == "running":
            policy_db.error_reason = str(e)
            await db.commit()

    latency_ms = (time.time() - start_time) * 1000.0

    obs_dims = ",".join(str(len(o)) for o in data.observations)
    output_actions_str = ",".join(str(a) for a in actions)

    log = InferenceLog(
        policy_service_id=policy_id,
        request_time=datetime.utcnow(),
        latency_ms=round(latency_ms, 2),
        obs_dimensions=obs_dims,
        output_actions=output_actions_str,
        is_timeout=is_timeout,
    )
    db.add(log)
    await db.commit()

    if is_timeout:
        raise HTTPException(408, f"Inference timeout after {policy.timeout_ms}ms")

    return InferenceResponse(actions=actions, q_values=q_values)


@router.get("/{policy_id}/logs")
async def get_inference_logs(
    policy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")

    conditions = [InferenceLog.policy_service_id == policy_id]
    if start_time:
        try:
            st = datetime.fromisoformat(start_time)
            conditions.append(InferenceLog.request_time >= st)
        except ValueError:
            pass
    if end_time:
        try:
            et = datetime.fromisoformat(end_time)
            conditions.append(InferenceLog.request_time <= et)
        except ValueError:
            pass

    count_q = select(func.count(InferenceLog.id)).where(*conditions)
    total_result = await db.execute(count_q)
    total_count = total_result.scalar() or 0

    q = (
        select(InferenceLog)
        .where(*conditions)
        .order_by(InferenceLog.request_time.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    logs = result.scalars().all()

    return {
        "total_count": total_count,
        "offset": offset,
        "limit": limit,
        "logs": [
            {
                "id": l.id,
                "policy_service_id": l.policy_service_id,
                "request_time": l.request_time.isoformat() if l.request_time else None,
                "latency_ms": l.latency_ms,
                "obs_dimensions": l.obs_dimensions,
                "output_actions": l.output_actions,
                "is_timeout": l.is_timeout,
            }
            for l in logs
        ],
    }


@router.get("/{policy_id}/stats", response_model=InferenceStatsResponse)
async def get_inference_stats(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")

    total_q = await db.execute(
        select(func.count(InferenceLog.id)).where(InferenceLog.policy_service_id == policy_id)
    )
    total_count = total_q.scalar() or 0

    if total_count == 0:
        return InferenceStatsResponse(
            total_count=0, avg_latency_ms=0.0, p95_latency_ms=0.0, timeout_rate=0.0, qps_last_hour=0.0
        )

    avg_q = await db.execute(
        select(func.avg(InferenceLog.latency_ms)).where(InferenceLog.policy_service_id == policy_id)
    )
    avg_latency = float(avg_q.scalar() or 0.0)

    all_latencies_q = await db.execute(
        select(InferenceLog.latency_ms)
        .where(InferenceLog.policy_service_id == policy_id)
        .order_by(InferenceLog.latency_ms)
    )
    all_latencies = [r for (r,) in all_latencies_q.all()]
    p95_idx = int(len(all_latencies) * 0.95)
    p95_latency = float(all_latencies[min(p95_idx, len(all_latencies) - 1)]) if all_latencies else 0.0

    timeout_q = await db.execute(
        select(func.count(InferenceLog.id)).where(
            InferenceLog.policy_service_id == policy_id, InferenceLog.is_timeout == True
        )
    )
    timeout_count = timeout_q.scalar() or 0
    timeout_rate = round(timeout_count / total_count, 4) if total_count > 0 else 0.0

    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    recent_q = await db.execute(
        select(func.count(InferenceLog.id)).where(
            InferenceLog.policy_service_id == policy_id, InferenceLog.request_time >= one_hour_ago
        )
    )
    recent_count = recent_q.scalar() or 0
    qps_last_hour = round(recent_count / 3600.0, 4)

    return InferenceStatsResponse(
        total_count=total_count,
        avg_latency_ms=round(avg_latency, 2),
        p95_latency_ms=round(p95_latency, 2),
        timeout_rate=timeout_rate,
        qps_last_hour=qps_last_hour,
    )
