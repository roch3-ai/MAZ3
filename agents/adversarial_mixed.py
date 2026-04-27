"""
Adversarial Mixed — Alternates inflation and risk under-reporting.

Strategy: deterministic 50/50 alternation per cycle. Even cycles inflate
the spatial envelope (like AdversarialInflatorAgent); odd cycles
under-report the risk gradient (like AdversarialUnderreporterAgent).

The agent never combines both attacks in the same cycle — that would
make detection trivial. By alternating, it tries to dilute each detector's
signal across time. Each individual cycle looks like one of two known
attack types; the temporal pattern is the novel adversarial signature.

Patent ref: P3 Claims (multi-vector adversarial detection),
            P4 Claim 54 (strategy-proof property).
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


class AdversarialMixedAgent(BaseAgent):
    """
    Alternates between inflation and under-reporting per cycle.

    On EVEN cycles (after activation): inflate spatial_envelope.
    On ODD cycles  (after activation): under-report risk_gradient.
    Before activation: behaves honestly (builds trust history).
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
        self._speed = config.max_speed * 0.6
        self._boundary = (0, 0, 50, 50)
        self._true_risks: dict[str, float] = {}

    @property
    def is_attacking(self) -> bool:
        return self._cycle >= self._activate_after

    @property
    def attack_mode_this_cycle(self) -> str:
        if not self.is_attacking:
            return "honest"
        return "inflate" if (self._cycle % 2 == 0) else "underreport"

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
        self._speed = self._config.max_speed * 0.6

        cell_id = f"{int(px)}_{int(py)}"
        bx0, by0, bx1, by1 = self._boundary
        dist_to_boundary = min(px - bx0, bx1 - px, py - by0, by1 - py)
        true_risk = max(0.0, 1.0 - dist_to_boundary / 5.0) * 0.4
        self._true_risks = {cell_id: true_risk}

    def project(self) -> MVRProjection:
        px, py = self._state.position
        r = self._config.envelope_radius
        mode = self.attack_mode_this_cycle

        if mode == "inflate":
            r_eff = r * self._inflation_factor
            envelope = SpatialEnvelope(
                px - r_eff, py - r_eff, px + r_eff, py + r_eff,
            )
            declared_risks = dict(self._true_risks)
        elif mode == "underreport":
            envelope = SpatialEnvelope(px - r, py - r, px + r, py + r)
            cell_id = f"{int(px)}_{int(py)}"
            declared_risks = {cell_id: 0.01}
        else:
            envelope = SpatialEnvelope(px - r, py - r, px + r, py + r)
            declared_risks = dict(self._true_risks)

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
            risk_gradient=RiskGradient(cell_risks=declared_risks),
        )

    def act(self, shared_mvr: dict, dt: float) -> None:
        self.receive_shared_mvr(shared_mvr)
        speed = self._speed
        direction = self._direction

        if shared_mvr and "constraint_set" in shared_mvr:
            max_spd = shared_mvr["constraint_set"].get(
                "max_speed", self._config.max_speed
            )
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
