import torch
import torch.nn as nn
import numpy as np
from app.algorithms.base import ObsEncoder


class CommModule(nn.Module):
    def __init__(self, obs_shape, n_agents, comm_dim=8, hidden_dim=64):
        super().__init__()
        self.n_agents = n_agents
        self.comm_dim = comm_dim
        self.encoder = ObsEncoder(obs_shape, hidden_dim)
        self.msg_encoder = nn.Linear(hidden_dim, comm_dim)
        self.msg_decoder = nn.Linear(comm_dim * (n_agents - 1), hidden_dim)
        self.attention = nn.Sequential(
            nn.Linear(comm_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Softmax(dim=1),
        )

    def forward(self, observations):
        messages = []
        encoded = []
        for i in range(self.n_agents):
            enc = self.encoder(observations[i])
            encoded.append(enc)
            msg = self.msg_encoder(enc)
            messages.append(msg)

        attended_msgs = []
        for i in range(self.n_agents):
            other_msgs = [messages[j] for j in range(self.n_agents) if j != i]
            other_msgs_stack = torch.stack(other_msgs, dim=0)
            query = messages[i].unsqueeze(0).expand(len(other_msgs), -1)
            attn_input = torch.cat([query, other_msgs_stack], dim=-1)
            attn_weights = self.attention(attn_input)
            weighted = (other_msgs_stack * attn_weights).sum(dim=0)
            attended_msgs.append(weighted)

        outputs = []
        for i in range(self.n_agents):
            all_msgs = torch.cat([messages[j] for j in range(self.n_agents) if j != i], dim=-1)
            decoded = self.msg_decoder(all_msgs)
            combined = encoded[i] + decoded
            outputs.append(combined)

        return outputs, messages, attn_weights if self.n_agents > 1 else None


class CommQMIXWrapper:
    def __init__(self, base_algorithm, comm_dim=8):
        self.base = base_algorithm
        self.comm = CommModule(
            base_algorithm.obs_shape,
            base_algorithm.n_agents,
            comm_dim,
        ).to(base_algorithm.device)
        self.comm_optimizer = torch.optim.Adam(
            self.comm.parameters(), lr=base_algorithm.learning_rate
        )
        self.message_history = []

    def enhance_observations(self, observations):
        with torch.no_grad():
            obs_t = [torch.FloatTensor(np.array(obs)).unsqueeze(0).to(self.base.device) for obs in observations]
            outputs, messages, attn = self.comm(obs_t)
        self.message_history.append([m.cpu().numpy() for m in messages])
        return outputs

    def get_attention_weights(self):
        if not self.message_history:
            return None
        return self.message_history[-1]
