"""
Base Agent — Interface for all MAZ3 agents.

Every agent (reference, baseline, adversarial, external) must implement this.
The interface mirrors the 5-phase Syncference loop:

  1. SENSE   → sense()       — perceive local environment
  2. INFER   → infer()       — produce local world model + intent
  3. SHARE   → project()     — extract MVR projection from internal state
  4. CONVERGE → (handled by engine, not agent)
  5. ACT     → act()         — execute action given converged MVR

The agent's internal state is SOVEREIGN — the engine never reads it directly.
The ONLY interface between agent and engine is the MVR projection.

Patent ref: P4 Section 3.1 (Syncference Protocol)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from roch3.mvr import MVRProjection


@dataclass
class AgentConfig:
    """Configuration for instantiating an agent."""
    agent_id: str = field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:8]}")
    start_position: tuple[float, float] = (0.0, 0.0)
    max_speed: float = 3.0  # m/s
    min_separation: float = 2.0  # meters
    envelope_radius: float = 1.5  # meters — half-width of spatial envelope


@dataclass
class AgentState:
    """
    Observable state of an agent — used by the engine for physics simulation.
    This is NOT the agent's internal state (which is sovereign).
    This is what the WORLD sees (position, velocity).
    """
    position: tuple[float, float]
    velocity: tuple[float, float] = (0.0, 0.0)
    speed: float = 0.0
    heading: float = 0.0  # radians
    cycle: int = 0


class BaseAgent(ABC):
    """
    Abstract base class for MAZ3 agents.

    Subclasses implement the 4 agent-side phases of Syncference.
    Phase 4 (CONVERGE) is handled by the simulation engine.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._agent_id = config.agent_id
        self._state = AgentState(position=config.start_position)
        self._last_shared_mvr: Optional[dict] = None
        self._cycle: int = 0

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def position(self) -> tuple[float, float]:
        return self._state.position

    @property
    def velocity(self) -> tuple[float, float]:
        return self._state.velocity

    # =================================================================
    # Phase 1 — SENSE
    # =================================================================

    @abstractmethod
    def sense(self, environment: dict) -> None:
        """
        Phase 1: Perceive local environment.

        The environment dict contains ONLY what the agent can observe:
        - "nearby_obstacles": list of obstacle positions/shapes
        - "boundary": simulation boundary
        - "cycle": current cycle number

        It does NOT contain other agents' internal states.
        Other agents are visible only through the shared MVR (Phase 5).
        """
        ...

    # =================================================================
    # Phase 2 — INFER
    # =================================================================

    @abstractmethod
    def infer(self) -> None:
        """
        Phase 2: Produce local world model and intent.

        The agent updates its internal model and decides what it
        WANTS to do next cycle. This is proprietary and opaque.
        The engine never calls this directly on behalf of other agents.
        """
        ...

    # =================================================================
    # Phase 3 — SHARE (Projection)
    # =================================================================

    @abstractmethod
    def project(self) -> MVRProjection:
        """
        Phase 3: Extract MVR projection from internal state.

        The projection function π: W → M extracts ONLY the 5 MVR fields.
        This is lossy by design — it discards proprietary detail while
        preserving coordination-relevant information.

        Returns a valid MVRProjection.
        """
        ...

    # =================================================================
    # Phase 5 — ACT
    # =================================================================

    @abstractmethod
    def act(self, shared_mvr: dict, dt: float) -> None:
        """
        Phase 5: Execute action given converged MVR.

        The agent receives M* and evaluates its planned action against it.
        - If compatible → proceed
        - If not → re-plan using M* as constraint

        The MVR CONSTRAINS agents — it does not COMMAND them.
        The decision to act remains sovereign.

        Args:
            shared_mvr: The converged MVR from operator Γ.
            dt: Time step in seconds.
        """
        ...

    # =================================================================
    # Utility
    # =================================================================

    def receive_shared_mvr(self, shared_mvr: dict) -> None:
        """Store the shared MVR for use in act()."""
        self._last_shared_mvr = shared_mvr

    def advance_cycle(self) -> None:
        """Increment cycle counter."""
        self._cycle += 1
        self._state.cycle = self._cycle

    def get_info(self) -> dict:
        """Public info about this agent (for logging, not for other agents)."""
        return {
            "agent_id": self._agent_id,
            "type": self.__class__.__name__,
            "position": self._state.position,
            "velocity": self._state.velocity,
            "cycle": self._cycle,
        }
