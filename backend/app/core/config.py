import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://marl:marl_secret_2024@db:5432/marl_platform"
    SYNC_DATABASE_URL: str = "postgresql+psycopg2://marl:marl_secret_2024@db:5432/marl_platform"
    CHECKPOINT_DIR: str = "/app/checkpoints"
    MAP_SAVE_DIR: str = "/app/saved_maps"
    MAX_CONCURRENT_TRAINING: int = 2
    MAX_CHECKPOINTS: int = 10
    CHECKPOINT_INTERVAL: int = 100
    POLICY_HEALTH_CHECK_INTERVAL: int = 30
    POLICY_HEALTH_CHECK_FAILURE_THRESHOLD: int = 3

    class Config:
        env_file = ".env"


settings = Settings()

os.makedirs(settings.CHECKPOINT_DIR, exist_ok=True)
os.makedirs(settings.MAP_SAVE_DIR, exist_ok=True)
