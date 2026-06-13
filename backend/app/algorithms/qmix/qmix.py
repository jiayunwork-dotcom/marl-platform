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


class MixingNetwork(nn.Module):
    def __init__(self, n_agents, state_dim, hidden_dim=64):
        super().__init__()
        self.n_agents = n_agents
        self.hyper_w1 = nn.Linear(state_dim, n_agents * hidden_dim)
        self.hyper_b1 = nn.Linear(state_dim, hidden_dim)
        self.hyper_w2 = nn.Linear(state_dim, hidden_dim)
        self.hyper_b2 = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )
        self.hidden_dim = hidden_dim

    def forward(self, agent_qs, states):
        bs = agent_qs.shape[0]
        w1 = torch.abs(self.hyper_w1(states)).view(bs, -1, self.n_agents)
        b1 = self.hyper_b1(states).view(bs, 1, -1)
        hidden = nn.functional.elu(torch.bmm(w1, agent_qs.unsqueeze(2)).squeeze(2) + b1)
        w2 = torch.abs(self.hyper_w2(states)).view(bs, -1, self.hidden_dim)
        b2 = self.hyper_b2(states).view(bs, 1, 1)
        q_tot = torch.bmm(w2, hidden.unsqueeze(2)).squeeze(2) + b2
        return q_tot


class QMIXAlgorithm(BaseAlgorithm):
    def __init__(self, n_agents, obs_shape, n_actions, config, device="cpu"):
        super().__init__(n_agents, obs_shape, n_actions, config, device)
        buffer_size = config.get("replay_buffer_size", 50000)
        self.buffer = ReplayBuffer(buffer_size)
        hidden_dim = config.get("qmix_hidden_dim", 64)
        self.agent_nets = [AgentQNet(obs_shape, n_actions, hidden_dim).to(self.device) for _ in range(n_agents)]
        self.target_agent_nets = [AgentQNet(obs_shape, n_actions, hidden_dim).to(self.device) for _ in range(n_agents)]

        h, w, c = obs_shape
        state_dim = h * w * c
        self.mixer = MixingNetwork(n_agents, state_dim, hidden_dim).to(self.device)
        self.target_mixer = MixingNetwork(n_agents, state_dim, hidden_dim).to(self.device)

        params = []
        for net in self.agent_nets:
            params += list(net.parameters())
        params += list(self.mixer.parameters())
        self.optimizer = optim.Adam(params, lr=self.learning_rate)
        self.target_update_freq = config.get("target_update_freq", 200)

        for n, tn in zip(self.agent_nets, self.target_agent_nets):
            tn.load_state_dict(n.state_dict())
        self.target_mixer.load_state_dict(self.mixer.state_dict())

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

    def _flatten_state(self, state_obs):
        if isinstance(state_obs, np.ndarray):
            return state_obs.flatten()
        return np.array(state_obs).flatten()

    def update(self, batch=None):
        if len(self.buffer) < self.batch_size:
            return {"loss": 0.0}
        b = self.buffer.sample(self.batch_size)
        obs_b = b["obs"]
        act_b = b["actions"]
        rew_b = b["rewards"]
        nobs_b = b["next_obs"]
        dones = torch.FloatTensor(b["dones"]).to(self.device)

        agent_qs = []
        target_agent_qs = []
        for i in range(self.n_agents):
            obs_t = torch.FloatTensor(np.array([o[i] for o in obs_b])).to(self.device)
            act_t = torch.LongTensor([a[i] for a in act_b]).to(self.device)
            nobs_t = torch.FloatTensor(np.array([o[i] for o in nobs_b])).to(self.device)
            q = self.agent_nets[i](obs_t).gather(1, act_t.unsqueeze(1)).squeeze(1)
            with torch.no_grad():
                nq = self.target_agent_nets[i](nobs_t).max(dim=1)[0]
            agent_qs.append(q)
            target_agent_qs.append(nq)

        agent_qs_stack = torch.stack(agent_qs, dim=1)
        target_qs_stack = torch.stack(target_agent_qs, dim=1)

        states = torch.FloatTensor(np.array([self._flatten_state(o[0]) for o in obs_b])).to(self.device)
        nstates = torch.FloatTensor(np.array([self._flatten_state(o[0]) for o in nobs_b])).to(self.device)

        q_tot = self.mixer(agent_qs_stack, states)
        with torch.no_grad():
            target_q_tot = self.target_mixer(target_qs_stack, nstates)
        team_reward = torch.FloatTensor(np.sum(rew_b, axis=1)).to(self.device)
        target = team_reward + self.gamma * target_q_tot.squeeze() * (1 - dones)

        loss = nn.MSELoss()(q_tot.squeeze(), target.detach())
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_([p for net in self.agent_nets for p in net.parameters()] +
                                  list(self.mixer.parameters()), 10)
        self.optimizer.step()

        self.total_steps += 1
        if self.total_steps % self.target_update_freq == 0:
            for n, tn in zip(self.agent_nets, self.target_agent_nets):
                tn.load_state_dict(n.state_dict())
            self.target_mixer.load_state_dict(self.mixer.state_dict())
        return {"loss": loss.item()}

    def get_q_values(self, agent_id, observation):
        with torch.no_grad():
            obs_t = torch.FloatTensor(np.array(observation)).unsqueeze(0).to(self.device)
            return self.agent_nets[agent_id](obs_t).cpu().numpy()[0]

    def state_dict(self):
        return {
            "agent_nets": [n.state_dict() for n in self.agent_nets],
            "target_agent_nets": [t.state_dict() for t in self.target_agent_nets],
            "mixer": self.mixer.state_dict(),
            "target_mixer": self.target_mixer.state_dict(),
            "total_steps": self.total_steps,
        }

    def load_state_dict(self, state):
        for n, s in zip(self.agent_nets, state["agent_nets"]):
            n.load_state_dict(s)
        for t, s in zip(self.target_agent_nets, state["target_agent_nets"]):
            t.load_state_dict(s)
        self.mixer.load_state_dict(state["mixer"])
        self.target_mixer.load_state_dict(state["target_mixer"])
        self.total_steps = state.get("total_steps", 0)
