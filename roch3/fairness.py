"""
Fairness Index — F(t)

F = 1 - std(wait_times) / mean(wait_times)

F = 1.0: perfectly fair (all agents wait the same)
F → 0.0: systematically unfair (one agent always waits)

Uses coefficient of variation (CV) so the metric is scale-invariant:
a system where everyone waits 10s is as fair as one where everyone waits 100s.

Design rationale:
  We use CV rather than raw std to allow fair comparison across scenarios
  with different durations and agent counts. This is the standard approach
  in queueing theory and traffic engineering.

Boundary cases:
  - Single agent: F = 1.0 (trivially fair)
  - All wait times zero: F = 1.0 (no waiting = fair)
  - Fewer than 2 agents: F = 1.0

Patent ref: Custom metrics extension (custom_metrics table, Phase 2+)
Used in: Intersection scenario, Corridor scenario (fairness of completion)
Paper ref: Paper 1 Table 3×3 (fairness column)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass
class FairnessResult:
    """Full Fairness Index computation result."""
    fairness_index: float   # [0, 1] — 1 is perfectly fair
    mean_wait: float        # mean wait time
    std_wait: float         # standard deviation of wait times
    cv: float               # coefficient of variation (std/mean)
    n_agents: int           # number of agents measured
    all_equal: bool         # True if all wait times are identical


def compute_fairness_index(wait_times: list[float]) -> float:
    """
    Compute Fairness Index from a list of per-agent wait times.

    F = max(0, 1 - std(wait_times) / mean(wait_times))

    Returns 1.0 for trivial inputs (< 2 agents, all-zero, all-equal).

    Args:
        wait_times: Per-agent wait time in any consistent unit
                    (cycles, seconds, etc.)

    Returns:
        float in [0, 1]
    """
    if not wait_times or len(wait_times) < 2:
        return 1.0

    n = len(wait_times)
    mean = sum(wait_times) / n
    if mean <= 0.0:
        return 1.0

    # Population std (not sample — we have the full population)
    variance = sum((x - mean) ** 2 for x in wait_times) / n
    std = math.sqrt(variance)
    cv = std / mean

    return max(0.0, 1.0 - cv)


def compute_fairness_result(wait_times: list[float]) -> FairnessResult:
    """
    Full Fairness computation with diagnostics.

    Returns FairnessResult with index and components for Paper 1 tables.
    """
    if not wait_times or len(wait_times) < 2:
        return FairnessResult(
            fairness_index=1.0,
            mean_wait=sum(wait_times) / len(wait_times) if wait_times else 0.0,
            std_wait=0.0,
            cv=0.0,
            n_agents=len(wait_times),
            all_equal=True,
        )

    n = len(wait_times)
    mean = sum(wait_times) / n
    variance = sum((x - mean) ** 2 for x in wait_times) / n
    std = math.sqrt(variance)
    cv = std / mean if mean > 0.0 else 0.0
    fairness = max(0.0, 1.0 - cv) if mean > 0.0 else 1.0

    all_equal = std < 1e-9

    return FairnessResult(
        fairness_index=fairness,
        mean_wait=mean,
        std_wait=std,
        cv=cv,
        n_agents=n,
        all_equal=all_equal,
    )
