"""
MVR — Minimum Viable Reality

Each agent projects exactly 5 fields. Nothing more, nothing less.
These fields are the ONLY information shared during Syncference.
The agent's internal state (strategy, learning, preferences) stays sovereign.

Patent ref: P4 Claims 1-5 (MVR Composition)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SpatialEnvelope:
    """
    Volume claimed by the agent, bounded by B_i(t).
    In 2D MAZ3: a bounding box or polygon on the grid.
    """
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def area(self) -> float:
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)

    def overlaps(self, other: SpatialEnvelope) -> bool:
        return not (
            self.x_max <= other.x_min or other.x_max <= self.x_min or
            self.y_max <= other.y_min or other.y_max <= self.y_min
        )

    def to_dict(self) -> dict:
        return {"x_min": self.x_min, "y_min": self.y_min,
                "x_max": self.x_max, "y_max": self.y_max}

    @classmethod
    def from_dict(cls, d: dict) -> SpatialEnvelope:
        return cls(d["x_min"], d["y_min"], d["x_max"], d["y_max"])


@dataclass
class TemporalSync:
    """
    Agent clock + drift bound.
    drift < ε_t is required for valid participation in Syncference.
    """
    timestamp: float  # Agent's local clock (epoch seconds)
    drift_bound_ms: float  # Maximum known drift from reference

    def to_dict(self) -> dict:
        return {"timestamp": self.timestamp, "drift_bound_ms": self.drift_bound_ms}

    @classmethod
    def from_dict(cls, d: dict) -> TemporalSync:
        return cls(d["timestamp"], d["drift_bound_ms"])


@dataclass
class IntentVector:
    """
    Planned action for the next cycle.
    Preserved individually in Γ — never merged.
    """
    direction: tuple[float, float]  # (dx, dy) unit vector
    speed: float  # m/s planned
    action_type: str = "move"  # move | stop | yield | emergency_stop

    def to_dict(self) -> dict:
        return {"direction": list(self.direction), "speed": self.speed,
                "action_type": self.action_type}

    @classmethod
    def from_dict(cls, d: dict) -> IntentVector:
        return cls(tuple(d["direction"]), d["speed"], d["action_type"])


@dataclass
class ConstraintSet:
    """
    Physical and regulatory limits.
    In Γ: intersection (strictest wins).
    """
    max_speed: float  # m/s — physical limit
    min_separation: float  # meters — minimum distance to any other agent
    regulatory_zones: list[dict] = field(default_factory=list)  # no-go zones

    def to_dict(self) -> dict:
        import copy
        return {"max_speed": self.max_speed, "min_separation": self.min_separation,
                "regulatory_zones": copy.deepcopy(self.regulatory_zones)}

    @classmethod
    def from_dict(cls, d: dict) -> ConstraintSet:
        return cls(d["max_speed"], d["min_separation"],
                   d.get("regulatory_zones", []))


@dataclass
class RiskGradient:
    """
    Per-cell risk assessment. In Γ: max (pessimistic).
    Keys are grid cell IDs, values are risk scores [0, 1].
    """
    cell_risks: dict[str, float] = field(default_factory=dict)

    def max_risk(self) -> float:
        return max(self.cell_risks.values()) if self.cell_risks else 0.0

    def to_dict(self) -> dict:
        # Shallow copy is sufficient for {str: float} — no nested mutables
        return {"cell_risks": dict(self.cell_risks)}

    @classmethod
    def from_dict(cls, d: dict) -> RiskGradient:
        return cls(d.get("cell_risks", {}))


@dataclass
class MVRProjection:
    """
    The complete MVR projection from one agent.
    This is the ONLY thing shared during Syncference.

    5 fields, exactly. The minimal representation needed for
    safe coordination without exposing internal state.
    """
    spatial_envelope: SpatialEnvelope
    temporal_sync: TemporalSync
    intent_vector: IntentVector
    constraint_set: ConstraintSet
    risk_gradient: RiskGradient

    # Metadata — NOT shared with other agents, used internally
    projection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        """Serialize to dict. Metadata excluded — this is what gets shared."""
        return {
            "spatial_envelope": self.spatial_envelope.to_dict(),
            "temporal_sync": self.temporal_sync.to_dict(),
            "intent_vector": self.intent_vector.to_dict(),
            "constraint_set": self.constraint_set.to_dict(),
            "risk_gradient": self.risk_gradient.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> MVRProjection:
        return cls(
            spatial_envelope=SpatialEnvelope.from_dict(d["spatial_envelope"]),
            temporal_sync=TemporalSync.from_dict(d["temporal_sync"]),
            intent_vector=IntentVector.from_dict(d["intent_vector"]),
            constraint_set=ConstraintSet.from_dict(d["constraint_set"]),
            risk_gradient=RiskGradient.from_dict(d["risk_gradient"]),
        )

    def to_json(self) -> str:
        """
        JSON-serializable representation. For wire transport (ROS 2, MQTT, gRPC).

        The MAZ3 SDK is designed to be wrappable by ROS 2 and other robotics
        middleware. This method produces a JSON string with only primitive types
        (no numpy arrays, no datetime objects, no custom classes).
        """
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> MVRProjection:
        """Reconstruct from JSON wire format."""
        import json
        return cls.from_dict(json.loads(json_str))

    def validate(self) -> list[str]:
        """Basic validity checks. Returns list of errors (empty = valid)."""
        import math
        errors = []
        env = self.spatial_envelope

        # Reject non-finite values in spatial envelope
        for field_name, value in [
            ("x_min", env.x_min), ("x_max", env.x_max),
            ("y_min", env.y_min), ("y_max", env.y_max),
        ]:
            if not math.isfinite(value):
                errors.append(f"spatial_envelope.{field_name} is {value} (must be finite)")

        if env.x_min >= env.x_max or env.y_min >= env.y_max:
            errors.append("spatial_envelope: degenerate (min >= max)")
        if env.area() > 10000:  # sanity: >100m × 100m is suspect
            errors.append("spatial_envelope: suspiciously large area")
        if self.temporal_sync.drift_bound_ms < 0:
            errors.append("temporal_sync: negative drift bound")
        if self.intent_vector.speed < 0:
            errors.append("intent_vector: negative speed")
        if self.constraint_set.max_speed <= 0:
            errors.append("constraint_set: non-positive max_speed")
        if self.constraint_set.min_separation < 0:
            errors.append("constraint_set: negative min_separation")

        # DOS defense: limit regulatory zones

        MAX_REGULATORY_ZONES = 1_000
        if len(self.constraint_set.regulatory_zones) > MAX_REGULATORY_ZONES:
            errors.append(
                f"constraint_set: {len(self.constraint_set.regulatory_zones)} "
                f"regulatory_zones exceeds maximum {MAX_REGULATORY_ZONES}"
            )

        # Cap drift bound to prevent temporal divergence manipulation
        # An agent declaring drift_bound_ms=1e15 collapses D_temporal to 0
        MAX_DRIFT_BOUND_MS = 10_000  # 10 seconds is generous
        if self.temporal_sync.drift_bound_ms > MAX_DRIFT_BOUND_MS:
            errors.append(
                f"temporal_sync: drift_bound_ms {self.temporal_sync.drift_bound_ms} "
                f"exceeds maximum {MAX_DRIFT_BOUND_MS}"
            )

        # DOS defense: limit risk gradient cells
        MAX_RISK_CELLS = 10_000
        if len(self.risk_gradient.cell_risks) > MAX_RISK_CELLS:
            errors.append(
                f"risk_gradient: {len(self.risk_gradient.cell_risks)} cells "
                f"exceeds maximum {MAX_RISK_CELLS}"
            )

        for cell_id, risk in self.risk_gradient.cell_risks.items():
            # Reject non-finite or out-of-range risk values

            if not math.isfinite(risk) or not (0.0 <= risk <= 1.0):
                errors.append(f"risk_gradient: cell {cell_id} risk {risk} invalid (must be finite and in [0,1])")
                break  # don't spam
        return errors
