from abc import ABC, abstractmethod
import numpy as np
import torch
import torch.nn as nn
from typing import Optional
from collections import deque
import random


class BaseAlgorithm(ABC):
    def __init__(self, n_agents: int, obs_shape: tuple, n_actions: int, config: dict, device: str = "cpu"):
        self.n_agents = n_agents
        self.obs_shape = obs_shape
        self.n_actions = n_actions
        self.config = config
        self.device = torch.device(device)
        self.learning_rate = config.get("learning_rate", 0.001)
        self.gamma = config.get("gamma", 0.99)
        self.epsilon_start = config.get("epsilon_start", 1.0)
        self.epsilon_end = config.get("epsilon_end", 0.05)
        self.epsilon_decay_steps = config.get("epsilon_decay_steps", 50000)
        self.batch_size = config.get("batch_size", 32)
        self.total_steps = 0

    def get_epsilon(self) -> float:
        if self.total_steps >= self.epsilon_decay_steps:
            return self.epsilon_end
        ratio = self.total_steps / self.epsilon_decay_steps
        return self.epsilon_start + (self.epsilon_end - self.epsilon_start) * ratio

    @abstractmethod
    def select_actions(self, observations: list, evaluate: bool = False) -> list:
        pass

    @abstractmethod
    def update(self, batch: dict) -> dict:
        pass

    @abstractmethod
    def store_transition(self, obs, actions, rewards, next_obs, done):
        pass

    @abstractmethod
    def get_q_values(self, agent_id: int, observation) -> np.ndarray:
        pass

    @abstractmethod
    def state_dict(self) -> dict:
        pass

    @abstractmethod
    def load_state_dict(self, state: dict):
        pass


class ReplayBuffer:
    def __init__(self, capacity: int):
        self.buffer = deque(maxlen=capacity)

    def push(self, obs, actions, rewards, next_obs, done):
        self.buffer.append((obs, actions, rewards, next_obs, done))

    def sample(self, batch_size: int):
        batch = random.sample(self.buffer, min(batch_size, len(self.buffer)))
        obs, actions, rewards, next_obs, dones = zip(*batch)
        return {
            "obs": np.array(obs),
            "actions": np.array(actions),
            "rewards": np.array(rewards),
            "next_obs": np.array(next_obs),
            "dones": np.array(dones),
        }

    def __len__(self):
        return len(self.buffer)


class ObsEncoder(nn.Module):
    def __init__(self, obs_shape: tuple, hidden_dim: int = 64):
        super().__init__()
        h, w, c = obs_shape
        self.conv = nn.Sequential(
            nn.Conv2d(c, 16, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Flatten(),
        )
        with torch.no_grad():
            dummy = torch.zeros(1, c, h, w)
            flat_size = self.conv(dummy).shape[1]
        self.fc = nn.Sequential(
            nn.Linear(flat_size, hidden_dim),
            nn.ReLU(),
        )

    def forward(self, x):
        if x.dim() == 3:
            x = x.permute(2, 0, 1).unsqueeze(0)
        elif x.dim() == 4:
            x = x.permute(0, 3, 1, 2)
        return self.fc(self.conv(x))
