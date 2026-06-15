from __future__ import annotations

import logging
from typing import Optional

from app.algorithms.iql.iql import IQLAlgorithm
from app.algorithms.dqn.dqn import DQNAlgorithm
from app.algorithms.vdn.vdn import VDNAlgorithm
from app.algorithms.qmix.qmix import QMIXAlgorithm
from app.algorithms.mappo.mappo import MAPPOAlgorithm
from app.algorithms.maddpg.maddpg import MADDPGAlgorithm

logger = logging.getLogger(__name__)

ALGORITHM_MAP = {
    "IQL": IQLAlgorithm,
    "DQN": DQNAlgorithm,
    "VDN": VDNAlgorithm,
    "QMIX": QMIXAlgorithm,
    "MAPPO": MAPPOAlgorithm,
    "MADDPG": MADDPGAlgorithm,
}

_CASE_INSENSITIVE = {k.upper(): k for k in ALGORITHM_MAP}


def _resolve_algorithm_name(algorithm_name: Optional[str], config: dict) -> str:
    """
    Robustly resolve an algorithm name. Accepts case variations and falls back
    to looking for a hint inside the config dict itself.
    """
    if algorithm_name:
        if algorithm_name in ALGORITHM_MAP:
            return algorithm_name
        upper = algorithm_name.upper()
        if upper in _CASE_INSENSITIVE:
            return _CASE_INSENSITIVE[upper]

    if isinstance(config, dict):
        for key in ("algorithm", "algorithm_name", "algo", "name"):
            if key in config:
                resolved = _resolve_algorithm_name(config[key], {})
                if resolved:
                    return resolved

    raise ValueError(
        f"Cannot resolve algorithm name (got {algorithm_name!r}). "
        f"Available: {sorted(ALGORITHM_MAP.keys())}. "
        f"Config: {config!r}"
    )


def create_algorithm(
    algorithm_name: str,
    n_agents: int,
    obs_shape: tuple,
    n_actions: int,
    config: dict,
    device: str = "cpu",
):
    resolved = _resolve_algorithm_name(algorithm_name, config)
    cls = ALGORITHM_MAP[resolved]
    logger.info(
        "Creating algorithm %s (n_agents=%s, obs_shape=%s, n_actions=%s, device=%s)",
        resolved, n_agents, obs_shape, n_actions, device,
    )
    effective_config = dict(config) if isinstance(config, dict) else {}
    effective_config.setdefault("algorithm", resolved)
    return cls(n_agents, obs_shape, n_actions, effective_config, device)
