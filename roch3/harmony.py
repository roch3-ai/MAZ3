"""
Harmony Index — H_p(t)

H_p(t) = 1 - ((D_spatial^p + D_temporal^p + D_risk^p) / 3)^(1/p)

p = 3: a single catastrophic outlier dominates the score.
This is deliberate — coordination that's perfect in 2 dimensions
but terrible in 1 is NOT safe coordination.

Thresholds:
  H_p > 0.85   → healthy coordination
  0.55 ≤ H_p   → attention required
  H_p < 0.55   → reduce operational density

Patent ref: P4 Claims (Harmony Index as coordination metric)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# Default p-norm exponent
DEFAULT_P = 3

# Thresholds
THRESHOLD_HEALTHY = 0.85
THRESHOLD_ATTENTION = 0.55


@dataclass
class HarmonyComponents:
    """Individual divergence components before aggregation."""
    d_spatial: float   # [0, 1] spatial divergence
    d_temporal: float  # [0, 1] temporal divergence
    d_risk: float      # [0, 1] risk divergence


@dataclass
class HarmonyResult:
    """Full Harmony Index computation result."""
    h_p: float
    components: HarmonyComponents
    p: int
    status: str  # "healthy" | "attention" | "critical"
    cycle: int


def compute_spatial_divergence(fields: list[dict]) -> float:
    """
    Spatial divergence: how much do spatial envelopes violate safety constraints?

    Measures proximity violations — agents whose centers are closer than
    min_separation produce divergence. Raw envelope overlap alone is not
    necessarily dangerous (agents in a corridor will have adjacent envelopes).

    What matters: are agents dangerously close given their constraints?
    """
    if len(fields) < 2:
        return 0.0

    envelopes = [f["spatial_envelope"] for f in fields]
    constraints = [f.get("constraint_set", {}) for f in fields]

    max_violation = 0.0
    pair_count = 0

    for i in range(len(envelopes)):
        ei = envelopes[i]
        ci_x = (ei["x_min"] + ei["x_max"]) / 2
        ci_y = (ei["y_min"] + ei["y_max"]) / 2
        min_sep_i = constraints[i].get("min_separation", 2.0)

        for j in range(i + 1, len(envelopes)):
            ej = envelopes[j]
            cj_x = (ej["x_min"] + ej["x_max"]) / 2
            cj_y = (ej["y_min"] + ej["y_max"]) / 2
            min_sep_j = constraints[j].get("min_separation", 2.0)

            # Use the stricter (larger) min_separation
            required_sep = max(min_sep_i, min_sep_j)

            # Distance between centers
            dist = math.sqrt((ci_x - cj_x) ** 2 + (ci_y - cj_y) ** 2)

            # Violation: how much closer than required?
            # 0 = at or beyond required separation
            # 1 = on top of each other
            if dist < required_sep:
                violation = 1.0 - (dist / required_sep)
                max_violation = max(max_violation, violation)

            pair_count += 1

    return min(1.0, max_violation)


def compute_temporal_divergence(fields: list[dict]) -> float:
    """
    Temporal divergence: how far apart are agent clocks?

    Uses drift bounds — if max pairwise clock difference exceeds
    sum of drift bounds, there's temporal divergence.
    """
    if len(fields) < 2:
        return 0.0

    syncs = [f["temporal_sync"] for f in fields]
    timestamps = [s["timestamp"] for s in syncs]
    drift_bounds = [s["drift_bound_ms"] for s in syncs]

    max_diff_ms = (max(timestamps) - min(timestamps)) * 1000  # to ms
    max_allowed = sum(drift_bounds)  # generous: sum of all bounds

    if max_allowed <= 0:
        return 1.0 if max_diff_ms > 0 else 0.0

    divergence = min(1.0, max_diff_ms / max_allowed)
    return divergence


def compute_risk_divergence(fields: list[dict]) -> float:
    """
    Risk divergence: how much do risk assessments disagree?

    For each cell, compare per-agent risk values.
    High variance = agents disagree on danger = divergence.
    """
    if len(fields) < 2:
        return 0.0

    # Collect all cell IDs across agents
    all_cells: set[str] = set()
    risk_maps = []
    for f in fields:
        rm = f["risk_gradient"]["cell_risks"]
        risk_maps.append(rm)
        all_cells.update(rm.keys())

    if not all_cells:
        return 0.0

    total_variance = 0.0
    for cell_id in all_cells:
        values = []
        for rm in risk_maps:
            values.append(rm.get(cell_id, 0.0))  # absent = 0 risk assumed
        if len(values) >= 2:
            mean = sum(values) / len(values)
            var = sum((v - mean) ** 2 for v in values) / len(values)
            total_variance += var

    # Normalize: max possible variance for [0,1] values is 0.25
    avg_variance = total_variance / len(all_cells)
    divergence = min(1.0, avg_variance / 0.25)
    return divergence


def compute_harmony_index(
    fields: list[dict],
    cycle: int,
    p: int = DEFAULT_P,
) -> HarmonyResult:
    """
    Compute H_p(t) = 1 - ((D_spatial^p + D_temporal^p + D_risk^p) / 3)^(1/p)

    Args:
        fields: Anonymous MVR fields from SovereignProjectionBuffer
        cycle: Current simulation cycle number
        p: Norm exponent (default 3 — one bad dimension dominates)

    Returns:
        HarmonyResult with score, components, and status
    """
    d_spatial = compute_spatial_divergence(fields)
    d_temporal = compute_temporal_divergence(fields)
    d_risk = compute_risk_divergence(fields)

    components = HarmonyComponents(
        d_spatial=d_spatial,
        d_temporal=d_temporal,
        d_risk=d_risk,
    )

    # H_p computation
    if p <= 0:
        raise ValueError(f"p must be positive, got {p}")

    norm = ((d_spatial ** p + d_temporal ** p + d_risk ** p) / 3) ** (1 / p)
    h_p = 1.0 - min(1.0, norm)  # clamp to [0, 1]

    # Status classification
    if h_p > THRESHOLD_HEALTHY:
        status = "healthy"
    elif h_p >= THRESHOLD_ATTENTION:
        status = "attention"
    else:
        status = "intervene"

    return HarmonyResult(
        h_p=h_p,
        components=components,
        p=p,
        status=status,
        cycle=cycle,
    )
