"""
OmniscientCoordinator v2 — Γ with lossless MVR inputs.

Unlike v1 (``agents/omniscient_coordinator.py``), v2 is NOT a BaseAgent. It is
an engine-level coordinator that replaces the GammaOperator for a session:

- Agents in an "omniscient_v2" session are standard ReferenceSyncferenceAgent
  instances. They project, sense, infer and act exactly as in a "syncference"
  session.
- The engine, in Phase 4 (CONVERGE), bypasses the SovereignProjectionBuffer
  and instead builds a ground-truth state dict from engine-internal knowledge.
- That ground-truth dict is fed to OmniscientProjector, which produces one
  lossless MVRProjection per agent (same schema as a Syncference projection,
  but with zero-drift clocks, exact kinodynamic constraints, exact risk
  field, and an exact swept-volume spatial envelope).
- The lossless projections are composed by the SAME GammaOperator used by
  Syncference. Only the input quality differs.

This isolates input fidelity as the only independent variable between
"syncference" and "omniscient_v2" runs. The SBE claim (§5.2) is then a
direct test of whether lossy MVRs produce different M* than lossless ones.

Patent ref: P4 Claim 74 (coordination quality); Paper 1 §5.2 (SBE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from roch3.convergence import ConvergenceResult, GammaOperator
from roch3.mvr import (
    ConstraintSet, IntentVector, MVRProjection, RiskGradient,
    SpatialEnvelope, TemporalSync,
)


@dataclass
class AgentGroundTruth:
    """
    Full per-agent state as seen from an omniscient vantage point.
    Constructed by the engine from its internal knowledge of each agent.
    """
    position: tuple              # (x, y)
    velocity: tuple              # (vx, vy)
    radius: float                # agent footprint radius (envelope_radius)
    global_time: float           # exact timestamp (no drift)
    planned_direction: tuple     # unit vector
    planned_speed: float
    action_type: str             # "move" | "stop"
    true_max_speed: float
    true_min_separation: float
    true_risk_field: dict        # {cell_id: risk in [0,1]}
    true_restricted_zones: List[dict] = field(default_factory=list)


class OmniscientProjector:
    """
    Build a lossless MVRProjection from per-agent ground-truth state.

    "Lossless" here means: no drift bound, exact bounding box of the swept
    volume, exact kinodynamic constraints, exact risk field, true planned
    intent. The output still conforms to the MVRProjection schema so that
    GammaOperator can compose it without modification.
    """

    def __init__(self, horizon: float = 2.0, dt: float = 0.1) -> None:
        self._horizon = horizon
        self._dt = dt

    def project_lossless(self, gt: AgentGroundTruth) -> MVRProjection:
        px, py = gt.position
        vx, vy = gt.velocity
        r = gt.radius

        # Spatial envelope: bounding box of the swept path over [0, horizon].
        end_x = px + vx * self._horizon
        end_y = py + vy * self._horizon
        envelope = SpatialEnvelope(
            x_min=min(px, end_x) - r,
            y_min=min(py, end_y) - r,
            x_max=max(px, end_x) + r,
            y_max=max(py, end_y) + r,
        )

        return MVRProjection(
            spatial_envelope=envelope,
            temporal_sync=TemporalSync(
                timestamp=gt.global_time,
                drift_bound_ms=0.0,
            ),
            intent_vector=IntentVector(
                direction=gt.planned_direction,
                speed=gt.planned_speed,
                action_type=gt.action_type,
            ),
            constraint_set=ConstraintSet(
                max_speed=gt.true_max_speed,
                min_separation=gt.true_min_separation,
                regulatory_zones=list(gt.true_restricted_zones or []),
            ),
            risk_gradient=RiskGradient(
                cell_risks=dict(gt.true_risk_field or {}),
            ),
        )


class OmniscientCoordinatorV2:
    """
    Drop-in Γ replacement for omniscient_v2 sessions.

    Usage (by the engine, not by agents):

        self._omni_v2 = OmniscientCoordinatorV2()
        ...
        # Phase 4, omni_v2 branch:
        gt_states = self._build_ground_truth_states()
        convergence_result = self._omni_v2.coordinate(gt_states, self._cycle)
        fields = self._omni_v2.last_fields()  # for harmony computation
    """

    def __init__(self, horizon: float = 2.0, dt: float = 0.1) -> None:
        self._projector = OmniscientProjector(horizon=horizon, dt=dt)
        self._gamma = GammaOperator()
        self._last_fields: List[dict] = []

    def coordinate(
        self,
        ground_truth_states: Dict[str, AgentGroundTruth],
        cycle: int,
    ) -> ConvergenceResult:
        fields: List[dict] = []
        for i, (_agent_id, gt) in enumerate(ground_truth_states.items()):
            mvr = self._projector.project_lossless(gt)
            d = mvr.to_dict()
            d["_trust_weight"] = 1.0
            d["_index"] = i
            fields.append(d)
        self._last_fields = fields
        return self._gamma.converge(fields, cycle)

    def last_fields(self) -> List[dict]:
        return list(self._last_fields)
