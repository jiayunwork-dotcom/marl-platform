import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from app.algorithms.base import BaseAlgorithm, ReplayBuffer, ObsEncoder


class MADDPGActor(nn.Module):
    def __init__(self, obs_shape, n_actions, hidden_dim=64):
        super().__init__()
        self.encoder = ObsEncoder(obs_shape, hidden_dim)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, n_actions),
            nn.Softmax(dim=-1),
        )

    def forward(self, x):
        return self.head(self.encoder(x))


class MADDPGCritic(nn.Module):
    def __init__(self, state_dim, n_agents, n_actions, hidden_dim=64):
        super().__init__()
        total_action_dim = n_agents * n_actions
        self.net = nn.Sequential(
            nn.Linear(state_dim + total_action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, state, all_actions):
        return self.net(torch.cat([state, all_actions], dim=-1))


class MADDPGAlgorithm(BaseAlgorithm):
    def __init__(self, n_agents, obs_shape, n_actions, config, device="cpu"):
        super().__init__(n_agents, obs_shape, n_actions, config, device)
        buffer_size = config.get("replay_buffer_size", 50000)
        self.buffer = ReplayBuffer(buffer_size)
        self.hidden_dim = 64

        self.actors = [MADDPGActor(obs_shape, n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]
        self.target_actors = [MADDPGActor(obs_shape, n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]
        self.critics = [MADDPGCritic(self._state_dim(), n_agents, n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]
        self.target_critics = [MADDPGCritic(self._state_dim(), n_agents, n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]

        self.actor_optimizers = [optim.Adam(a.parameters(), lr=self.learning_rate) for a in self.actors]
        self.critic_optimizers = [optim.Adam(c.parameters(), lr=self.learning_rate) for c in self.critics]
        self.target_update_freq = config.get("target_update_freq", 200)
        self.tau = 0.01

        for a, ta in zip(self.actors, self.target_actors):
            ta.load_state_dict(a.state_dict())
        for c, tc in zip(self.critics, self.target_critics):
            tc.load_state_dict(c.state_dict())

    def _state_dim(self):
        h, w, c = self.obs_shape
        return h * w * c

    def _flatten_state(self, state):
        if isinstance(state, np.ndarray):
            return state.flatten()
        return np.array(state).flatten()

    def select_actions(self, observations, evaluate=False):
        actions = []
        eps = 0.0 if evaluate else self.get_epsilon()
        for i, obs in enumerate(observations):
            with torch.no_grad():
                obs_t = torch.FloatTensor(np.array(obs)).unsqueeze(0).to(self.device)
                probs = self.actors[i](obs_t)
                if np.random.random() < eps:
                    actions.append(np.random.randint(0, self.n_actions))
                else:
                    if evaluate:
                        actions.append(probs.argmax(dim=1).item())
                    else:
                        dist = torch.distributions.Categorical(probs)
                        actions.append(dist.sample().item())
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

        total_loss = 0.0
        for i in range(self.n_agents):
            obs_t = torch.FloatTensor(np.array([o[i] for o in obs_b])).to(self.device)
            act_t = torch.LongTensor([a[i] for a in act_b]).to(self.device)
            nobs_t = torch.FloatTensor(np.array([o[i] for o in nobs_b])).to(self.device)

            state_t = torch.FloatTensor(np.array([self._flatten_state(o[0]) for o in obs_b])).to(self.device)
            nstate_t = torch.FloatTensor(np.array([self._flatten_state(o[0]) for o in nobs_b])).to(self.device)

            all_act_oh = []
            all_next_act_oh = []
            for j in range(self.n_agents):
                oh = torch.zeros(len(act_b), self.n_actions).to(self.device)
                a_j = torch.LongTensor([a[j] for a in act_b]).to(self.device)
                oh.scatter_(1, a_j.unsqueeze(1), 1.0)
                all_act_oh.append(oh)

                with torch.no_grad():
                    nobs_j = torch.FloatTensor(np.array([o[j] for o in nobs_b])).to(self.device)
                    n_probs = self.target_actors[j](nobs_j)
                    n_oh = n_probs
                all_next_act_oh.append(n_oh)

            all_act_concat = torch.cat(all_act_oh, dim=-1)
            all_next_act_concat = torch.cat(all_next_act_oh, dim=-1)

            q_val = self.critics[i](state_t, all_act_concat).squeeze()
            with torch.no_grad():
                target_q = self.target_critics[i](nstate_t, all_next_act_concat).squeeze()
                rew_t = torch.FloatTensor([r[i] for r in rew_b]).to(self.device)
                target = rew_t + self.gamma * target_q * (1 - dones)

            critic_loss = nn.MSELoss()(q_val, target.detach())
            self.critic_optimizers[i].zero_grad()
            critic_loss.backward()
            nn.utils.clip_grad_norm_(self.critics[i].parameters(), 10)
            self.critic_optimizers[i].step()

            probs = self.actors[i](obs_t)
            act_oh_i = torch.zeros(len(act_b), self.n_actions).to(self.device)
            act_oh_i.scatter_(1, act_t.unsqueeze(1), 1.0)
            all_act_oh_new = list(all_act_oh)
            all_act_oh_new[i] = probs
            all_act_concat_new = torch.cat(all_act_oh_new, dim=-1)
            actor_q = self.critics[i](state_t, all_act_concat_new).mean()
            actor_loss = -actor_q

            self.actor_optimizers[i].zero_grad()
            actor_loss.backward()
            nn.utils.clip_grad_norm_(self.actors[i].parameters(), 10)
            self.actor_optimizers[i].step()

            total_loss += critic_loss.item() + actor_loss.item()

        self.total_steps += 1
        if self.total_steps % self.target_update_freq == 0:
            for a, ta in zip(self.actors, self.target_actors):
                for p, tp in zip(a.parameters(), ta.parameters()):
                    tp.data.copy_(self.tau * p.data + (1 - self.tau) * tp.data)
            for c, tc in zip(self.critics, self.target_critics):
                for p, tp in zip(c.parameters(), tc.parameters()):
                    tp.data.copy_(self.tau * p.data + (1 - self.tau) * tp.data)

        return {"loss": total_loss / max(self.n_agents, 1)}

    def get_q_values(self, agent_id, observation):
        with torch.no_grad():
            obs_t = torch.FloatTensor(np.array(observation)).unsqueeze(0).to(self.device)
            return self.actors[agent_id](obs_t).cpu().numpy()[0]

    def state_dict(self):
        return {
            "actors": [a.state_dict() for a in self.actors],
            "target_actors": [a.state_dict() for a in self.target_actors],
            "critics": [c.state_dict() for c in self.critics],
            "target_critics": [c.state_dict() for c in self.target_critics],
            "total_steps": self.total_steps,
        }

    def load_state_dict(self, state):
        for a, s in zip(self.actors, state["actors"]):
            a.load_state_dict(s)
        for a, s in zip(self.target_actors, state["target_actors"]):
            a.load_state_dict(s)
        for c, s in zip(self.critics, state["critics"]):
            c.load_state_dict(s)
        for c, s in zip(self.target_critics, state["target_critics"]):
            c.load_state_dict(s)
        self.total_steps = state.get("total_steps", 0)
