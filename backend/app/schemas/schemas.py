from __future__ import annotations

import ast
import json
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime


def _coerce_json_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return {}
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            try:
                parsed = ast.literal_eval(s)
                return parsed if isinstance(parsed, dict) else {}
            except (ValueError, SyntaxError):
                return {}
    return {}


def _coerce_json_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            return json.loads(s)
        except (json.JSONDecodeError, ValueError):
            try:
                parsed = ast.literal_eval(s)
                return parsed if isinstance(parsed, list) else []
            except (ValueError, SyntaxError):
                return []
    return []


class CellConfig(BaseModel):
    x: int
    y: int
    type: str = Field(description="empty|obstacle|resource|spawn|target")
    team: Optional[int] = None


class MapConfig(BaseModel):
    width: int = Field(ge=5, le=30)
    height: int = Field(ge=5, le=30)
    cells: list[CellConfig] = []


class EnvironmentCreate(BaseModel):
    name: str
    description: str = ""
    map_config: MapConfig
    max_steps: int = 100
    obs_range: int = Field(default=-1, description="-1 for global, 1-5 for local radius")
    action_space: int = Field(default=5, description="4 or 5 directions")
    collision_rule: str = Field(default="both_stay", description="bounce_back|both_stay")
    resource_refresh: str = Field(default="fixed_interval", description="fixed_interval|random_position")
    resource_refresh_interval: int = 10
    reward_goal: float = 10.0
    reward_resource: float = 5.0
    reward_collision: float = -2.0
    reward_wall: float = -1.0
    reward_step: float = -0.1
    reward_catch_predator: float = 20.0
    reward_catch_prey: float = -20.0
    reward_timeout: float = -5.0
    scenario_type: str = "custom"
    agent_count: int = Field(default=2, ge=2, le=8)
    team_config: dict[str, Any] = {}


class EnvironmentResponse(BaseModel):
    id: int
    name: str
    description: str
    map_config: dict
    width: int
    height: int
    max_steps: int
    obs_range: int
    action_space: int
    collision_rule: str
    resource_refresh: str
    resource_refresh_interval: int
    reward_goal: float
    reward_resource: float
    reward_collision: float
    reward_wall: float
    reward_step: float
    reward_catch_predator: float
    reward_catch_prey: float
    reward_timeout: float
    scenario_type: str
    agent_count: int
    team_config: dict
    created_at: datetime

    @field_validator("map_config", mode="before")
    @classmethod
    def _mc(cls, v): return _coerce_json_dict(v)

    @field_validator("team_config", mode="before")
    @classmethod
    def _tc(cls, v): return _coerce_json_dict(v)

    model_config = {"from_attributes": True}


class AlgorithmConfig(BaseModel):
    algorithm: str = Field(description="IQL|DQN|VDN|QMIX|MAPPO|MADDPG")
    learning_rate: float = 0.001
    gamma: float = 0.99
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay_steps: int = 50000
    replay_buffer_size: int = 50000
    batch_size: int = 32
    target_update_freq: int = 200
    qmix_hidden_dim: int = 64
    mappo_clip: float = 0.2
    mappo_gae_lambda: float = 0.95
    communication_enabled: bool = False
    comm_dim: int = 8


class ExperimentCreate(BaseModel):
    name: str
    environment_id: int
    algorithm_config: AlgorithmConfig
    total_episodes: int = 1000


class ExperimentResponse(BaseModel):
    id: int
    name: str
    environment_id: int
    algorithm: str
    hyperparams: dict
    communication_enabled: bool
    status: str
    current_episode: int
    total_episodes: int
    batch_run_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    summary: Optional[dict[str, Any]] = None

    @field_validator("hyperparams", mode="before")
    @classmethod
    def _hp(cls, v): return _coerce_json_dict(v)

    @field_validator("summary", mode="before")
    @classmethod
    def _sm(cls, v): return _coerce_json_dict(v)

    model_config = {"from_attributes": True}


class TrainingLogResponse(BaseModel):
    id: int
    experiment_id: int
    episode: int
    total_reward: float
    agent_rewards: dict
    steps: int
    goal_reached: bool
    win_rate: float
    timestamp: datetime

    @field_validator("agent_rewards", mode="before")
    @classmethod
    def _ar(cls, v): return _coerce_json_dict(v)

    model_config = {"from_attributes": True}


class EvaluationCreate(BaseModel):
    experiment_id: int
    num_episodes: int = 10


class EvaluationResponse(BaseModel):
    id: int
    experiment_id: int
    num_episodes: int
    avg_reward: float
    success_rate: float
    collision_rate: float
    avg_steps: float
    episode_data: list
    created_at: datetime

    @field_validator("episode_data", mode="before")
    @classmethod
    def _ed(cls, v): return _coerce_json_list(v)

    model_config = {"from_attributes": True}


