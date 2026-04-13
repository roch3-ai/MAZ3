"""
Adversarial Detection — Behavioral anomaly detection for ARGUS.

Detects:
  1. Spatial Inflation: envelope area >> expected from agent speed/size
  2. Risk Under-reporting: declared risk much lower than what kinematics suggest
  3. Projection Poisoning: sudden large changes in projection without matching movement
  4. Envelope-Speed Inconsistency: large envelope but slow movement (or vice versa)

Each detector produces observations for ARGUS trust updates.
Detection happens BETWEEN Phase 3 (SHARE) and Phase 4 (CONVERGE).

Patent ref: P3 Claims (cooperative attack detection, projection poisoning detection)
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DetectionResult:
    """Result of running adversarial detection on one agent's projection."""
    agent_index: int
    observations: list[dict]  # ARGUS observations to apply
    detection_latency_ms: float
    attacks_detected: list[str]  # attack type names


class AdversarialDetector:
    """
    Detects adversarial behavior by comparing projections against
    physical plausibility and historical consistency.

    Stateful: maintains per-agent history for trend analysis.
    """

    def __init__(
        self,
        max_envelope_area: float = 50.0,  # m² — suspiciously large for a single agent
        max_envelope_speed_ratio: float = 5.0,  # envelope_radius / speed threshold
        risk_correlation_window: int = 10,
        inflation_threshold: float = 2.5,  # ratio of declared vs expected envelope
    ) -> None:
        self._max_envelope_area = max_envelope_area
        self._max_env_speed_ratio = max_envelope_speed_ratio
        self._risk_window = risk_correlation_window
        self._inflation_threshold = inflation_threshold

        # Per-agent history: {index: [previous_projections]}
        self._projection_history: dict[int, list[dict]] = {}

    def analyze(
        self,
        index: int,
        projection: dict,
        agent_velocity: tuple[float, float],
    ) -> DetectionResult:
        """
        Analyze a single agent's projection for adversarial patterns.
        Called for each agent after Phase 3 (SHARE).
        """
        start = time.perf_counter()
        observations = []
        attacks = []

        # Store history
        if index not in self._projection_history:
            self._projection_history[index] = []
        self._projection_history[index].append(projection)

        # Keep history bounded
        if len(self._projection_history[index]) > 50:
            self._projection_history[index] = self._projection_history[index][-50:]

        # Run detectors
        obs = self._detect_spatial_inflation(index, projection, agent_velocity)
        if obs:
            observations.append(obs)
            attacks.append("spatial_inflation")

        obs = self._detect_envelope_speed_inconsistency(index, projection, agent_velocity)
        if obs:
            observations.append(obs)
            attacks.append("envelope_speed_inconsistency")

        obs = self._detect_projection_poisoning(index, projection)
        if obs:
            observations.append(obs)
            attacks.append("projection_poisoning")

        obs = self._detect_risk_underreporting(index, projection, agent_velocity)
        if obs:
            observations.append(obs)
            attacks.append("under_reporting_risk")

        # If nothing detected, mark as consistent
        if not observations:
            observations.append({"type": "consistent"})

        elapsed_ms = (time.perf_counter() - start) * 1000

        return DetectionResult(
            agent_index=index,
            observations=observations,
            detection_latency_ms=elapsed_ms,
            attacks_detected=attacks,
        )

    def _detect_spatial_inflation(
        self,
        index: int,
        projection: dict,
        velocity: tuple[float, float],
    ) -> Optional[dict]:
        """
        Detect: declared envelope much larger than expected.

        Expected envelope ≈ agent_radius + speed * dt (kinematic buffer).
        If declared >> expected, likely inflation.
        """
        env = projection["spatial_envelope"]
        width = env["x_max"] - env["x_min"]
        height = env["y_max"] - env["y_min"]
        declared_area = width * height

        # Suspiciously large absolute area
        if declared_area > self._max_envelope_area:
            return {
                "type": "spatial_inflation",
                "severity": min(5.0, declared_area / self._max_envelope_area),
                "declared_area": declared_area,
                "threshold": self._max_envelope_area,
            }

        # Compare to historical: sudden jump in area
        history = self._projection_history.get(index, [])
        if len(history) >= 3:
            prev_areas = []
            for h in history[-4:-1]:  # last 3 before current
                e = h["spatial_envelope"]
                prev_areas.append(
                    (e["x_max"] - e["x_min"]) * (e["y_max"] - e["y_min"])
                )
            avg_prev = sum(prev_areas) / len(prev_areas)
            if avg_prev > 0 and declared_area / avg_prev > self._inflation_threshold:
                return {
                    "type": "spatial_inflation",
                    "severity": min(5.0, declared_area / avg_prev),
                    "declared_area": declared_area,
                    "historical_avg": avg_prev,
                    "ratio": declared_area / avg_prev,
                }

        return None

    def _detect_envelope_speed_inconsistency(
        self,
        index: int,
        projection: dict,
        velocity: tuple[float, float],
    ) -> Optional[dict]:
        """
        Detect: large envelope but barely moving (or vice versa).
        A stationary agent claiming 10m radius is suspicious.
        """
        env = projection["spatial_envelope"]
        radius = max(
            (env["x_max"] - env["x_min"]) / 2,
            (env["y_max"] - env["y_min"]) / 2,
        )
        speed = math.sqrt(velocity[0] ** 2 + velocity[1] ** 2)

        # Large envelope + low speed = suspicious
        if speed < 0.1 and radius > 3.0:
            return {
                "type": "spatial_inflation",
                "severity": min(3.0, radius / 3.0),
                "reason": "large_envelope_while_stationary",
                "radius": radius,
                "speed": speed,
            }

        # High speed + tiny envelope = under-reporting space needed
        if speed > 2.0 and radius < 0.5:
            return {
                "type": "under_reporting_risk",
                "severity": 1.5,
                "reason": "fast_with_tiny_envelope",
                "radius": radius,
                "speed": speed,
            }

        return None

    def _detect_projection_poisoning(
        self,
        index: int,
        projection: dict,
    ) -> Optional[dict]:
        """
        Detect: sudden large change in projection without physical justification.
        Position doesn't teleport — if envelope center jumps > 5m between cycles,
        the projection is suspicious.
        """
        history = self._projection_history.get(index, [])
        if len(history) < 2:
            return None

        current = projection["spatial_envelope"]
        prev = history[-2]["spatial_envelope"]

        cx = (current["x_min"] + current["x_max"]) / 2
        cy = (current["y_min"] + current["y_max"]) / 2
        px = (prev["x_min"] + prev["x_max"]) / 2
        py = (prev["y_min"] + prev["y_max"]) / 2

        jump = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)

        # 5m jump in one cycle (0.1s) implies 50 m/s — physically impossible
        # for ground robots / warehouse drones
        if jump > 5.0:
            return {
                "type": "projection_poisoning",
                "severity": min(5.0, jump / 5.0),
                "position_jump_m": jump,
            }

        return None

    def _detect_risk_underreporting(
        self,
        index: int,
        projection: dict,
        velocity: tuple[float, float],
    ) -> Optional[dict]:
        """
        Detect: declared risk much lower than kinematics suggest.

        If agent is moving fast near other known positions,
        but reports near-zero risk, it's likely under-reporting.
        """
        speed = math.sqrt(velocity[0] ** 2 + velocity[1] ** 2)
        risks = projection["risk_gradient"].get("cell_risks", {})

        if not risks:
            return None

        max_declared_risk = max(risks.values()) if risks else 0.0

        # Fast agent declaring very low risk
        if speed > 2.0 and max_declared_risk < 0.05:
            return {
                "type": "under_reporting_risk",
                "severity": min(3.0, speed / 2.0),
                "declared_max_risk": max_declared_risk,
                "speed": speed,
            }

        return None

    def clear(self) -> None:
        self._projection_history.clear()
