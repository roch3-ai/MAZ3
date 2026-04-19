"""
Reference Syncference Agent — the canonical implementation.

This agent implements Syncference correctly:
- Projects honest MVR fields
- Respects shared MVR constraints
- Re-plans when intent conflicts with M*
- Moves toward a goal while respecting coordination

This is the agent that SHOULD score well on Harmony Index.
It serves as the reference for benchmarking.

Patent ref: P4 Section 3.1 (Syncference Protocol)
"""

from __future__ import annotations

import math
import time
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig, AgentState
from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)


class ReferenceSyncferenceAgent(BaseAgent):
    """
    Reference implementation of a Syncference-compliant agent.

    Behavior: navigate toward goal, respect constraints, honest projections.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Optional[tuple[float, float]] = None,
    ) -> None:
        super().__init__(config)
        self._goal = goal or (config.start_position[0] + 20.0,
                              config.start_position[1])
        self._desired_speed = config.max_speed * 0.6  # cruise at 60% max
        self._local_risks: dict[str, float] = {}
        self._environment: dict = {}
        self._boundary: tuple[float, float, float, float] = (0, 0, 50, 50)

    # =================================================================
    # Phase 1 — SENSE
    # =================================================================

    def sense(self, environment: dict) -> None:
        """Perceive local environment. Store for inference."""
        self._environment = environment
        if "boundary" in environment:
            self._boundary = environment["boundary"]

    # =================================================================
    # Phase 2 — INFER
    # =================================================================

    def infer(self) -> None:
        """
        Produce intent: move toward goal.
        Compute local risk based on proximity to obstacles/boundaries.
        """
        px, py = self._state.position
        gx, gy = self._goal

        # Direction to goal
        dx = gx - px
        dy = gy - py
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < 0.5:
            # At goal — stop
            self._desired_direction = (0.0, 0.0)
            self._desired_speed = 0.0
            return

        # Normalize direction
        self._desired_direction = (dx / dist, dy / dist)

        # Slow down near goal
        if dist < 5.0:
            self._desired_speed = self._config.max_speed * 0.3
        else:
            self._desired_speed = self._config.max_speed * 0.6

        # Compute risk: higher near boundaries
        self._local_risks = {}
        cell_x = int(px)
        cell_y = int(py)
        cell_id = f"{cell_x}_{cell_y}"

        bx0, by0, bx1, by1 = self._boundary
        dist_to_boundary = min(
            px - bx0, bx1 - px,
            py - by0, by1 - py,
        )
        boundary_risk = max(0.0, 1.0 - dist_to_boundary / 5.0)
        self._local_risks[cell_id] = min(1.0, boundary_risk * 0.5)

        # Environmental risk zones (e.g. asymmetric_risk scenario) — sensed
        # only within sensing_radius of the agent's position. Scenarios that
        # don't publish risk_zones leave this block inert.
        risk_zones = self._environment.get("risk_zones") or []
        sensing_radius = self._environment.get("sensing_radius")
        if sensing_radius is None:
            sensing_radius = float("inf")
        sr_sq = sensing_radius * sensing_radius if sensing_radius != float("inf") else None
        for zone in risk_zones:
            zc_x, zc_y = zone["center"]
            hs = zone["half_size"]
            val = zone["value"]
            for ix in range(int(zc_x - hs), int(zc_x + hs) + 1):
                for iy in range(int(zc_y - hs), int(zc_y + hs) + 1):
                    if sr_sq is not None:
                        dx = (ix + 0.5) - px
                        dy = (iy + 0.5) - py
                        if dx * dx + dy * dy > sr_sq:
                            continue
                    cid = f"{ix}_{iy}"
                    if val > self._local_risks.get(cid, 0.0):
                        self._local_risks[cid] = val

    # =================================================================
    # Phase 3 — SHARE (Projection)
    # =================================================================

    def project(self) -> MVRProjection:
        """
        Project internal state to MVR.
        Honest projection — no inflation, no under-reporting.
        """
        px, py = self._state.position
        r = self._config.envelope_radius

        direction = getattr(self, '_desired_direction', (1.0, 0.0))
        speed = getattr(self, '_desired_speed', 0.0)

        return MVRProjection(
            spatial_envelope=SpatialEnvelope(
                x_min=px - r, y_min=py - r,
                x_max=px + r, y_max=py + r,
            ),
            temporal_sync=TemporalSync(
                timestamp=time.time(),
                drift_bound_ms=2.0,
            ),
            intent_vector=IntentVector(
                direction=direction,
                speed=speed,
                action_type="move" if speed > 0.01 else "stop",
            ),
            constraint_set=ConstraintSet(
                max_speed=self._config.max_speed,
                min_separation=self._config.min_separation,
            ),
            risk_gradient=RiskGradient(
                cell_risks=dict(self._local_risks),
            ),
        )

    # =================================================================
    # Phase 5 — ACT
    # =================================================================

    def act(self, shared_mvr: dict, dt: float) -> None:
        """
        Execute action respecting shared MVR constraints.

        1. Check if intent is compatible with M*
        2. If constraint violation → reduce speed / adjust direction
        3. Update position
        """
        self.receive_shared_mvr(shared_mvr)

        direction = getattr(self, '_desired_direction', (0.0, 0.0))
        speed = getattr(self, '_desired_speed', 0.0)

        # Respect shared constraints
        if shared_mvr and "constraint_set" in shared_mvr:
            max_speed = shared_mvr["constraint_set"].get("max_speed", self._config.max_speed)
            speed = min(speed, max_speed)

        # Check shared risk — if high risk in our cell, slow down
        if shared_mvr and "risk_gradient" in shared_mvr:
            cell_risks = shared_mvr["risk_gradient"].get("cell_risks", {})
            px, py = self._state.position
            cell_id = f"{int(px)}_{int(py)}"
            cell_risk = cell_risks.get(cell_id, 0.0)
            if cell_risk > 0.7:
                speed *= 0.3  # Heavy braking in high-risk cells
            elif cell_risk > 0.4:
                speed *= 0.6  # Cautious

        # Check other agents' intents — avoid head-on
        if shared_mvr and "intent_vector" in shared_mvr:
            intents = shared_mvr["intent_vector"]
            if isinstance(intents, list) and len(intents) > 1:
                # Simple collision avoidance: if any intent is directly opposing, slow down
                for intent_data in intents:
                    other_intent = intent_data.get("intent", {})
                    other_dir = other_intent.get("direction", [0, 0])
                    if isinstance(other_dir, list) and len(other_dir) == 2:
                        # Dot product: if negative → opposing directions
                        dot = direction[0] * other_dir[0] + direction[1] * other_dir[1]
                        if dot < -0.5 and other_intent.get("speed", 0) > 0.5:
                            speed *= 0.5  # Slow down for opposing traffic

        # Update velocity
        vx = direction[0] * speed
        vy = direction[1] * speed
        self._state.velocity = (vx, vy)
        self._state.speed = speed

        # Update position
        px, py = self._state.position
        new_px = px + vx * dt
        new_py = py + vy * dt

        # Boundary clamping
        bx0, by0, bx1, by1 = self._boundary
        new_px = max(bx0 + 0.1, min(bx1 - 0.1, new_px))
        new_py = max(by0 + 0.1, min(by1 - 0.1, new_py))

        self._state.position = (new_px, new_py)

        # Update heading
        if speed > 0.01:
            self._state.heading = math.atan2(vy, vx)

        self.advance_cycle()
