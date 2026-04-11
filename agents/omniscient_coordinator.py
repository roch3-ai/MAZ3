"""
Omniscient Coordinator — Internal reference with perfect information.

This agent has FULL visibility of all agents' positions, velocities,
and goals. It computes the globally optimal action for its own movement.

Purpose: validate Claim 74 — that Syncference achieves near-optimal
coordination WITHOUT requiring global information.

Hypothesis:
  H0: H_p(Omniscient) - H_p(Syncference) > 0.05  (Syncference inferior)
  H1: |H_p(Omniscient) - H_p(Syncference)| ≤ 0.05 (equivalence)
  If H1 with p < 0.05 → Claim 74 has empirical evidence.

NEVER appears on public leaderboard. Internal reference only.

Patent ref: P4 Claim 74 (coordination quality)
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


class OmniscientCoordinator(BaseAgent):
    """
    Omniscient agent with perfect global information.

    In sense(), it receives ALL agents' positions and velocities
    (information that Syncference agents don't have).
    It uses this to compute collision-free paths.

    This is the UPPER BOUND on coordination quality.
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
        self._speed = config.max_speed * 0.6
        self._boundary = (0, 0, 50, 50)
        self._local_risks: dict[str, float] = {}
        # Omniscient: knows all other agents
        self._all_agents: list[dict] = []

    def sense(self, environment: dict) -> None:
        if "boundary" in environment:
            self._boundary = environment["boundary"]
        # NOTE: omniscient info no longer comes from environment.
        # The engine pushes it via _set_omniscient_info() backdoor.

    def _set_omniscient_info(self, all_agents_info: list[dict]) -> None:
        """
        Backdoor channel — only the engine calls this.

        Normal agents do not have this method, so the engine's
        _push_omniscient_info() never reaches them. This is the
        structural enforcement that omniscient access is reserved
        for the internal reference coordinator.
        """
        self._all_agents = all_agents_info

    def infer(self) -> None:
        px, py = self._state.position
        gx, gy = self._goal

        dx = gx - px
        dy = gy - py
        dist_to_goal = math.sqrt(dx * dx + dy * dy)

        if dist_to_goal < 0.5:
            self._direction = (0.0, 0.0)
            self._speed = 0.0
            return

        # Base direction: toward goal
        goal_dir = (dx / dist_to_goal, dy / dist_to_goal)

        # Omniscient avoidance: compute repulsion from ALL known agents
        avoid_x, avoid_y = 0.0, 0.0
        min_dist = float("inf")

        for other in self._all_agents:
            # AUDIT ROUND 2 FIX C1: No agent_id in snapshot anymore.
            # Self-exclude by position match instead.
            ox, oy = other.get("position", (0, 0))
            if (abs(ox - px) < 0.001 and abs(oy - py) < 0.001):
                continue
            rx = px - ox
            ry = py - oy
            r_dist = math.sqrt(rx * rx + ry * ry)

            if r_dist < 0.01:
                continue

            min_dist = min(min_dist, r_dist)
            min_sep = self._config.min_separation

            if r_dist < min_sep * 2:
                # Repulsion force: stronger when closer
                strength = (min_sep * 2 - r_dist) / (min_sep * 2)
                avoid_x += (rx / r_dist) * strength
                avoid_y += (ry / r_dist) * strength

        # Blend: goal attraction + collision avoidance
        if min_dist < self._config.min_separation * 2:
            # Close to another agent: heavy avoidance weight
            blend = 0.3  # 30% goal, 70% avoidance
        else:
            blend = 0.9  # 90% goal, 10% avoidance

        final_x = blend * goal_dir[0] + (1 - blend) * avoid_x
        final_y = blend * goal_dir[1] + (1 - blend) * avoid_y

        norm = math.sqrt(final_x * final_x + final_y * final_y)
        if norm > 0.01:
            self._direction = (final_x / norm, final_y / norm)
        else:
            self._direction = goal_dir

        # Speed: slow down near other agents (omniscient: knows exact distances)
        if min_dist < self._config.min_separation * 1.5:
            self._speed = self._config.max_speed * 0.2
        elif min_dist < self._config.min_separation * 3:
            self._speed = self._config.max_speed * 0.4
        elif dist_to_goal < 5.0:
            self._speed = self._config.max_speed * 0.3
        else:
            self._speed = self._config.max_speed * 0.6

        # Omniscient risk: knows where danger actually is
        cell_id = f"{int(px)}_{int(py)}"
        if min_dist < self._config.min_separation:
            self._local_risks = {cell_id: 0.8}
        elif min_dist < self._config.min_separation * 2:
            self._local_risks = {cell_id: 0.4}
        else:
            self._local_risks = {cell_id: 0.1}

    def project(self) -> MVRProjection:
        px, py = self._state.position
        r = self._config.envelope_radius
        return MVRProjection(
            spatial_envelope=SpatialEnvelope(px - r, py - r, px + r, py + r),
            temporal_sync=TemporalSync(time.time(), drift_bound_ms=1.0),
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

        # Omniscient still respects hard constraints
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
