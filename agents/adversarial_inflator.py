"""
Adversarial Spatial Inflator — Claims more space than occupied.

Attack strategy: inflate spatial_envelope to 3-5x real size.
This pushes other agents away via the conservative composition
(union of envelopes → more claimed space → less room for others).

What SHOULD happen:
  - ARGUS detects inconsistency between declared envelope and actual movement
  - Trust score drops
  - Inflated claims get discounted in Γ via trust weights
  - The system remains safe because conservative composition still applies

What this tests:
  - P3 Claim: cooperative attack detection
  - P3 Claim: projection poisoning detection
  - P4 Claim: strategy-proof property (inflation incurs cost to inflator)

Patent ref: P3 Claims (adversarial detection), P4 Claim 54 (strategy-proof)
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


class AdversarialInflatorAgent(BaseAgent):
    """
    Inflates spatial envelope to claim more space than actually occupied.

    The inflation_factor controls how much larger the declared envelope
    is compared to real size. E.g., 3.0 = claims 3x the radius.

    The agent otherwise behaves normally (moves toward goal).
    This makes the attack subtle — it's not obviously broken,
    just dishonest about how much space it needs.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Optional[tuple[float, float]] = None,
        inflation_factor: float = 3.0,
        activate_after_cycle: int = 20,
    ) -> None:
        super().__init__(config)
        self._goal = goal or (config.start_position[0] + 30.0,
                              config.start_position[1])
        self._inflation_factor = inflation_factor
        self._activate_after = activate_after_cycle
        self._direction = (1.0, 0.0)
        self._speed = config.max_speed * 0.5
        self._boundary = (0, 0, 50, 50)
        self._local_risks: dict[str, float] = {}

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
        self._speed = self._config.max_speed * 0.5

        cell_id = f"{int(px)}_{int(py)}"
        self._local_risks = {cell_id: 0.2}

    def project(self) -> MVRProjection:
        """
        ATTACK: inflate spatial envelope when active.
        Before activation, behaves normally (builds trust history).
        """
        px, py = self._state.position
        r = self._config.envelope_radius

        if self.is_attacking:
            # Inflate: claim much more space than real
            r_inflated = r * self._inflation_factor
            envelope = SpatialEnvelope(
                px - r_inflated, py - r_inflated,
                px + r_inflated, py + r_inflated,
            )
        else:
            # Normal: build trust first
            envelope = SpatialEnvelope(px - r, py - r, px + r, py + r)

        return MVRProjection(
            spatial_envelope=envelope,
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
            risk_gradient=RiskGradient(cell_risks=dict(self._local_risks)),
        )

    def act(self, shared_mvr: dict, dt: float) -> None:
        """Moves normally — the attack is in the projection, not the action."""
        self.receive_shared_mvr(shared_mvr)

        speed = self._speed
        direction = self._direction

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
