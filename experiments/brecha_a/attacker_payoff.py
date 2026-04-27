"""
Brecha A — Attacker payoff metric (post-run analysis).

Computes TWO payoff timelines per run:

1) `payoff_binary` (original, conservative):
       +1.0 if focal reached goal (only on the last cycle of a completed run)
       -2.0 * (count of focal detections this cycle, ignoring deference_*)
       -0.5 if focal trust < 0.999 this cycle

2) `payoff_proportional` (refined, captures continuous cost):
       +1.0 * task_progress_fraction_this_cycle
            (per-cycle delta of cumulative goal-progress in [0,1])
       -2.0 * detection_severity_this_cycle
            (deference level / 4 ∈ {0.0, 0.25, 0.5, 0.75, 1.0})
       -2.0 * (1.0 - trust_score_this_cycle)
            (single trust-degradation term with explicit coefficient -2.0,
             capturing both the immediate reduction of the attacker's
             weight in Γ and the opportunity cost of degraded trust in
             future rounds. In MAZ3 v1.1.0 weight_in_Γ ≡ trust_score by
             construction — `apply_trust_weights` copies the ARGUS score
             into each projection's _trust_weight, and Γ uses that weight
             directly — so consolidating these into a single term with
             coefficient 2.0 avoids spurious double-counting while
             preserving the same numerical contribution.)

The "focal agent" is identified by agent_id (e.g., "focal_inflator"). The
mapping agent_id → anonymous_index must be supplied at compute time (captured
from the engine after initialization). For the proportional metric we also
need `distances_per_cycle: dict[int, float]` (Euclidean distance to the focal's
goal at the END of each cycle), captured by the runner.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PayoffRow:
    cycle: int
    payoff_binary: float
    payoff_proportional: float
    trust: float
    weight_in_gamma: float
    n_detections: int
    deference_level: int  # 0..4 if known, -1 if missing
    detection_severity: float  # in [0,1]
    weight_below_one: bool
    task_completed: bool
    task_progress_fraction: float  # delta progress this cycle (can be negative)


@dataclass
class PayoffResult:
    focal_agent_id: str
    focal_agent_index: int
    rows: list[PayoffRow] = field(default_factory=list)
    final_trust: float = 1.0
    total_detections: int = 0
    task_completed_at_cycle: Optional[int] = None


def _severity_from_deference_level(level: int) -> float:
    """D0 → 0.0, D1 → 0.25, D2 → 0.5, D3 → 0.75, D4 → 1.0. Unknown → 0.0."""
    if level is None or level < 0:
        return 0.0
    if level >= 4:
        return 1.0
    return level / 4.0


def compute_attacker_payoff(
    db_path: str,
    session_id: str,
    focal_agent_id: str,
    focal_agent_index: int,
    final_distance_to_goal: float,
    distances_per_cycle: Optional[dict[int, float]] = None,
    initial_distance_to_goal: Optional[float] = None,
    completion_threshold_m: float = 2.0,
) -> PayoffResult:
    """
    Compute payoff timelines (binary + proportional) for the focal agent.

    Args:
        db_path: SQLite DB written by the engine.
        session_id: session row id in maze_sessions.
        focal_agent_id: e.g. "focal_inflator".
        focal_agent_index: anonymous index assigned by SovereignProjectionBuffer.
        final_distance_to_goal: distance at end of run (used for completion).
        distances_per_cycle: {cycle → distance_to_goal_at_end_of_cycle}.
                             Required for `payoff_proportional`. If None, the
                             proportional task-progress term is 0.0.
        initial_distance_to_goal: distance at cycle 0 (used to normalize
                                  task_progress_fraction). If None, taken from
                                  distances_per_cycle's first entry.
        completion_threshold_m: distance below which task is considered completed.
    """
    result = PayoffResult(
        focal_agent_id=focal_agent_id,
        focal_agent_index=focal_agent_index,
    )

    completed_overall = final_distance_to_goal <= completion_threshold_m

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # Detection events for this focal agent
        cur.execute(
            "SELECT cycle_number, attack_type, details "
            "FROM detection_events WHERE session_id = ? "
            "ORDER BY cycle_number ASC",
            (session_id,),
        )
        det_per_cycle: dict[int, int] = {}
        for row in cur.fetchall():
            details_str = row["details"]
            if not details_str:
                continue
            try:
                d = json.loads(details_str)
            except (json.JSONDecodeError, TypeError):
                continue
            idx = d.get("agent_index")
            if idx == focal_agent_index:
                attack_type = row["attack_type"]
                if attack_type and not attack_type.startswith("deference_"):
                    det_per_cycle[row["cycle_number"]] = (
                        det_per_cycle.get(row["cycle_number"], 0) + 1
                    )

        # Trust / weight per cycle from flight_snapshots (same scalar in v1.1.0).
        cur.execute(
            "SELECT cycle_number, agent_projections "
            "FROM flight_snapshots WHERE session_id = ? "
            "ORDER BY cycle_number ASC",
            (session_id,),
        )
        trust_per_cycle: dict[int, float] = {}
        for row in cur.fetchall():
            projections_str = row["agent_projections"]
            if not projections_str:
                continue
            try:
                projections = json.loads(projections_str)
            except (json.JSONDecodeError, TypeError):
                continue
            for proj in projections:
                if proj.get("_index") == focal_agent_index:
                    trust_per_cycle[row["cycle_number"]] = float(
                        proj.get("_trust_weight", 1.0)
                    )

        # Deference level per cycle (for severity) from custom_metrics.
        cur.execute(
            "SELECT cycle_number, metadata FROM custom_metrics "
            "WHERE session_id = ? AND metric_name = 'agent_intent_compliance' "
            "ORDER BY cycle_number ASC",
            (session_id,),
        )
        deference_per_cycle: dict[int, int] = {}
        for row in cur.fetchall():
            md_str = row["metadata"]
            if not md_str:
                continue
            try:
                md = json.loads(md_str)
            except (json.JSONDecodeError, TypeError):
                continue
            if md.get("agent_index") == focal_agent_index:
                lvl = md.get("deference_level")
                if isinstance(lvl, (int, float)):
                    deference_per_cycle[row["cycle_number"]] = int(lvl)

        cycles = sorted(set(
            list(det_per_cycle.keys())
            + list(trust_per_cycle.keys())
            + list(deference_per_cycle.keys())
        ))
        if not cycles:
            return result
        last_cycle = max(cycles)

        # Task progress normalisation
        d0 = initial_distance_to_goal
        if d0 is None and distances_per_cycle:
            d0 = distances_per_cycle.get(min(distances_per_cycle.keys()))
        if d0 is None or d0 <= 1e-6:
            d0 = max(1.0, final_distance_to_goal)  # safe fallback

        prev_progress = 0.0  # cumulative progress before cycle 0

        for c in cycles:
            n_det = det_per_cycle.get(c, 0)
            trust = trust_per_cycle.get(c, 1.0)
            weight = trust  # equal in v1.1.0
            detected = n_det > 0
            weight_below_one = trust < 0.999
            task_now_done = completed_overall and (c == last_cycle)
            lvl = deference_per_cycle.get(c, -1)
            severity = _severity_from_deference_level(lvl)

            # Binary payoff (original)
            payoff_b = 0.0
            if task_now_done:
                payoff_b += 1.0
            payoff_b -= 2.0 * n_det
            if weight_below_one:
                payoff_b -= 0.5

            # Task progress fraction (proportional).
            if distances_per_cycle and c in distances_per_cycle:
                dist = distances_per_cycle[c]
                cum_progress = max(0.0, min(1.0, (d0 - dist) / d0))
            else:
                cum_progress = prev_progress
            tp_frac = cum_progress - prev_progress
            prev_progress = cum_progress

            # Single trust-degradation term, coefficient -2.0 (see module
            # docstring for design rationale). Avoids double-counting the
            # weight_in_Γ ≡ trust_score identity in MAZ3 v1.1.0.
            payoff_p = 0.0
            payoff_p += 1.0 * tp_frac
            payoff_p -= 2.0 * severity
            payoff_p -= 2.0 * (1.0 - trust)

            result.rows.append(PayoffRow(
                cycle=c,
                payoff_binary=payoff_b,
                payoff_proportional=payoff_p,
                trust=trust,
                weight_in_gamma=weight,
                n_detections=n_det,
                deference_level=lvl,
                detection_severity=severity,
                weight_below_one=weight_below_one,
                task_completed=task_now_done,
                task_progress_fraction=tp_frac,
            ))
            result.total_detections += n_det

        if completed_overall:
            result.task_completed_at_cycle = last_cycle
        if result.rows:
            result.final_trust = result.rows[-1].trust
        return result
    finally:
        conn.close()


def cumulative_payoff_binary(rows: list[PayoffRow]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    cum = 0.0
    for r in rows:
        cum += r.payoff_binary
        out.append((r.cycle, cum))
    return out


def cumulative_payoff_proportional(rows: list[PayoffRow]) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    cum = 0.0
    for r in rows:
        cum += r.payoff_proportional
        out.append((r.cycle, cum))
    return out


# Backwards-compatible alias used by older callers (returns binary).
def cumulative_payoff(rows: list[PayoffRow]) -> list[tuple[int, float]]:
    return cumulative_payoff_binary(rows)
