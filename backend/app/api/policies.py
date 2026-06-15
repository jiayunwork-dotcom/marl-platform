import asyncio
import json
import time
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.models.models import PolicyService, InferenceLog, Checkpoint, Experiment
from app.schemas.schemas import (
    PolicyServiceCreate,
    PolicyServiceResponse,
    PolicyServiceDetailResponse,
    PolicyServiceGroupItem,
    InferenceRequest,
    InferenceResponse,
    InferenceLogResponse,
    InferenceStatsResponse,
    ABTestRequest,
    ABTestResponse,
    ABTestPolicyResult,
    PolicyResourceStats,
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

    max_version_q = await db.execute(
        select(func.max(PolicyService.version)).where(PolicyService.name == data.name)
    )
    max_version = max_version_q.scalar() or 0
    next_version = max_version + 1

    policy = PolicyService(
        name=data.name,
        version=next_version,
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


@router.get("/grouped", response_model=list[PolicyServiceGroupItem])
async def list_policy_services_grouped(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PolicyService).order_by(PolicyService.name.asc(), PolicyService.version.desc())
    )
    all_policies = result.scalars().all()

    groups: dict[str, list[PolicyService]] = {}
    for policy in all_policies:
        if policy.name not in groups:
            groups[policy.name] = []
        groups[policy.name].append(policy)

    return [
        PolicyServiceGroupItem(name=name, versions=policies)
        for name, policies in groups.items()
    ]


@router.get("/{policy_id}", response_model=PolicyServiceDetailResponse)
async def get_policy_service(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")

    history_q = await db.execute(
        select(PolicyService)
        .where(and_(PolicyService.name == policy.name, PolicyService.id != policy_id))
        .order_by(PolicyService.version.desc())
    )
    history_versions = history_q.scalars().all()

    return PolicyServiceDetailResponse(
        id=policy.id,
        name=policy.name,
        version=policy.version,
        experiment_id=policy.experiment_id,
        checkpoint_id=policy.checkpoint_id,
        max_concurrent=policy.max_concurrent,
        timeout_ms=policy.timeout_ms,
        status=policy.status,
        error_reason=policy.error_reason,
        created_at=policy.created_at,
        started_at=policy.started_at,
        stopped_at=policy.stopped_at,
        history_versions=history_versions,
    )


@router.get("/{policy_id}/resource-stats", response_model=PolicyResourceStats)
async def get_policy_resource_stats(policy_id: int, db: AsyncSession = Depends(get_db)):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        raise HTTPException(404, "Policy service not found")

    stats = deployment_manager.get_resource_stats(policy_id)
    if stats is None:
        return PolicyResourceStats(
            policy_id=policy_id,
            current_concurrent=0,
            max_concurrent=policy.max_concurrent,
            queue_depth=0,
            avg_latency_1min=0.0,
        )

    stats["max_concurrent"] = policy.max_concurrent
    return PolicyResourceStats(**stats)


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


async def _do_inference(policy_id: int, data: InferenceRequest, db: AsyncSession):
    policy = await db.get(PolicyService, policy_id)
    if not policy:
        return ABTestPolicyResult(
            policy_id=policy_id,
            latency_ms=0,
            timeout=False,
            error="Policy service not found",
        )
    if policy.status != "running":
        return ABTestPolicyResult(
            policy_id=policy_id,
            latency_ms=0,
            timeout=False,
            error=f"Policy service is not running (status={policy.status})",
        )

    deployed = deployment_manager.get_deployed(policy_id)
    if deployed is None:
        return ABTestPolicyResult(
            policy_id=policy_id,
            latency_ms=0,
            timeout=False,
            error="Deployed model not found in memory",
        )

    if len(data.observations) != deployed.n_agents:
        return ABTestPolicyResult(
            policy_id=policy_id,
            latency_ms=0,
            timeout=False,
            error=f"Expected {deployed.n_agents} agent observations, got {len(data.observations)}",
        )

    deployed.acquire_concurrent()
    try:
        start_time = time.time()
        is_timeout = False
        actions = []
        q_values = None
        error_msg = None
        is_cached = False

        try:
            loop = asyncio.get_event_loop()
            timeout_sec = policy.timeout_ms / 1000.0
            result = await asyncio.wait_for(
                loop.run_in_executor(None, deployed.infer, data.observations, data.communication_context),
                timeout=timeout_sec,
            )
            actions = result["actions"]
            q_values = result.get("q_values")
            is_cached = result.get("cached", False)
        except asyncio.TimeoutError:
            is_timeout = True
            actions = [0] * deployed.n_agents
        except Exception as e:
            error_msg = str(e)
            actions = [0] * deployed.n_agents

        latency_ms = (time.time() - start_time) * 1000.0

        if not is_cached:
            deployed._add_latency(latency_ms)

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
            return ABTestPolicyResult(
                policy_id=policy_id,
                latency_ms=round(latency_ms, 2),
                timeout=True,
                error=None,
                cached=is_cached,
            )

        if error_msg:
            return ABTestPolicyResult(
                policy_id=policy_id,
                latency_ms=round(latency_ms, 2),
                timeout=False,
                error=error_msg,
                cached=is_cached,
            )

        return ABTestPolicyResult(
            policy_id=policy_id,
            actions=actions,
            q_values=q_values,
            latency_ms=round(latency_ms, 2),
            timeout=False,
            error=None,
            cached=is_cached,
        )
    finally:
        deployed.release_concurrent()


@router.post("/{policy_id}/infer", response_model=InferenceResponse)
async def infer_policy(policy_id: int, data: InferenceRequest, db: AsyncSession = Depends(get_db)):
    result = await _do_inference(policy_id, data, db)

    if result.timeout:
        raise HTTPException(408, f"Inference timeout")
    if result.error:
        raise HTTPException(500, result.error)

    return InferenceResponse(
        actions=result.actions or [],
        q_values=result.q_values,
        cached=result.cached,
        latency_ms=result.latency_ms,
    )


@router.post("/ab-test", response_model=ABTestResponse)
async def ab_test_policies(data: ABTestRequest, db: AsyncSession = Depends(get_db)):
    if data.policy_a == data.policy_b:
        raise HTTPException(400, "Policy A and Policy B must be different")

    policy_a = await db.get(PolicyService, data.policy_a)
    policy_b = await db.get(PolicyService, data.policy_b)

    if not policy_a:
        raise HTTPException(404, f"Policy A (id={data.policy_a}) not found")
    if not policy_b:
        raise HTTPException(404, f"Policy B (id={data.policy_b}) not found")

    if policy_a.status != "running":
        raise HTTPException(400, f"Policy A is not running (status={policy_a.status})")
    if policy_b.status != "running":
        raise HTTPException(400, f"Policy B is not running (status={policy_b.status})")

    infer_req = InferenceRequest(
        observations=data.observations,
        communication_context=data.communication_context,
    )

    result_a, result_b = await asyncio.gather(
        _do_inference(data.policy_a, infer_req, db),
        _do_inference(data.policy_b, infer_req, db),
    )

    diff_rate = 0.0
    if result_a.actions and result_b.actions and len(result_a.actions) == len(result_b.actions):
        diff_count = sum(1 for a, b in zip(result_a.actions, result_b.actions) if a != b)
        diff_rate = diff_count / len(result_a.actions) if len(result_a.actions) > 0 else 0.0

    return ABTestResponse(
        policy_a=result_a,
        policy_b=result_b,
        diff_rate=round(diff_rate, 4),
    )


@router.get("/{policy_id}/logs")
async def get_inference_logs(
    policy_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    include_observations: bool = Query(False),
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
            total_count=0,
            avg_latency_ms=0.0,
            p95_latency_ms=0.0,
            timeout_rate=0.0,
            qps_last_hour=0.0,
            cache_hit_rate=0.0,
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

    deployed = deployment_manager.get_deployed(policy_id)
    cache_hit_rate = deployed.cache.hit_rate() if deployed else 0.0

    return InferenceStatsResponse(
        total_count=total_count,
        avg_latency_ms=round(avg_latency, 2),
        p95_latency_ms=round(p95_latency, 2),
        timeout_rate=timeout_rate,
        qps_last_hour=qps_last_hour,
        cache_hit_rate=round(cache_hit_rate, 4),
    )
