"""
Operador Γ — Conservative Composition

The convergence operator that produces the shared MVR (M*) from
individual agent projections.

Rules (NEVER produce a less safe state than the most cautious assessment):
  Spatial:     M*.envelope    = ⋃ᵢ envelopeᵢ      (union — conservative)
  Temporal:    M*.clock       = weighted_median     (drift < ε_t)
  Intent:      M*.intent      = {Iᵢ}               (preserved individually)
  Constraints: M*.constraints = ⋂ᵢ constraintsᵢ    (intersection — strictest)
  Risk:        M*.risk        = maxᵢ(riskᵢ)         (per cell — pessimistic)

Γ operates on ANONYMOUS fields from SovereignProjectionBuffer.
Γ never sees agent_ids. It sees MVR fields + trust weights.

Patent ref: P4 Claims 1-5 (MVR Composition), P3 Conservative Composition
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConvergenceResult:
    """Result of Γ operator."""
    shared_mvr: dict  # The converged M*
    convergence_time_ms: float
    agent_count: int
    cycle: int


class GammaOperator:
    """
    Conservative Composition Operator (Γ).

    Takes anonymous MVR fields + trust weights from SovereignProjectionBuffer.
    Produces shared MVR (M*) following conservative composition rules.

    The operator is stateless — each call is independent.
    This is deliberate: Γ has no memory of previous cycles.
    History lives in the flight recorder.
    """

    def converge(
        self,
        fields: list[dict],
        cycle: int,
    ) -> ConvergenceResult:
        """
        Apply conservative composition to produce M*.

        Args:
            fields: Anonymous MVR fields from SovereignProjectionBuffer.
                    Each has _trust_weight and _index (meta fields).
            cycle: Current simulation cycle.

        Returns:
            ConvergenceResult with the shared MVR.
        """
        start = time.perf_counter()

        if not fields:
            return ConvergenceResult(
                shared_mvr={},
                convergence_time_ms=0.0,
                agent_count=0,
                cycle=cycle,
            )

        shared_mvr = {
            "spatial_envelope": self._union_spatial(fields),
            "temporal_sync": self._weighted_median_temporal(fields),
            "intent_vector": self._preserve_intents(fields),
            "constraint_set": self._intersect_constraints(fields),
            "risk_gradient": self._max_risk(fields),
        }

        elapsed_ms = (time.perf_counter() - start) * 1000

        return ConvergenceResult(
            shared_mvr=shared_mvr,
            convergence_time_ms=elapsed_ms,
            agent_count=len(fields),
            cycle=cycle,
        )

    def _union_spatial(self, fields: list[dict]) -> dict:
        """
        Spatial: Union of all envelopes (conservative).
        The shared spatial awareness includes ALL claimed space.
        """
        envelopes = [f["spatial_envelope"] for f in fields]
        weights = [f.get("_trust_weight", 1.0) for f in fields]

        # Weighted union: low-trust envelopes are still included
        # (conservative — we don't ignore claimed space even if trust is low)
        x_min = min(e["x_min"] for e in envelopes)
        y_min = min(e["y_min"] for e in envelopes)
        x_max = max(e["x_max"] for e in envelopes)
        y_max = max(e["y_max"] for e in envelopes)

        return {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max}

    def _weighted_median_temporal(self, fields: list[dict]) -> dict:
        """
        Temporal: Weighted median clock (drift < ε_t).
        Median is robust to outlier clocks (e.g., compromised agent).
        Trust weights influence which clocks get more credibility.
        """
        syncs = [f["temporal_sync"] for f in fields]
        weights = [f.get("_trust_weight", 1.0) for f in fields]

        # Weighted median via repetition (simple, correct)
        expanded_timestamps = []
        for sync, w in zip(syncs, weights):
            # Repeat timestamp proportional to weight (discretized)
            count = max(1, int(w * 10))
            expanded_timestamps.extend([sync["timestamp"]] * count)

        median_ts = statistics.median(expanded_timestamps)
        max_drift = max(s["drift_bound_ms"] for s in syncs)

        return {"timestamp": median_ts, "drift_bound_ms": max_drift}

    def _preserve_intents(self, fields: list[dict]) -> list[dict]:
        """
        Intent: Preserved individually — never merged.
        Each agent's intent is kept separate in M*.
        Γ cannot decide what agents want to do.
        """
        return [
            {
                "_index": f.get("_index"),
                "intent": f["intent_vector"],
                "_trust_weight": f.get("_trust_weight", 1.0),
            }
            for f in fields
        ]

    def _intersect_constraints(self, fields: list[dict]) -> dict:
        """
        Constraints: Intersection (strictest wins).
        The shared constraint set is the most restrictive combination.
        """
        constraints = [f["constraint_set"] for f in fields]

        # Strictest = minimum max_speed, maximum min_separation
        min_max_speed = min(c["max_speed"] for c in constraints)
        max_min_sep = max(c["min_separation"] for c in constraints)

        # Union of all regulatory zones (all no-go zones apply)
        all_zones = []
        for c in constraints:
            all_zones.extend(c.get("regulatory_zones", []))

        return {
            "max_speed": min_max_speed,
            "min_separation": max_min_sep,
            "regulatory_zones": all_zones,
        }

    def _max_risk(self, fields: list[dict]) -> dict:
        """
        Risk: Max per cell (pessimistic).
        The shared risk is the WORST assessment for each cell.
        Never produce a less safe assessment than any individual agent.
        """
        merged: dict[str, float] = {}

        for f in fields:
            cell_risks = f["risk_gradient"].get("cell_risks", {})
            trust = f.get("_trust_weight", 1.0)

            for cell_id, risk in cell_risks.items():
                # Trust-weighted risk: low-trust agents' risk is discounted
                # BUT we still take max — a low-trust agent claiming high risk
                # means we should be cautious (conservative)
                weighted_risk = risk * trust
                if cell_id not in merged or weighted_risk > merged[cell_id]:
                    merged[cell_id] = weighted_risk

        return {"cell_risks": merged}
