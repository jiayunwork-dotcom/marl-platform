from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import traceback
import logging

from app.core.database import init_db
from app.api import environments, experiments, evaluations, visualization, reports, policies, templates, batch_runs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="MARL Platform API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", str(exc), traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "error_type": type(exc).__name__},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={"detail": "Not Found"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error("Middleware caught exception: %s", str(exc))
        response = JSONResponse(
            status_code=500,
            content={"detail": str(exc), "error_type": type(exc).__name__},
        )
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

app.include_router(environments.router)
app.include_router(experiments.router)
app.include_router(evaluations.router)
app.include_router(visualization.router)
app.include_router(reports.router)
app.include_router(policies.router)
app.include_router(templates.router)
app.include_router(batch_runs.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/algorithms")
async def list_algorithms():
    return {
        "algorithms": [
            {"id": "IQL", "name": "Independent Q-Learning", "type": "value_based", "off_policy": True},
            {"id": "DQN", "name": "Independent DQN", "type": "value_based", "off_policy": True},
            {"id": "VDN", "name": "VDN (Value Decomposition)", "type": "value_decomposition", "off_policy": True},
            {"id": "QMIX", "name": "QMIX (Monotonic Mixing)", "type": "value_decomposition", "off_policy": True, "supports_comm": True},
            {"id": "MAPPO", "name": "MAPPO (Multi-Agent PPO)", "type": "policy_gradient", "off_policy": False, "supports_comm": True},
            {"id": "MADDPG", "name": "MADDPG (Multi-Agent DDPG)", "type": "actor_critic", "off_policy": True},
        ]
    }