class CheckpointResponse(BaseModel):
    id: int
    experiment_id: int
    episode: int
    filepath: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ComparisonRequest(BaseModel):
    experiment_ids: list[int] = Field(min_length=2, max_length=4)


class PresetScenarioRequest(BaseModel):
    scenario_type: str = Field(description="cooperative_navigation|resource_competition|predator_prey")
    map_size: int = Field(default=10, ge=5, le=30)
    agent_count: int = Field(default=4, ge=2, le=8)
    team_config: Optional[dict[str, Any]] = None


class PolicyServiceCreate(BaseModel):
    name: str
    experiment_id: int
    checkpoint_id: int
    max_concurrent: int = Field(default=10, ge=1, le=100)
    timeout_ms: int = Field(default=5000, ge=100, le=60000)


class PolicyServiceResponse(BaseModel):
    id: int
    name: str
    version: int
    experiment_id: int
    checkpoint_id: int
    max_concurrent: int
    timeout_ms: int
    status: str
    error_reason: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PolicyServiceDetailResponse(PolicyServiceResponse):
    history_versions: list[PolicyServiceResponse] = []


class PolicyServiceGroupItem(BaseModel):
    name: str
    versions: list[PolicyServiceResponse]


class InferenceRequest(BaseModel):
    observations: list[list[float]]
    communication_context: Optional[list[float]] = None


class InferenceResponse(BaseModel):
    actions: list[int]
    q_values: Optional[list[list[float]]] = None
    cached: bool = False
    latency_ms: float = 0.0


class InferenceLogResponse(BaseModel):
    id: int
    policy_service_id: int
    request_time: datetime
    latency_ms: float
    obs_dimensions: str
    output_actions: str
    is_timeout: bool
    observations: Optional[list[list[float]]] = None

    model_config = {"from_attributes": True}


class InferenceStatsResponse(BaseModel):
    total_count: int
    avg_latency_ms: float
    p95_latency_ms: float
    timeout_rate: float
    qps_last_hour: float
    cache_hit_rate: float = 0.0


class ABTestRequest(BaseModel):
    policy_a: int
    policy_b: int
    observations: list[list[float]]
    communication_context: Optional[list[float]] = None


class ABTestPolicyResult(BaseModel):
    policy_id: int
    actions: Optional[list[int]] = None
    q_values: Optional[list[list[float]]] = None
    latency_ms: float
    timeout: bool = False
    error: Optional[str] = None
    cached: bool = False


class ABTestResponse(BaseModel):
    policy_a: ABTestPolicyResult
    policy_b: ABTestPolicyResult
    diff_rate: float


class PolicyResourceStats(BaseModel):
    policy_id: int
    current_concurrent: int
    max_concurrent: int
    queue_depth: int
    avg_latency_1min: float


class ExperimentTemplateCreate(BaseModel):
    name: str
    description: str = ""
    algorithm: str
    hyperparams: dict[str, Any] = {}
    communication_enabled: bool = False
    environment_id: int
    agent_count: int = 2
    total_episodes: int = 1000
    param_variables: dict[str, Any] = {}


class ExperimentTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    param_variables: Optional[dict[str, Any]] = None
    hyperparams: Optional[dict[str, Any]] = None
    total_episodes: Optional[int] = None


class ExperimentTemplateResponse(BaseModel):
    id: int
    name: str
    description: str
    algorithm: str
    hyperparams: dict
    communication_enabled: bool
    environment_id: int
    agent_count: int
    total_episodes: int
    param_variables: dict
    created_at: datetime

    @field_validator("hyperparams", mode="before")
    @classmethod
    def _hp(cls, v): return _coerce_json_dict(v)

    @field_validator("param_variables", mode="before")
    @classmethod
    def _pv(cls, v): return _coerce_json_dict(v)

    model_config = {"from_attributes": True}


class CreateTemplateFromExperimentRequest(BaseModel):
    experiment_id: int
    name: str
    description: str = ""


class BatchRunCreate(BaseModel):
    template_id: int
    name: str


class BatchRunResponse(BaseModel):
    id: int
    name: str
    template_id: int
    status: str
    experiment_ids: list
    current_index: int
    param_combinations: list
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    is_cancelled: bool

    @field_validator("experiment_ids", mode="before")
    @classmethod
    def _eids(cls, v): return _coerce_json_list(v)

    @field_validator("param_combinations", mode="before")
    @classmethod
    def _pcombs(cls, v): return _coerce_json_list(v)

    model_config = {"from_attributes": True}


class BatchRunPreviewRequest(BaseModel):
    template_id: int


class BatchRunPreviewResponse(BaseModel):
    total_combinations: int
    param_combinations: list[dict]


class BatchRunStatsResponse(BaseModel):
    batch_run_id: int
    status: str
    total_experiments: int
    completed_count: int
    running_count: int
    failed_count: int
    pending_count: int
    experiments: list[dict]
    group_stats: list[dict]
    best_combination: Optional[dict] = None
    total_duration_seconds: Optional[float] = None
