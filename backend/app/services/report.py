import json
import numpy as np
from datetime import datetime
from scipy import stats as scipy_stats
from app.core.database import async_session
from app.models.models import Experiment, TrainingLog, Environment
from sqlalchemy import select


async def generate_comparison_report(experiment_ids: list[int]) -> dict:
    async with async_session() as session:
        experiments = []
        for eid in experiment_ids:
            exp = await session.get(Experiment, eid)
            if not exp:
                continue
            experiments.append(exp)

        if len(experiments) < 2:
            raise ValueError("Need at least 2 experiments for comparison")

        configs_diff = _compute_config_diff(experiments)

        performance = []
        for exp in experiments:
            logs = await session.execute(
                select(TrainingLog).where(TrainingLog.experiment_id == exp.id)
                .order_by(TrainingLog.episode)
            )
            log_list = logs.scalars().all()
            if not log_list:
                performance.append({"id": exp.id, "name": exp.name, "avg_reward": 0, "success_rate": 0, "convergence_ep": 0})
                continue

            rewards = [l.total_reward for l in log_list]
            last_10 = rewards[-10:] if len(rewards) >= 10 else rewards
            avg_reward = np.mean(last_10)
            success_rate = np.mean([1 if l.goal_reached else 0 for l in log_list[-10:]])
            convergence_ep = _find_convergence(rewards)

            performance.append({
                "id": exp.id, "name": exp.name,
                "avg_reward": float(avg_reward),
                "success_rate": float(success_rate),
                "convergence_ep": convergence_ep,
                "total_episodes": len(log_list),
                "all_rewards": rewards,
            })

        significance = _compute_significance(performance)

        return {
            "experiments": [{"id": e.id, "name": e.name, "algorithm": e.algorithm} for e in experiments],
            "config_diff": configs_diff,
            "performance": performance,
            "significance": significance,
            "generated_at": datetime.utcnow().isoformat(),
        }


def _compute_config_diff(experiments: list) -> dict:
    all_keys = set()
    configs = []
    for exp in experiments:
        hp = exp.hyperparams if isinstance(exp.hyperparams, dict) else json.loads(exp.hyperparams)
        configs.append(hp)
        all_keys.update(hp.keys())

    diff = {}
    for key in sorted(all_keys):
        values = [c.get(key) for c in configs]
        unique = set(str(v) for v in values if v is not None)
        if len(unique) > 1:
            diff[key] = {f"exp_{i}": v for i, v in enumerate(values)}

    return diff


def _find_convergence(rewards: list, window: int = 50, threshold: float = 0.05) -> int:
    if len(rewards) < window * 2:
        return len(rewards)

    for i in range(window, len(rewards) - window):
        prev = np.mean(rewards[i - window:i])
        curr = np.mean(rewards[i:i + window])
        if abs(curr - prev) < threshold * abs(prev + 1e-8):
            return i
    return len(rewards)


def _compute_significance(performance: list) -> list:
    results = []
    for i in range(len(performance)):
        for j in range(i + 1, len(performance)):
            rewards_i = performance[i].get("all_rewards", [])
            rewards_j = performance[j].get("all_rewards", [])
            min_len = min(len(rewards_i), len(rewards_j))
            if min_len < 5:
                results.append({
                    "exp_a": performance[i]["id"], "exp_b": performance[j]["id"],
                    "p_value": None, "significant": False, "note": "insufficient data",
                })
                continue

            ri = rewards_i[-min_len:]
            rj = rewards_j[-min_len:]
            t_stat, p_value = scipy_stats.ttest_ind(ri, rj)
            results.append({
                "exp_a": performance[i]["id"], "exp_b": performance[j]["id"],
                "t_statistic": float(t_stat), "p_value": float(p_value),
                "significant": p_value < 0.05,
            })
    return results
