from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class DTWResult:
    normalized_cost: float
    path: list[tuple[int, int]]


def dynamic_time_warping(reference: np.ndarray, candidate: np.ndarray) -> DTWResult:
    if reference.ndim != 2 or candidate.ndim != 2:
        raise ValueError("DTW 输入必须是二维特征矩阵")
    n, m = len(reference), len(candidate)
    if n == 0 or m == 0:
        raise ValueError("DTW 输入不能为空")

    cost = np.full((n + 1, m + 1), np.inf, dtype=np.float64)
    cost[0, 0] = 0.0
    predecessor = np.zeros((n, m, 2), dtype=np.int32)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            distance = float(np.linalg.norm(reference[i - 1] - candidate[j - 1]))
            options = (cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
            choice = int(np.argmin(options))
            cost[i, j] = distance + options[choice]
            if choice == 0:
                predecessor[i - 1, j - 1] = (i - 2, j - 1)
            elif choice == 1:
                predecessor[i - 1, j - 1] = (i - 1, j - 2)
            else:
                predecessor[i - 1, j - 1] = (i - 2, j - 2)

    i, j = n - 1, m - 1
    path: list[tuple[int, int]] = []
    while i >= 0 and j >= 0:
        path.append((i, j))
        previous_i, previous_j = predecessor[i, j]
        if previous_i == i and previous_j == j:
            break
        i, j = int(previous_i), int(previous_j)
    path.reverse()
    return DTWResult(normalized_cost=float(cost[n, m] / max(len(path), 1)), path=path)


def aligned_pairs(path: list[tuple[int, int]]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([item[0] for item in path], dtype=np.int32),
        np.asarray([item[1] for item in path], dtype=np.int32),
    )
