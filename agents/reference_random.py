"""
Reference Random Agent — Baseline with no strategy.

Moves in random directions, projects honest MVR fields.
This agent exists to be BAD at coordination — it's the floor.
If Syncference can't outperform random, the protocol has no value.

Used in benchmarks as lower-bound baseline.
"""

from __future__ import annotations

import math
import random
import time
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)


class ReferenceRandomAgent(BaseAgent):
    """
    Random walk agent. Changes direction randomly every N cycles.
    Projects honest MVR — it's bad at coordination, not dishonest.
    """

    def __init__(
        self,
        config: AgentConfig,
        direction_change_interval: int = 10,
        seed: Optional[int] = None,
    ) -> None:
        super().__init__(config)
        self._rng = random.Random(seed)
        self._change_interval = direction_change_interval
        self._direction = self._random_direction()
        self._speed = config.max_speed * 0.4
        self._local_risks: dict[str, float] = {}
        self._boundary = (0, 0, 50, 50)

    def _random_direction(self) -> tuple[float, float]:
        angle = self._rng.uniform(0, 2 * math.pi)
        return (math.cos(angle), math.sin(angle))

    def sense(self, environment: dict) -> None:
        if "boundary" in environment:
            self._boundary = environment["boundary"]

    def infer(self) -> None:
        # Change direction periodically
        if self._cycle % self._change_interval == 0:
            self._direction = self._random_direction()

        # Bounce off boundaries
        px, py = self._state.position
        bx0, by0, bx1, by1 = self._boundary
        margin = 3.0
        dx, dy = self._direction

        if px < bx0 + margin and dx < 0:
            dx = abs(dx)
        elif px > bx1 - margin and dx > 0:
            dx = -abs(dx)
        if py < by0 + margin and dy < 0:
            dy = abs(dy)
        elif py > by1 - margin and dy > 0:
            dy = -abs(dy)

        norm = math.sqrt(dx * dx + dy * dy)
        if norm > 0.01:
            self._direction = (dx / norm, dy / norm)

        # Simple risk: low everywhere (random agent doesn't assess risk well)
        cell_id = f"{int(px)}_{int(py)}"
        self._local_risks = {cell_id: 0.1}

    def project(self) -> MVRProjection:
        px, py = self._state.position
        r = self._config.envelope_radius
        return MVRProjection(
            spatial_envelope=SpatialEnvelope(px - r, py - r, px + r, py + r),
            temporal_sync=TemporalSync(time.time(), drift_bound_ms=5.0),
            intent_vector=IntentVector(
                direction=self._direction,
                speed=self._speed,
                action_type="move",
            ),
            constraint_set=ConstraintSet(
                max_speed=self._config.max_speed,
                min_separation=self._config.min_separation,
            ),
            risk_gradient=RiskGradient(cell_risks=dict(self._local_risks)),
        )

    def act(self, shared_mvr: dict, dt: float) -> None:
        self.receive_shared_mvr(shared_mvr)

        speed = self._speed
        direction = self._direction

        # Respect shared max_speed constraint
        if shared_mvr and "constraint_set" in shared_mvr:
            max_spd = shared_mvr["constraint_set"].get("max_speed", self._config.max_speed)
            speed = min(speed, max_spd)

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
