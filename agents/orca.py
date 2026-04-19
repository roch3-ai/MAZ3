"""
ORCA Agent — Optimal Reciprocal Collision Avoidance (van den Berg et al. 2011).

Homogeneous baseline. All ORCA agents assume every other agent is also ORCA.
This is a requirement of the ORCA framework, not a limitation of MAZ3 — it is
exactly why ORCA does not satisfy sovereignty (all agents must share the same
algorithm and full state visibility).

Reference:
    van den Berg, J., Guy, S., Lin, M., & Manocha, D. (2011).
    Reciprocal n-body collision avoidance. In Robotics Research, pp. 3-19.

Adapted for MAZ3 SDK. ORCAAgent inherits from BaselineAgent (not BaseAgent)
so the engine attaches a ground-truth neighbor hook. Sovereign agents do not
receive this hook.

Implements the 5-phase BaseAgent interface so the engine can drive ORCA agents
through the same loop as Syncference agents:
    sense/infer : minimal (ORCA decides in act() using ground truth)
    project     : publishes a valid MVRProjection corresponding to the agent's
                  swept footprint, so Γ can still compose when running a pure
                  ORCA fleet. ORCA itself ignores shared_mvr in act().
    act         : runs the ORCA half-plane solver against ground-truth neighbors.

Simplifications vs. full ORCA:
    - 2D only (no 3D drones — future work)
    - Half-planes solved by iterative projection (not randomized LP). For n<50
      this converges in ≤50 iterations and is easier to audit.
    - No density fallback: if infeasible, agent stops (documented).
"""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from agents.base_agent import AgentConfig
from agents.baseline_agent import BaselineAgent
from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)


ORCA_TIME_HORIZON = 2.0    # seconds: time horizon for collision prediction
ORCA_TIME_STEP = 0.1       # seconds: integration step for VO computation
EPSILON = 1e-6             # numerical tolerance


# ---------------------------------------------------------------------------
# Vector helpers (2D)
# ---------------------------------------------------------------------------

def _vec_sub(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] - b[0], a[1] - b[1])


def _vec_add(a: Tuple[float, float], b: Tuple[float, float]) -> Tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def _vec_scale(a: Tuple[float, float], s: float) -> Tuple[float, float]:
    return (a[0] * s, a[1] * s)


