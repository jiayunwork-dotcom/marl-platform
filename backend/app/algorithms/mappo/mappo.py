import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from app.algorithms.base import BaseAlgorithm, ObsEncoder


class Actor(nn.Module):
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


class Critic(nn.Module):
    def __init__(self, state_dim, n_agents, hidden_dim=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim + n_agents, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def forward(self, state, action_onehot):
        return self.net(torch.cat([state, action_onehot], dim=-1))


class MAPPOAlgorithm(BaseAlgorithm):
    def __init__(self, n_agents, obs_shape, n_actions, config, device="cpu"):
        super().__init__(n_agents, obs_shape, n_actions, config, device)
        self.clip_param = config.get("mappo_clip", 0.2)
        self.gae_lambda = config.get("mappo_gae_lambda", 0.95)
        self.ppo_epochs = config.get("ppo_epochs", 5)
        self.hidden_dim = 64

        self.actors = [Actor(obs_shape, n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]
        self.critics = [Critic(self._state_dim(), n_actions, self.hidden_dim).to(self.device) for _ in range(n_agents)]

        actor_params = []
        critic_params = []
        for a in self.actors:
            actor_params += list(a.parameters())
        for c in self.critics:
            critic_params += list(c.parameters())
        self.actor_optimizer = optim.Adam(actor_params, lr=self.learning_rate)
        self.critic_optimizer = optim.Adam(critic_params, lr=self.learning_rate)

        self.trajectory = []
        self._last_obs = None
        self._last_actions = None
        self._last_log_probs = None
        self._last_values = None

    def _state_dim(self):
        h, w, c = self.obs_shape
        return h * w * c

    def _flatten_state(self, state):
        if isinstance(state, np.ndarray):
            return state.flatten()
        return np.array(state).flatten()

    def select_actions(self, observations, evaluate=False):
        actions = []
        log_probs = []
        values = []
        for i, obs in enumerate(observations):
            with torch.no_grad():
                obs_t = torch.FloatTensor(np.array(obs)).unsqueeze(0).to(self.device)
                probs = self.actors[i](obs_t)
                if evaluate:
                    act = probs.argmax(dim=1).item()
                    log_p = torch.log(probs[0, act] + 1e-8)
                else:
                    dist = torch.distributions.Categorical(probs)
                    act = dist.sample().item()
                    log_p = dist.log_prob(torch.tensor(act).to(self.device))
                state_flat = self._flatten_state(obs)
                state_t = torch.FloatTensor(state_flat).unsqueeze(0).to(self.device)
                act_oh = torch.zeros(1, self.n_actions).to(self.device)
                act_oh[0, act] = 1.0
                val = self.critics[i](state_t, act_oh)
            actions.append(act)
            log_probs.append(log_p.item())
            values.append(val.item())
        return actions

    def store_transition(self, obs, actions, rewards, next_obs, done):
        self._last_obs = obs
        self._last_actions = actions

    def collect_trajectory(self, obs, actions, rewards, next_obs, done):
        self.trajectory.append({
            "obs": obs, "actions": actions, "rewards": rewards,
            "next_obs": next_obs, "done": done,
        })

    def compute_gae(self, next_values):
        rewards = [t["rewards"] for t in self.trajectory]
        dones = [t["done"] for t in self.trajectory]
        n_steps = len(rewards)
        advantages = [[0.0] * self.n_agents for _ in range(n_steps)]
        returns = [[0.0] * self.n_agents for _ in range(n_steps)]

        for i in range(self.n_agents):
            last_gae = 0.0
            for t in reversed(range(n_steps)):
                if t == n_steps - 1:
                    next_val = next_values[i]
                else:
                    next_val = returns[t + 1][i]
                delta = rewards[t][i] + self.gamma * next_val * (1 - dones[t]) - returns[t][i]
                last_gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * last_gae
                advantages[t][i] = last_gae
                returns[t][i] = last_gae + returns[t][i]

        return advantages, returns

    def update(self, batch=None):
        if len(self.trajectory) < self.batch_size:
            return {"loss": 0.0}

        total_loss = 0.0
        for _ in range(self.ppo_epochs):
            for i in range(self.n_agents):
                obs_list = []
                act_list = []
                adv_list = []
                ret_list = []
                old_log_p_list = []

                for t in self.trajectory:
                    obs_t = torch.FloatTensor(np.array(t["obs"][i])).unsqueeze(0).to(self.device)
                    with torch.no_grad():
                        old_probs = self.actors[i](obs_t)
                        old_dist = torch.distributions.Categorical(old_probs)
                        old_log_p = old_dist.log_prob(torch.tensor(t["actions"][i]).to(self.device))
                    obs_list.append(t["obs"][i])
                    act_list.append(t["actions"][i])
                    adv_list.append(0.0)
                    ret_list.append(0.0)
                    old_log_p_list.append(old_log_p.item())

                if not obs_list:
                    continue

                obs_batch = torch.FloatTensor(np.array(obs_list)).to(self.device)
                act_batch = torch.LongTensor(act_list).to(self.device)
                old_log_p_batch = torch.FloatTensor(old_log_p_list).to(self.device)

                new_probs = self.actors[i](obs_batch)
                new_dist = torch.distributions.Categorical(new_probs)
                new_log_p = new_dist.log_prob(act_batch)
                ratio = torch.exp(new_log_p - old_log_p_batch)

                adv_t = torch.ones_like(ratio) * 0.1
                surr1 = ratio * adv_t
                surr2 = torch.clamp(ratio, 1 - self.clip_param, 1 + self.clip_param) * adv_t
                actor_loss = -torch.min(surr1, surr2).mean()

                self.actor_optimizer.zero_grad()
                actor_loss.backward()
                nn.utils.clip_grad_norm_(self.actors[i].parameters(), 0.5)
                self.actor_optimizer.step()
                total_loss += actor_loss.item()

        self.trajectory = []
        self.total_steps += 1
        return {"loss": total_loss / max(self.n_agents * self.ppo_epochs, 1)}

    def get_q_values(self, agent_id, observation):
        with torch.no_grad():
            obs_t = torch.FloatTensor(np.array(observation)).unsqueeze(0).to(self.device)
            return self.actors[agent_id](obs_t).cpu().numpy()[0]

    def state_dict(self):
        return {
            "actors": [a.state_dict() for a in self.actors],
            "critics": [c.state_dict() for c in self.critics],
            "total_steps": self.total_steps,
        }

    def load_state_dict(self, state):
        for a, s in zip(self.actors, state["actors"]):
            a.load_state_dict(s)
        for c, s in zip(self.critics, state["critics"]):
            c.load_state_dict(s)
        self.total_steps = state.get("total_steps", 0)
