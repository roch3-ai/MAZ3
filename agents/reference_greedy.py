"""
Reference Greedy Agent — Baseline that ignores coordination.

Moves straight toward its goal at maximum speed.
Projects honest MVR fields but IGNORES the shared MVR constraints.
It doesn't re-plan when M* says it should — it just barrels through.

This agent exists to show WHAT HAPPENS without deference.
It should produce:
- Low H_p scores (spatial conflicts)
- High ΔK values (kinetic risk)
- D2+ deference interventions from the safety system

The gap between Syncference agent and Greedy agent IS the value
of the coordination protocol.
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


class ReferenceGreedyAgent(BaseAgent):
    """
    Greedy agent. Goes straight to goal, doesn't yield.
    Honest projections — it tells the truth about what it plans to do.
    But it ignores what others project and what M* recommends.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Optional[tuple[float, float]] = None,
    ) -> None:
        super().__init__(config)
        self._goal = goal or (config.start_position[0] + 30.0,
                              config.start_position[1])
        self._direction = (1.0, 0.0)
        self._speed = config.max_speed  # Full speed always
        self._boundary = (0, 0, 50, 50)

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
        self._speed = self._config.max_speed  # ALWAYS full speed — greedy

        # Under-reports risk (sees danger but declares low)
        # This is honest in the sense that the agent genuinely doesn't care about risk
        cell_id = f"{int(px)}_{int(py)}"
        self._local_risks = {cell_id: 0.05}  # Always says "low risk"

    def project(self) -> MVRProjection:
        """Honest projection — declares intent to go full speed."""
        px, py = self._state.position
        r = self._config.envelope_radius
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
            risk_gradient=RiskGradient(
                cell_risks=getattr(self, '_local_risks', {}),
            ),
        )

    def act(self, shared_mvr: dict, dt: float) -> None:
        """
        IGNORES shared MVR constraints (except deference-imposed ones).

        The greedy agent WILL respect D3/D4 (commanded stop / emergency veto)
        because those are physically enforced, not advisory.
        But it ignores D1 advisories and D2 speed corrections voluntarily.

        In a real system, D3/D4 would be enforced at the actuator level.
        Here we simulate that: if max_speed is 0, the agent stops.
        """
        self.receive_shared_mvr(shared_mvr)

        speed = self._speed
        direction = self._direction

        # Only respect hard physical constraints (D3/D4 → max_speed = 0)
        if shared_mvr and "constraint_set" in shared_mvr:
            max_spd = shared_mvr["constraint_set"].get("max_speed", self._config.max_speed)
            if max_spd <= 0:
                # D3/D4: physically enforced stop
                speed = 0.0
            # Otherwise: ignore speed reduction (greedy doesn't yield)

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
