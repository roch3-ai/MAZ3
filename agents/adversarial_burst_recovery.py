"""
Adversarial Burst-Recovery — Temporal burst-and-recover attacker.

Strategy: deterministic temporal alternation between BURST phase
(inflate spatial envelope) and RECOVER phase (honest projection).

This agent does NOT observe its own trust score. Sovereignty constraints
in MAZ3 prevent agents from reading internal trust metrics; instead,
this attacker uses a fixed temporal schedule. The hypothesis is that
during RECOVER, ARGUS may grant partial trust recovery, which the next
BURST exploits before being re-detected.

Pattern (after activate_after_cycle):
  cycles [activate, activate+burst_period)        → BURST
  cycles [activate+burst_period, activate+2N)     → RECOVER
  cycles [activate+2N,       activate+3N)         → BURST
  ...

This is the architectural analogue of "adaptive" without violating
sovereignty: the agent's behavior is fully determined by cycle counter,
not by trust feedback.

Patent ref: P3/P4 — temporal adversarial pattern detection.
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


class AdversarialBurstRecoveryAgent(BaseAgent):
    """
    Alternates BURST (inflate) and RECOVER (honest) phases on a fixed
    temporal schedule. No trust observation.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Optional[tuple[float, float]] = None,
        burst_period: int = 10,
        inflation_factor: float = 1.5,
        activate_after_cycle: int = 5,
    ) -> None:
        super().__init__(config)
        self._goal = goal or (config.start_position[0] + 30.0,
                              config.start_position[1])
        self._burst_period = max(1, burst_period)
        self._inflation_factor = inflation_factor
        self._activate_after = activate_after_cycle
        self._direction = (1.0, 0.0)
        self._speed = config.max_speed * 0.5
        self._boundary = (0, 0, 50, 50)
        self._local_risks: dict[str, float] = {}

    @property
    def is_attacking(self) -> bool:
        return self._cycle >= self._activate_after

    @property
    def attack_mode_this_cycle(self) -> str:
        """Returns 'burst', 'recover', or 'honest' (pre-activation)."""
        if not self.is_attacking:
            return "honest"
        # Phase alternates every burst_period cycles after activation
        cycles_since_activation = self._cycle - self._activate_after
        phase_index = cycles_since_activation // self._burst_period
        return "burst" if (phase_index % 2 == 0) else "recover"

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
        px, py = self._state.position
        r = self._config.envelope_radius
        mode = self.attack_mode_this_cycle

        if mode == "burst":
            r_eff = r * self._inflation_factor
            envelope = SpatialEnvelope(
                px - r_eff, py - r_eff, px + r_eff, py + r_eff,
            )
        else:
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
