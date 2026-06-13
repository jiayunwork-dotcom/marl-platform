from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.database import init_db
from app.api import environments, experiments, evaluations, visualization, reports


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
)

app.include_router(environments.router)
app.include_router(experiments.router)
app.include_router(evaluations.router)
app.include_router(visualization.router)
app.include_router(reports.router)


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
