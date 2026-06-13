from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


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

    class Config:
        from_attributes = True


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
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


class CheckpointResponse(BaseModel):
    id: int
    experiment_id: int
    episode: int
    filepath: str
    created_at: datetime

    class Config:
        from_attributes = True


class ComparisonRequest(BaseModel):
    experiment_ids: list[int] = Field(min_length=2, max_length=4)


class PresetScenarioRequest(BaseModel):
    scenario_type: str = Field(description="cooperative_navigation|resource_competition|predator_prey")
    map_size: int = Field(default=10, ge=5, le=30)
    agent_count: int = Field(default=4, ge=2, le=8)
    team_config: Optional[dict[str, Any]] = None
