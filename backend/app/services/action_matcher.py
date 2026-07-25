from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dtw import dynamic_time_warping
from .features import NormalizedPose, pose_feature_matrix


@dataclass(frozen=True, slots=True)
class ActionMatchAssessment:
    matched: bool
    expected_action_id: str
    closest_action_id: str | None
    expected_cost: float
    closest_cost: float
    confidence: float
    message: str


def assess_action_match(
    *,
    expected_action_id: str,
    candidate_variants: list[NormalizedPose],
    references: dict[str, NormalizedPose],
    action_names: dict[str, str],
    maximum_match_cost: float = 2.0,
    alternative_ratio: float = 0.65,
) -> ActionMatchAssessment:
    """Decide whether a clip is the selected dance before giving technique advice."""

    if expected_action_id not in references:
        raise KeyError(f"动作 {expected_action_id} 没有可用参考")
    if not candidate_variants:
        raise ValueError("没有可用于动作匹配的骨架")

    costs = {
        action_id: min(
            dynamic_time_warping(
                pose_feature_matrix(reference),
                pose_feature_matrix(candidate),
            ).normalized_cost
            for candidate in candidate_variants
        )
        for action_id, reference in references.items()
    }
    expected_cost = float(costs[expected_action_id])
    closest_action_id = min(costs, key=costs.get)
    closest_cost = float(costs[closest_action_id])
    clear_alternative = (
        closest_action_id != expected_action_id
        and closest_cost <= maximum_match_cost
        and closest_cost < expected_cost * alternative_ratio
    )
    matched = expected_cost <= maximum_match_cost and not clear_alternative
    expected_name = action_names.get(expected_action_id, expected_action_id)

    if matched:
        confidence = float(np.clip(1.0 - expected_cost / maximum_match_cost * 0.5, 0.5, 0.99))
        message = f"动作身份通过：这段和《{expected_name}》属于同一套动作。"
        reported_closest: str | None = expected_action_id
    elif clear_alternative:
        closest_name = action_names.get(closest_action_id, closest_action_id)
        confidence = float(np.clip(1.0 - closest_cost / max(expected_cost, 1e-6), 0.55, 0.99))
        message = f"这段更像《{closest_name}》，不是当前的《{expected_name}》。请换成同一段动作再试。"
        reported_closest = closest_action_id
    else:
        confidence = float(
            np.clip((expected_cost - maximum_match_cost) / maximum_match_cost + 0.55, 0.55, 0.95)
        )
        message = f"这段动作和《{expected_name}》对不上。请上传同一段舞的 3–8 秒模仿。"
        reported_closest = None

    return ActionMatchAssessment(
        matched=matched,
        expected_action_id=expected_action_id,
        closest_action_id=reported_closest,
        expected_cost=expected_cost,
        closest_cost=closest_cost,
        confidence=confidence,
        message=message,
    )
