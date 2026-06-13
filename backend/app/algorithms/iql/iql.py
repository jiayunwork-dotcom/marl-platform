import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from app.algorithms.base import BaseAlgorithm, ReplayBuffer, ObsEncoder


class QNetwork(nn.Module):
    def __init__(self, obs_shape: tuple, n_actions: int, hidden_dim: int = 64):
        super().__init__()
        self.encoder = ObsEncoder(obs_shape, hidden_dim)
        self.head = nn.Linear(hidden_dim, n_actions)

    def forward(self, x):
        return self.head(self.encoder(x))


class IQLAlgorithm(BaseAlgorithm):
    def __init__(self, n_agents, obs_shape, n_actions, config, device="cpu"):
        super().__init__(n_agents, obs_shape, n_actions, config, device)
        buffer_size = config.get("replay_buffer_size", 50000)
        self.buffers = [ReplayBuffer(buffer_size) for _ in range(n_agents)]
        self.q_networks = [QNetwork(obs_shape, n_actions).to(self.device) for _ in range(n_agents)]
        self.target_networks = [QNetwork(obs_shape, n_actions).to(self.device) for _ in range(n_agents)]
        self.optimizers = [optim.Adam(q.parameters(), lr=self.learning_rate) for q in self.q_networks]
        self.target_update_freq = config.get("target_update_freq", 200)
        for q, tq in zip(self.q_networks, self.target_networks):
            tq.load_state_dict(q.state_dict())

    def select_actions(self, observations, evaluate=False):
        actions = []
        eps = 0.0 if evaluate else self.get_epsilon()
        for i, obs in enumerate(observations):
            if np.random.random() < eps:
                actions.append(np.random.randint(0, self.n_actions))
            else:
                with torch.no_grad():
                    obs_t = torch.FloatTensor(np.array(obs)).unsqueeze(0).to(self.device)
                    q_vals = self.q_networks[i](obs_t)
                    actions.append(q_vals.argmax(dim=1).item())
        return actions

    def store_transition(self, obs, actions, rewards, next_obs, done):
        for i in range(self.n_agents):
            self.buffers[i].push(obs[i], actions[i], rewards[i], next_obs[i], done)

    def update(self, batch=None):
        total_loss = 0.0
        for i in range(self.n_agents):
            if len(self.buffers[i]) < self.batch_size:
                continue
            b = self.buffers[i].sample(self.batch_size)
            obs = torch.FloatTensor(b["obs"]).to(self.device)
            act = torch.LongTensor(b["actions"]).to(self.device)
            rew = torch.FloatTensor(b["rewards"]).to(self.device)
            next_obs = torch.FloatTensor(b["next_obs"]).to(self.device)
            dones = torch.FloatTensor(b["dones"]).to(self.device)

            q_vals = self.q_networks[i](obs).gather(1, act.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                next_q = self.target_networks[i](next_obs).max(dim=1)[0]
                target = rew + self.gamma * next_q * (1 - dones)
            loss = nn.MSELoss()(q_vals, target)
            self.optimizers[i].zero_grad()
            loss.backward()
            self.optimizers[i].step()
            total_loss += loss.item()

        self.total_steps += 1
        if self.total_steps % self.target_update_freq == 0:
            for q, tq in zip(self.q_networks, self.target_networks):
                tq.load_state_dict(q.state_dict())

        return {"loss": total_loss / max(self.n_agents, 1)}

    def get_q_values(self, agent_id, observation):
        with torch.no_grad():
            obs_t = torch.FloatTensor(np.array(observation)).unsqueeze(0).to(self.device)
            return self.q_networks[agent_id](obs_t).cpu().numpy()[0]

    def state_dict(self):
        return {
            "q_networks": [q.state_dict() for q in self.q_networks],
            "target_networks": [t.state_dict() for t in self.target_networks],
            "total_steps": self.total_steps,
        }

    def load_state_dict(self, state):
        for q, s in zip(self.q_networks, state["q_networks"]):
            q.load_state_dict(s)
        for t, s in zip(self.target_networks, state["target_networks"]):
            t.load_state_dict(s)
        self.total_steps = state.get("total_steps", 0)
