"""
Kinetic Safety — ΔK calculation and D0-D4 graduated response.

Core principle: ΔK > θ → quietud (when in doubt, stillness).

Deference Levels:
  D0: Passive monitoring — normal operations
  D1: Advisory to operator — <100ms latency
  D2: Speed correction — <50ms latency
  D3: Commanded stop — <20ms latency
  D4: Emergency veto — <10ms latency

ΔK is the kinetic risk delta — the rate of change of kinetic risk
in the local neighborhood of an agent. When ΔK exceeds θ_K,
the system escalates through deference levels.

θ_K is multi-factor adaptive (confirmed across 6 sciences):
  statistical baseline, density/Thermodynamics, entropy/Military,
  certitude/Biology, geometric/Hydrodynamics, gain-scheduled/Control Theory.

Patent ref: P3 Claims 1-55 (Kinetic Deference system)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional


class DeferenceLevel(IntEnum):
    D0 = 0  # Passive monitoring
    D1 = 1  # Advisory
    D2 = 2  # Speed correction
    D3 = 3  # Commanded stop
    D4 = 4  # Emergency veto


# Maximum allowed latency per level (milliseconds)
LATENCY_REQUIREMENTS = {
    DeferenceLevel.D0: float("inf"),  # No latency requirement
    DeferenceLevel.D1: 100.0,
    DeferenceLevel.D2: 50.0,
    DeferenceLevel.D3: 20.0,
    DeferenceLevel.D4: 10.0,
}

# θ_K thresholds for escalation (ΔK values)
# These are initial defaults — θ_K is adaptive in production
DEFAULT_THETA_K = {
    DeferenceLevel.D1: 0.3,  # ΔK > 0.3 → advisory
    DeferenceLevel.D2: 0.5,  # ΔK > 0.5 → speed correction
    DeferenceLevel.D3: 0.7,  # ΔK > 0.7 → commanded stop
    DeferenceLevel.D4: 0.9,  # ΔK > 0.9 → emergency veto
}


@dataclass
class KineticState:
    """Kinetic state of an agent at a point in time."""
    position: tuple[float, float]
    velocity: tuple[float, float]  # (vx, vy) m/s
    mass_estimate: float = 1.0  # normalized
    timestamp: float = 0.0

    @property
    def speed(self) -> float:
        return (self.velocity[0] ** 2 + self.velocity[1] ** 2) ** 0.5

    @property
    def kinetic_energy(self) -> float:
        """Normalized kinetic energy: 0.5 * m * v²"""
        return 0.5 * self.mass_estimate * self.speed ** 2


@dataclass
class DeferenceAction:
    """Action taken at a deference level."""
    level: DeferenceLevel
    delta_k: float
    theta_k: float  # threshold that was exceeded
    latency_ms: float  # actual response latency
    latency_met: bool  # did we meet the requirement?
    timestamp: float
    details: dict = field(default_factory=dict)


class KineticSafety:
    """
    Computes ΔK and determines appropriate deference level.

    ΔK measures the rate of change of kinetic risk in the local
    neighborhood. It considers:
    - Closing speed between agents
    - Spatial proximity
    - Risk gradient changes
    - Constraint violations

    When ΔK > θ_K → escalate to the appropriate deference level.
    """

    def __init__(
        self,
        theta_k: Optional[dict[DeferenceLevel, float]] = None,
        min_separation: float = 2.0,  # meters
    ) -> None:
        self._theta_k = theta_k or dict(DEFAULT_THETA_K)
        self._min_separation = min_separation
        # History for computing ΔK (rate of change needs previous state)
        self._previous_states: dict[int, KineticState] = {}  # index → state
        self._action_log: list[DeferenceAction] = []

    def compute_delta_k(
        self,
        agent_index: int,
        current: KineticState,
        neighbors: list[KineticState],
    ) -> float:
        """
        Compute ΔK for an agent given its neighbors.

        Components:
        1. Closing speed factor: how fast agents approach each other
        2. Proximity factor: inverse of distance (closer = higher risk)
        3. Acceleration factor: rate of change from previous state

        Returns ΔK ∈ [0, 1] normalized.
        """
        if not neighbors:
            return 0.0

        max_risk = 0.0

        for neighbor in neighbors:
            # Distance between agents
            dx = current.position[0] - neighbor.position[0]
            dy = current.position[1] - neighbor.position[1]
            distance = max(0.01, (dx ** 2 + dy ** 2) ** 0.5)  # floor to avoid /0

            # Closing speed: dot product of relative velocity with relative position
            rel_vx = current.velocity[0] - neighbor.velocity[0]
            rel_vy = current.velocity[1] - neighbor.velocity[1]
            # Positive = closing, negative = separating
            closing_speed = -(rel_vx * dx + rel_vy * dy) / distance

            # Proximity factor: exponential increase as distance shrinks
            proximity = max(0.0, 1.0 - distance / (self._min_separation * 3))

            # Combined kinetic risk for this pair
            # closing_speed normalized by sum of max speeds (approximated)
            max_speed = max(current.speed, neighbor.speed, 0.01)
            closing_factor = max(0.0, closing_speed / (2 * max_speed))

            pair_risk = (0.6 * closing_factor + 0.4 * proximity)
            max_risk = max(max_risk, pair_risk)

        # Acceleration factor: change from previous state
        accel_factor = 0.0
        if agent_index in self._previous_states:
            prev = self._previous_states[agent_index]
            dt = max(0.001, current.timestamp - prev.timestamp)
            dvx = current.velocity[0] - prev.velocity[0]
            dvy = current.velocity[1] - prev.velocity[1]
            accel = (dvx ** 2 + dvy ** 2) ** 0.5 / dt
            # Normalize: >5 m/s² is considered aggressive
            accel_factor = min(1.0, accel / 5.0)

        # Store for next cycle
        self._previous_states[agent_index] = current

        # ΔK: weighted combination
        delta_k = min(1.0, 0.7 * max_risk + 0.3 * accel_factor)
        return delta_k

    def determine_level(self, delta_k: float) -> DeferenceLevel:
        """
        Determine deference level from ΔK.
        Escalates through D0→D4 based on θ_K thresholds.
        """
        level = DeferenceLevel.D0

        for d_level in [DeferenceLevel.D4, DeferenceLevel.D3,
                        DeferenceLevel.D2, DeferenceLevel.D1]:
            if delta_k >= self._theta_k[d_level]:
                level = d_level
                break

        return level

    def evaluate(
        self,
        agent_index: int,
        current: KineticState,
        neighbors: list[KineticState],
    ) -> DeferenceAction:
        """
        Full evaluation: compute ΔK, determine level, log action.
        """
        start = time.perf_counter()

        delta_k = self.compute_delta_k(agent_index, current, neighbors)
        level = self.determine_level(delta_k)

        elapsed_ms = (time.perf_counter() - start) * 1000
        latency_req = LATENCY_REQUIREMENTS[level]
        latency_met = elapsed_ms <= latency_req

        action = DeferenceAction(
            level=level,
            delta_k=delta_k,
            theta_k=self._theta_k.get(level, 0.0),
            latency_ms=elapsed_ms,
            latency_met=latency_met,
            timestamp=current.timestamp,
            details={
                "agent_index": agent_index,
                "speed": current.speed,
                "neighbor_count": len(neighbors),
            },
        )

        self._action_log.append(action)
        return action

    def update_theta_k(self, level: DeferenceLevel, new_value: float) -> None:
        """
        Update θ_K threshold (antifragility loop adaptation).
        """
        if not (0.0 < new_value < 1.0):
            raise ValueError(f"θ_K must be in (0, 1), got {new_value}")
        self._theta_k[level] = new_value

    def get_theta_k(self) -> dict[DeferenceLevel, float]:
        return dict(self._theta_k)

    def get_action_log(self, last_n: int = 50) -> list[DeferenceAction]:
        return list(self._action_log[-last_n:])

    def clear_history(self) -> None:
        self._previous_states.clear()
        self._action_log.clear()
