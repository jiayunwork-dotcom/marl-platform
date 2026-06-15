from __future__ import annotations

from typing import Any, Optional
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from app.core.database import Base


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str] = mapped_column(sa.Text, default="")
    map_config: Mapped[dict[str, Any]] = mapped_column(sa.JSON)
    width: Mapped[int] = mapped_column(sa.Integer)
    height: Mapped[int] = mapped_column(sa.Integer)
    max_steps: Mapped[int] = mapped_column(sa.Integer, default=100)
    obs_range: Mapped[int] = mapped_column(sa.Integer, default=-1)
    action_space: Mapped[int] = mapped_column(sa.Integer, default=5)
    collision_rule: Mapped[str] = mapped_column(sa.String(50), default="both_stay")
    resource_refresh: Mapped[str] = mapped_column(sa.String(50), default="fixed_interval")
    resource_refresh_interval: Mapped[int] = mapped_column(sa.Integer, default=10)
    reward_goal: Mapped[float] = mapped_column(sa.Float, default=10.0)
    reward_resource: Mapped[float] = mapped_column(sa.Float, default=5.0)
    reward_collision: Mapped[float] = mapped_column(sa.Float, default=-2.0)
    reward_wall: Mapped[float] = mapped_column(sa.Float, default=-1.0)
    reward_step: Mapped[float] = mapped_column(sa.Float, default=-0.1)
    reward_catch_predator: Mapped[float] = mapped_column(sa.Float, default=20.0)
    reward_catch_prey: Mapped[float] = mapped_column(sa.Float, default=-20.0)
    reward_timeout: Mapped[float] = mapped_column(sa.Float, default=-5.0)
    scenario_type: Mapped[str] = mapped_column(sa.String(50), default="custom")
    agent_count: Mapped[int] = mapped_column(sa.Integer, default=2)
    team_config: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    environment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("environments.id"))
    algorithm: Mapped[str] = mapped_column(sa.String(50))
    hyperparams: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)
    communication_enabled: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    status: Mapped[str] = mapped_column(sa.String(50), default="created")
    current_episode: Mapped[int] = mapped_column(sa.Integer, default=0)
    total_episodes: Mapped[int] = mapped_column(sa.Integer, default=1000)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True, default=None)
    finished_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True, default=None)
    summary: Mapped[Optional[dict[str, Any]]] = mapped_column(sa.JSON, nullable=True, default=None)


class TrainingLog(Base):
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiments.id"))
    episode: Mapped[int] = mapped_column(sa.Integer)
    total_reward: Mapped[float] = mapped_column(sa.Float)
    agent_rewards: Mapped[dict[str, Any]] = mapped_column(sa.JSON, default=dict)
    steps: Mapped[int] = mapped_column(sa.Integer)
    goal_reached: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    win_rate: Mapped[float] = mapped_column(sa.Float, default=0.0)
    timestamp: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiments.id"))
    episode: Mapped[int] = mapped_column(sa.Integer)
    filepath: Mapped[str] = mapped_column(sa.String(500))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiments.id"))
    num_episodes: Mapped[int] = mapped_column(sa.Integer)
    avg_reward: Mapped[float] = mapped_column(sa.Float)
    success_rate: Mapped[float] = mapped_column(sa.Float)
    collision_rate: Mapped[float] = mapped_column(sa.Float)
    avg_steps: Mapped[float] = mapped_column(sa.Float)
    episode_data: Mapped[list[Any]] = mapped_column(sa.JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)


class PolicyService(Base):
    __tablename__ = "policy_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    experiment_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("experiments.id"))
    checkpoint_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("checkpoints.id"))
    max_concurrent: Mapped[int] = mapped_column(sa.Integer, default=10)
    timeout_ms: Mapped[int] = mapped_column(sa.Integer, default=5000)
    status: Mapped[str] = mapped_column(sa.String(50), default="created")
    error_reason: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True, default=None)
    stopped_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime, nullable=True, default=None)


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_service_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("policy_services.id"))
    request_time: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow)
    latency_ms: Mapped[float] = mapped_column(sa.Float)
    obs_dimensions: Mapped[str] = mapped_column(sa.String(200), default="")
    output_actions: Mapped[str] = mapped_column(sa.String(500), default="")
    is_timeout: Mapped[bool] = mapped_column(sa.Boolean, default=False)
