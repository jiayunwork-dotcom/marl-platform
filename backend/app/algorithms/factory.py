from app.algorithms.iql.iql import IQLAlgorithm
from app.algorithms.dqn.dqn import DQNAlgorithm
from app.algorithms.vdn.vdn import VDNAlgorithm
from app.algorithms.qmix.qmix import QMIXAlgorithm
from app.algorithms.mappo.mappo import MAPPOAlgorithm
from app.algorithms.maddpg.maddpg import MADDPGAlgorithm


ALGORITHM_MAP = {
    "IQL": IQLAlgorithm,
    "DQN": DQNAlgorithm,
    "VDN": VDNAlgorithm,
    "QMIX": QMIXAlgorithm,
    "MAPPO": MAPPOAlgorithm,
    "MADDPG": MADDPGAlgorithm,
}


def create_algorithm(algorithm_name: str, n_agents: int, obs_shape: tuple, n_actions: int, config: dict, device: str = "cpu"):
    cls = ALGORITHM_MAP.get(algorithm_name)
    if cls is None:
        raise ValueError(f"Unknown algorithm: {algorithm_name}. Available: {list(ALGORITHM_MAP.keys())}")
    return cls(n_agents, obs_shape, n_actions, config, device)
