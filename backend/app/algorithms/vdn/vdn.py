import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from app.algorithms.base import BaseAlgorithm, ReplayBuffer, ObsEncoder


class AgentQNet(nn.Module):
    def __init__(self, obs_shape, n_actions, hidden_dim=64):
        super().__init__()
        self.encoder = ObsEncoder(obs_shape, hidden_dim)
        self.head = nn.Linear(hidden_dim, n_actions)

    def forward(self, x):
        return self.head(self.encoder(x))


class VDNAlgorithm(BaseAlgorithm):
    def __init__(self, n_agents, obs_shape, n_actions, config, device="cpu"):
        super().__init__(n_agents, obs_shape, n_actions, config, device)
        buffer_size = config.get("replay_buffer_size", 50000)
        self.buffer = ReplayBuffer(buffer_size)
        self.agent_nets = [AgentQNet(obs_shape, n_actions).to(self.device) for _ in range(n_agents)]
        self.target_nets = [AgentQNet(obs_shape, n_actions).to(self.device) for _ in range(n_agents)]
        params = []
        for net in self.agent_nets:
            params += list(net.parameters())
        self.optimizer = optim.Adam(params, lr=self.learning_rate)
        self.target_update_freq = config.get("target_update_freq", 200)
        for net, tnet in zip(self.agent_nets, self.target_nets):
            tnet.load_state_dict(net.state_dict())

    def select_actions(self, observations, evaluate=False):
        actions = []
        eps = 0.0 if evaluate else self.get_epsilon()
        for i, obs in enumerate(observations):
            if np.random.random() < eps:
                actions.append(np.random.randint(0, self.n_actions))
            else:
                with torch.no_grad():
                    obs_t = torch.FloatTensor(np.array(obs)).unsqueeze(0).to(self.device)
                    q = self.agent_nets[i](obs_t)
                    actions.append(q.argmax(dim=1).item())
        return actions

    def store_transition(self, obs, actions, rewards, next_obs, done):
        self.buffer.push(obs, actions, rewards, next_obs, done)

    def update(self, batch=None):
        if len(self.buffer) < self.batch_size:
            return {"loss": 0.0}
        b = self.buffer.sample(self.batch_size)
        obs_b = b["obs"]
        act_b = b["actions"]
        rew_b = b["rewards"]
        nobs_b = b["next_obs"]
        dones = torch.FloatTensor(b["dones"]).to(self.device)

        total_q = 0.0
        total_nq = 0.0
        for i in range(self.n_agents):
            obs_t = torch.FloatTensor(np.array([o[i] for o in obs_b])).to(self.device)
            act_t = torch.LongTensor([a[i] for a in act_b]).to(self.device)
            nobs_t = torch.FloatTensor(np.array([o[i] for o in nobs_b])).to(self.device)
            q = self.agent_nets[i](obs_t).gather(1, act_t.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                nq = self.target_nets[i](nobs_t).max(dim=1)[0]
            total_q = total_q + q
            total_nq = total_nq + nq

        team_reward = torch.FloatTensor(np.sum(rew_b, axis=1)).to(self.device)
        target = team_reward + self.gamma * total_nq * (1 - dones)
        loss = nn.MSELoss()(total_q, target.detach())
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_([p for net in self.agent_nets for p in net.parameters()], 10)
        self.optimizer.step()

        self.total_steps += 1
        if self.total_steps % self.target_update_freq == 0:
            for net, tnet in zip(self.agent_nets, self.target_nets):
                tnet.load_state_dict(net.state_dict())
        return {"loss": loss.item()}

    def get_q_values(self, agent_id, observation):
        with torch.no_grad():
            obs_t = torch.FloatTensor(np.array(observation)).unsqueeze(0).to(self.device)
            return self.agent_nets[agent_id](obs_t).cpu().numpy()[0]

    def state_dict(self):
        return {
            "agent_nets": [n.state_dict() for n in self.agent_nets],
            "target_nets": [t.state_dict() for t in self.target_nets],
            "total_steps": self.total_steps,
        }

    def load_state_dict(self, state):
        for n, s in zip(self.agent_nets, state["agent_nets"]):
            n.load_state_dict(s)
        for t, s in zip(self.target_nets, state["target_nets"]):
            t.load_state_dict(s)
        self.total_steps = state.get("total_steps", 0)
