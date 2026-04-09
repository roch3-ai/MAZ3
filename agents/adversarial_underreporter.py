"""
Adversarial Risk Underreporter — Declares low risk in dangerous areas.

Attack strategy: report risk_gradient values near 0 everywhere,
even in cells where the agent knows there is real danger.
This tries to manipulate the conservative composition: if all agents
report low risk, M*.risk will be low, and other agents won't slow down
in dangerous areas.

What SHOULD happen:
  - Conservative composition uses MAX risk per cell
  - Even one honest agent reporting high risk overrides the underreporter
  - ARGUS detects that this agent's risk reports don't correlate with
    actual events (e.g., near-misses happen in cells it declared safe)
  - Trust score drops → risk reports get discounted

What this tests:
  - P3 Claim: under-reporting detection
  - P4 Claim 54: strategy-proof (under-reporting risk incurs cost when
    true risk manifests)
  - Γ's pessimistic risk aggregation (max per cell)
"""

from __future__ import annotations

import math
import time
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)


class AdversarialUnderreporterAgent(BaseAgent):
    """
    Under-reports risk to manipulate shared risk gradient.

    Declares risk ≈ 0 in all cells, regardless of actual conditions.
    Moves at high speed through areas it declares "safe."

    The attack is subtle: the agent doesn't claim impossible things
    about space or time — it just lies about risk assessment.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Optional[tuple[float, float]] = None,
        activate_after_cycle: int = 15,
    ) -> None:
        super().__init__(config)
        self._goal = goal or (config.start_position[0] + 30.0,
                              config.start_position[1])
        self._activate_after = activate_after_cycle
        self._direction = (1.0, 0.0)
        self._speed = config.max_speed * 0.8  # Faster than normal — reckless
        self._boundary = (0, 0, 50, 50)
        self._true_risks: dict[str, float] = {}  # What it really sees

    @property
    def is_attacking(self) -> bool:
        return self._cycle >= self._activate_after

    def sense(self, environment: dict) -> None:
        if "boundary" in environment:
            self._boundary = environment["boundary"]

    def infer(self) -> None:
        px, py = self._state.position
        gx, gy = self._goal

        dx = gx - px
        dy = gy - py
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 0.5:
            self._direction = (0.0, 0.0)
            self._speed = 0.0
            return

        self._direction = (dx / dist, dy / dist)
        self._speed = self._config.max_speed * 0.8

        # Compute TRUE risk (agent knows it's risky near boundaries)
        cell_id = f"{int(px)}_{int(py)}"
        bx0, by0, bx1, by1 = self._boundary
        dist_to_boundary = min(px - bx0, bx1 - px, py - by0, by1 - py)
        true_risk = max(0.0, 1.0 - dist_to_boundary / 5.0) * 0.6
        self._true_risks = {cell_id: true_risk}

    def project(self) -> MVRProjection:
        """
        ATTACK: under-report risk when active.
        Reports near-zero risk everywhere.
        """
        px, py = self._state.position
        r = self._config.envelope_radius

        if self.is_attacking:
            # Lie: declare everything is safe
            cell_id = f"{int(px)}_{int(py)}"
            declared_risks = {cell_id: 0.01}  # Almost zero
        else:
            # Before activation: report honestly (build trust)
            declared_risks = dict(self._true_risks)

        return MVRProjection(
            spatial_envelope=SpatialEnvelope(px - r, py - r, px + r, py + r),
            temporal_sync=TemporalSync(time.time(), drift_bound_ms=3.0),
            intent_vector=IntentVector(
                direction=self._direction,
                speed=self._speed,
                action_type="move" if self._speed > 0.01 else "stop",
            ),
            constraint_set=ConstraintSet(
                max_speed=self._config.max_speed,
                min_separation=self._config.min_separation,
            ),
            risk_gradient=RiskGradient(cell_risks=declared_risks),
        )

    def act(self, shared_mvr: dict, dt: float) -> None:
        """Moves at high speed — doesn't respect risk warnings."""
        self.receive_shared_mvr(shared_mvr)

        speed = self._speed
        direction = self._direction

        # Only stops for D3/D4 (physically enforced)
        if shared_mvr and "constraint_set" in shared_mvr:
            max_spd = shared_mvr["constraint_set"].get("max_speed", self._config.max_speed)
            if max_spd <= 0:
                speed = 0.0

        vx = direction[0] * speed
        vy = direction[1] * speed
        self._state.velocity = (vx, vy)
        self._state.speed = speed

        px, py = self._state.position
        new_px = px + vx * dt
        new_py = py + vy * dt

        bx0, by0, bx1, by1 = self._boundary
        new_px = max(bx0 + 0.1, min(bx1 - 0.1, new_px))
        new_py = max(by0 + 0.1, min(by1 - 0.1, new_py))

        self._state.position = (new_px, new_py)
        if speed > 0.01:
            self._state.heading = math.atan2(vy, vx)
        self.advance_cycle()