def _vec_dot(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _vec_norm(a: Tuple[float, float]) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


def _vec_normalize(a: Tuple[float, float]) -> Tuple[float, float]:
    n = _vec_norm(a)
    if n < EPSILON:
        return (0.0, 0.0)
    return (a[0] / n, a[1] / n)


def _cross_2d(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return a[0] * b[1] - a[1] * b[0]


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ORCAAgent(BaselineAgent):
    """
    Homogeneous baseline agent implementing ORCA.

    Unlike Syncference agents, ORCA agents:
    - Require complete state knowledge of all neighbors (position, velocity, radius)
    - Assume all other agents also run ORCA (homogeneity requirement)
    - Do not consume the shared MVR (they ignore M* in act())

    This violates sovereignty by construction. Included as a baseline to
    enable direct comparison against the dominant collision-avoidance
    algorithm in heterogeneous multi-agent systems literature.
    """

    def __init__(
        self,
        config: AgentConfig,
        goal: Tuple[float, float],
        neighbor_dist: float = 10.0,
    ) -> None:
        super().__init__(config)
        self._goal: Tuple[float, float] = goal
        self._neighbor_dist: float = neighbor_dist
        self._boundary: Tuple[float, float, float, float] = (0.0, 0.0, 50.0, 50.0)
        self._last_pref_vel: Tuple[float, float] = (0.0, 0.0)

    # ---- Phase 1: SENSE -----------------------------------------------------

    def sense(self, environment: dict) -> None:
        if "boundary" in environment:
            self._boundary = environment["boundary"]

    # ---- Phase 2: INFER -----------------------------------------------------

    def infer(self) -> None:
        # ORCA defers the collision-avoidance decision to act() where ground
        # truth is available. infer() only caches the preferred velocity so
        # that project() can publish a consistent intent.
        self._last_pref_vel = self._preferred_velocity(self._state.position)

    # ---- Phase 3: SHARE (Projection) ----------------------------------------

    def project(self) -> MVRProjection:
        px, py = self._state.position
        r = self._config.envelope_radius
        pref_speed = _vec_norm(self._last_pref_vel)
        pref_dir = _vec_normalize(self._last_pref_vel)
        # Envelope: footprint + 1-step swept volume along preferred velocity.
        end_x = px + self._last_pref_vel[0] * ORCA_TIME_STEP
        end_y = py + self._last_pref_vel[1] * ORCA_TIME_STEP
        return MVRProjection(
            spatial_envelope=SpatialEnvelope(
                x_min=min(px, end_x) - r,
                y_min=min(py, end_y) - r,
                x_max=max(px, end_x) + r,
                y_max=max(py, end_y) + r,
            ),
            temporal_sync=TemporalSync(
                timestamp=time.time(),
                drift_bound_ms=2.0,
            ),
            intent_vector=IntentVector(
                direction=pref_dir if pref_speed > EPSILON else (1.0, 0.0),
                speed=pref_speed,
                action_type="move" if pref_speed > 0.01 else "stop",
            ),
            constraint_set=ConstraintSet(
                max_speed=self._config.max_speed,
                min_separation=self._config.min_separation,
            ),
            risk_gradient=RiskGradient(cell_risks={}),
        )

    # ---- Phase 5: ACT -------------------------------------------------------

    def act(self, shared_mvr: dict, dt: float) -> None:
        # ORCA ignores shared_mvr by design (homogeneous baseline).
        # We still store it for logging symmetry with other agents.
        self.receive_shared_mvr(shared_mvr)

        pos = self._state.position
        vel = self._state.velocity
        pref_vel = self._preferred_velocity(pos)

        neighbors = self._get_ground_truth_neighbors(radius=self._neighbor_dist)
        new_vel = self._compute_orca_velocity(pos, vel, pref_vel, neighbors)

        # Integrate one step
        new_x = pos[0] + new_vel[0] * dt
        new_y = pos[1] + new_vel[1] * dt

        # Boundary clamp (matches reference agents)
        bx0, by0, bx1, by1 = self._boundary
        new_x = max(bx0 + 0.1, min(bx1 - 0.1, new_x))
        new_y = max(by0 + 0.1, min(by1 - 0.1, new_y))

        self._state.position = (new_x, new_y)
        self._state.velocity = new_vel
        speed = _vec_norm(new_vel)
        self._state.speed = speed
        if speed > EPSILON:
            self._state.heading = math.atan2(new_vel[1], new_vel[0])

        self.advance_cycle()

    # ------------------------------------------------------------------------
    # ORCA core math
    # ------------------------------------------------------------------------

    def _preferred_velocity(self, pos: Tuple[float, float]) -> Tuple[float, float]:
        """Unit vector toward goal × max_speed (less if close to goal)."""
        to_goal = _vec_sub(self._goal, pos)
        dist = _vec_norm(to_goal)
        if dist < EPSILON:
            return (0.0, 0.0)
        speed = min(self._config.max_speed, dist / ORCA_TIME_STEP)
        return _vec_scale(_vec_normalize(to_goal), speed)

    def _compute_orca_velocity(
        self,
        pos: Tuple[float, float],
        vel: Tuple[float, float],
        pref_vel: Tuple[float, float],
        neighbors: List[Tuple[str, Tuple[float, float], Tuple[float, float], float]],
    ) -> Tuple[float, float]:
        half_planes: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
        my_radius = self._config.envelope_radius

        for _nid, npos, nvel, nradius in neighbors:
            hp = self._orca_half_plane(pos, vel, my_radius, npos, nvel, nradius)
            if hp is not None:
                half_planes.append(hp)

        return self._project_onto_half_planes(
            pref_vel, half_planes, self._config.max_speed,
        )

    def _orca_half_plane(
        self,
        pos_a: Tuple[float, float],
        vel_a: Tuple[float, float],
        rad_a: float,
        pos_b: Tuple[float, float],
        vel_b: Tuple[float, float],
        rad_b: float,
    ) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        rel_pos = _vec_sub(pos_b, pos_a)
        rel_vel = _vec_sub(vel_a, vel_b)
        dist_sq = _vec_dot(rel_pos, rel_pos)
        combined_radius = rad_a + rad_b
        combined_radius_sq = combined_radius * combined_radius

        if dist_sq < combined_radius_sq:
            # Already in collision; skip to avoid infeasibility. MAZ3's
            # KineticSafety layer handles the actual physical response.
            return None

        inv_tau = 1.0 / ORCA_TIME_HORIZON
        w = _vec_sub(rel_vel, _vec_scale(rel_pos, inv_tau))
        w_len_sq = _vec_dot(w, w)
        w_len = math.sqrt(w_len_sq)
        dot_product = _vec_dot(w, rel_pos)

        if dot_product < 0.0 and dot_product * dot_product > combined_radius_sq * w_len_sq:
            # Project onto circular part of VO boundary
            unit_w = _vec_normalize(w)
            normal = unit_w
            u_magnitude = (combined_radius * inv_tau) - w_len
            u = _vec_scale(unit_w, u_magnitude)
        else:
            leg = math.sqrt(max(dist_sq - combined_radius_sq, 0.0))
            if _cross_2d(rel_pos, w) > 0.0:
                direction = (
                    rel_pos[0] * leg - rel_pos[1] * combined_radius,
                    rel_pos[0] * combined_radius + rel_pos[1] * leg,
                )
            else:
                direction = (
                    rel_pos[0] * leg + rel_pos[1] * combined_radius,
                    -rel_pos[0] * combined_radius + rel_pos[1] * leg,
                )
            direction = _vec_normalize(direction)
            dot_leg = _vec_dot(rel_vel, direction)
            projected = _vec_scale(direction, dot_leg)
            u = _vec_sub(projected, rel_vel)
            normal = _vec_normalize(u)

        # Reciprocal responsibility sharing: each agent absorbs half of u.
        hp_point = _vec_add(vel_a, _vec_scale(u, 0.5))
        return (hp_point, normal)

    def _project_onto_half_planes(
        self,
        target: Tuple[float, float],
        half_planes: List[Tuple[Tuple[float, float], Tuple[float, float]]],
        max_speed: float,
    ) -> Tuple[float, float]:
        v = target
        # Clamp to max_speed disk first
        v_norm = _vec_norm(v)
        if v_norm > max_speed:
            v = _vec_scale(_vec_normalize(v), max_speed)

        # Iterative projection — not optimal LP, but audit-friendly and
        # convergent for small n.
        for _ in range(50):
            changed = False
            for (hp_point, hp_normal) in half_planes:
                signed_dist = _vec_dot(_vec_sub(v, hp_point), hp_normal)
                if signed_dist < -EPSILON:
                    v = _vec_add(v, _vec_scale(hp_normal, -signed_dist))
                    v_norm = _vec_norm(v)
                    if v_norm > max_speed:
                        v = _vec_scale(_vec_normalize(v), max_speed)
                    changed = True
            if not changed:
                break

        # Final feasibility check
        for (hp_point, hp_normal) in half_planes:
            signed_dist = _vec_dot(_vec_sub(v, hp_point), hp_normal)
            if signed_dist < -0.01:
                return (0.0, 0.0)
        return v
