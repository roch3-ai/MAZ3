"""
Simulation Engine — Main Syncference Loop

Orchestrates the 5-phase Syncference cycle across all agents:

  Phase 1: SENSE   — each agent perceives environment
  Phase 2: INFER   — each agent produces local model + intent
  Phase 3: SHARE   — each agent projects MVR (stored in SovereignProjectionBuffer)
  Phase 4: CONVERGE — Γ produces shared MVR M* (+ ARGUS trust + jitter)
  Phase 5: ACT     — each agent executes action constrained by M*

After each cycle:
  - Harmony Index computed
  - VoidIndex updated
  - Kinetic Safety evaluated
  - Flight Recorder logs snapshot

The engine does NOT read agent internal state.
The ONLY interface is MVR projections.

Patent ref: P4 Section 3.1 (Syncference Protocol), P3 (Kinetic Deference)
"""

from __future__ import annotations

import copy
import random
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import numpy as _np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

from agents.base_agent import BaseAgent
from agents.omniscient_coordinator import OmniscientCoordinator
from roch3.sovereign_context import SovereignProjectionBuffer, ARGUSTrustChannel
from roch3.convergence import GammaOperator
from roch3.harmony import compute_harmony_index, HarmonyResult
from roch3.void_index import VoidIndex, VoidConfig
from roch3.network_jitter import NetworkJitterModel
from roch3.kinetic_safety import KineticSafety, KineticState, DeferenceLevel
from roch3.adversarial_detection import AdversarialDetector
from api.models import FlightRecorder


@dataclass
class SimulationConfig:
    """Configuration for a simulation session."""
    scenario: str = "open_field"
    network_profile: str = "ideal"
    dt: float = 0.1  # seconds per cycle
    max_cycles: int = 500
    boundary: tuple[float, float, float, float] = (0.0, 0.0, 50.0, 50.0)
    void_config: Optional[VoidConfig] = None
    db_path: str = "maz3_flight_recorder.db"
    record_every_n: int = 1  # record snapshot every N cycles
    jitter_seed: Optional[int] = None
    seed: Optional[int] = None  # global RNG seed for full determinism


@dataclass
class CycleResult:
    """Result of a single Syncference cycle."""
    cycle: int
    harmony: HarmonyResult
    convergence_time_ms: float
    agent_count: int
    deference_actions: list  # DeferenceAction list
    void_snapshot: dict
    shared_mvr: dict
    attacks_detected: list = field(default_factory=list)  # attack type names this cycle
    trust_scores: dict = field(default_factory=dict)  # {anonymous_index: score} — NEVER agent_ids


class SimulationEngine:
    """
    Main simulation engine for MAZ3.

    Drives the Syncference loop and coordinates all subsystems.
    """

    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        self._agents: dict[str, BaseAgent] = {}  # {agent_id: agent}

        # Core subsystems
        self._buffer = SovereignProjectionBuffer()
        self._argus = ARGUSTrustChannel(self._buffer)
        self._gamma = GammaOperator()
        self._jitter = NetworkJitterModel(
            config.network_profile,
            seed=config.jitter_seed,
        )
        self._void = VoidIndex(config.void_config or VoidConfig(
            width=config.boundary[2] - config.boundary[0],
            height=config.boundary[3] - config.boundary[1],
        ))
        self._safety = KineticSafety()
        self._detector = AdversarialDetector()
        self._recorder = FlightRecorder(config.db_path)

        # State
        self._cycle: int = 0
        self._session_id: Optional[str] = None
        self._running: bool = False
        self._history: list[CycleResult] = []
        self._max_history: int = 1000  # bound to prevent memory leak

        # M2: Local RNG instance for determinism (seed != jitter_seed)
        # Uses a local Random instance — does NOT call random.seed() globally.
        # Calling random.seed() globally contaminates other concurrent sessions
        # (e.g., FastAPI running multiple benchmarks). The CLI (__main__.py)
        # may set the global seed at process start if full reproducibility is needed.
        # jitter_seed controls NetworkJitterModel RNG separately.
        self._rng = random.Random(config.seed) if config.seed is not None else random.Random()

    def add_agent(self, agent: BaseAgent) -> None:
        """Register an agent for the simulation."""
        self._agents[agent.agent_id] = agent

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent."""
        self._agents.pop(agent_id, None)
        self._buffer.remove_agent(agent_id)

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def cycle(self) -> int:
        return self._cycle

    # =================================================================
    # Lifecycle
    # =================================================================

    def initialize(self) -> str:
        """Initialize the simulation. Returns session_id."""
        from roch3.__version__ import __benchmark_version__
        self._recorder.initialize()
        self._session_id = self._recorder.create_session(
            scenario=self._config.scenario,
            network_profile=self._config.network_profile,
            agent_count=len(self._agents),
            maze_version=__benchmark_version__,
        )
        self._cycle = 0
        self._running = True
        return self._session_id

    def finalize(self) -> dict:
        """End the simulation. Returns session summary."""
        self._running = False
        if self._session_id:
            self._recorder.end_session(self._session_id)
            summary = self._recorder.get_session_summary(self._session_id)
            self._recorder.close()
            return summary or {}
        return {}

    # =================================================================
    # Main Loop
    # =================================================================

    def run(self, cycles: Optional[int] = None) -> list[CycleResult]:
        """
        Run the full simulation for N cycles.
        Returns list of CycleResults.
        """
        max_cycles = cycles or self._config.max_cycles

        if not self._session_id:
            self.initialize()

        results = []
        for _ in range(max_cycles):
            if not self._running:
                break
            result = self.step()
            results.append(result)

        return results

    def step(self) -> CycleResult:
        """
        Execute ONE Syncference cycle (5 phases).
        This is the heart of the simulation.
        """
        self._cycle += 1
        environment = self._build_environment()

        # =============================================================
        # Phase 1 — SENSE
        # =============================================================
        for agent in self._agents.values():
            agent.sense(environment)
        # Backdoor: only OmniscientCoordinator (internal reference) opts in
        self._push_omniscient_info()

        # =============================================================
        # Phase 2 — INFER
        # =============================================================
        for agent in self._agents.values():
            agent.infer()

        # =============================================================
        # Phase 3 — SHARE (Projection)
        # =============================================================
        projections_received = 0
        for agent in self._agents.values():
            projection = agent.project()

            # Apply network jitter — projection may be delayed or lost
            jitter_result = self._jitter.apply()

            if jitter_result.packet_lost:
                # Packet lost — this agent's projection doesn't arrive
                # The buffer retains the PREVIOUS projection (stale but safe)
                self._argus.update_trust(
                    agent.agent_id,
                    {"type": "packet_loss", "severity": 0.5},
                )
                continue

            # Store projection in sovereign buffer (anonymized)
            try:
                self._buffer.store(agent.agent_id, projection)
                projections_received += 1
            except ValueError:
                # Invalid projection — reject and flag
                self._argus.update_trust(
                    agent.agent_id,
                    {"type": "invalid_projection", "severity": 2.0},
                )
                continue

            # Adversarial detection: analyze projection for anomalies
            agent_idx = self._buffer.get_index_for_agent(agent.agent_id)
            if agent_idx is not None:
                detection = self._detector.analyze(
                    index=agent_idx,
                    projection=projection.to_dict(),
                    agent_velocity=agent.velocity,
                )
                # Apply all observations to ARGUS
                for obs in detection.observations:
                    self._argus.update_trust(agent.agent_id, obs)

                # Log adversarial detections to flight recorder
                if detection.attacks_detected and self._session_id:
                    for attack_type in detection.attacks_detected:
                        self._recorder.record_detection(
                            session_id=self._session_id,
                            cycle_number=self._cycle,
                            attack_type=attack_type,
                            detection_latency_ms=detection.detection_latency_ms,
                            deference_level=f"D{self._safety.determine_level(0.5)}",
                            details={
                                "agent_index": agent_idx,
                                "attacks": detection.attacks_detected,
                            },
                        )

        # Push trust weights to buffer (anonymized)
        self._argus.push_weights_to_buffer()

        # =============================================================
        # Phase 4 — CONVERGE (Harmonic Resolution)
        # =============================================================
        fields = self._buffer.get_fields_for_convergence()
        convergence_result = self._gamma.converge(fields, self._cycle)
        shared_mvr = convergence_result.shared_mvr

        # Compute Harmony Index
        harmony = compute_harmony_index(fields, self._cycle)

        # Update VoidIndex
        envelopes = [f["spatial_envelope"] for f in fields]
        self._void.update(envelopes, self._cycle)
        void_snap = self._void.get_snapshot()

        # Check void collapse
        if self._void.void_collapse_detected() and self._session_id:
            self._recorder.record_detection(
                session_id=self._session_id,
                cycle_number=self._cycle,
                attack_type="void_collapse",
                detection_latency_ms=0.0,
                deference_level="D3",
                details=void_snap,
            )

        # =============================================================
        # Phase 5 — ACT (Coordinated Execution)
        # =============================================================
        deference_actions = []
        agent_list = list(self._agents.values())

        for i, agent in enumerate(agent_list):
            # Kinetic safety evaluation BEFORE acting
            current_ks = KineticState(
                position=agent.position,
                velocity=agent.velocity,
                timestamp=time.time(),
            )
            # Neighbors: all other agents
            neighbors_ks = [
                KineticState(
                    position=other.position,
                    velocity=other.velocity,
                    timestamp=time.time(),
                )
                for j, other in enumerate(agent_list) if j != i
            ]

            action = self._safety.evaluate(i, current_ks, neighbors_ks)
            deference_actions.append(action)

            # If deference level requires it, modify shared_mvr to constrain agent
            effective_mvr = self._apply_deference(shared_mvr, action)

            # Capture position BEFORE agent acts (for D3/D4 rollback)
            position_before = tuple(agent.position)

            # Agent acts with (potentially constrained) MVR
            # NOTE: a malicious agent may ignore the MVR. The motor
            # enforces D2/D3/D4 below, regardless of agent compliance.
            agent.act(effective_mvr, self._config.dt)

            # =========================================================
            # PHYSICAL ENFORCEMENT — D3/D4 cannot be ignored by agents
            # =========================================================
            # Without this, D3/D4 would be merely advisory. A malicious
            # agent could ignore the shared MVR and keep moving. This
            # block is what makes P3's "physically enforced" claim true
            # in MAZ3: the engine intercepts the agent's state after act()
            # and overrides it if the deference level demands it.
            # =========================================================
            if action.level >= DeferenceLevel.D3:
                # D3 (commanded stop) / D4 (emergency veto):
                # Agent CANNOT move. Position is rolled back to before act().
                agent.engine_override_state(
                    position=position_before,
                    velocity=(0.0, 0.0),
                )
            elif action.level == DeferenceLevel.D2:
                # D2 (speed correction):
                # Cap velocity to the constraint and recompute position.
                max_spd = effective_mvr.get("constraint_set", {}).get(
                    "max_speed", self._config.boundary[2]
                )
                vx, vy = agent.velocity
                spd = (vx * vx + vy * vy) ** 0.5
                if spd > max_spd > 0:
                    scale = max_spd / spd
                    new_vx = vx * scale
                    new_vy = vy * scale
                    new_pos = (
                        position_before[0] + new_vx * self._config.dt,
                        position_before[1] + new_vy * self._config.dt,
                    )
                    # Clamp to boundary
                    bx0, by0, bx1, by1 = self._config.boundary
                    new_pos = (
                        max(bx0 + 0.1, min(bx1 - 0.1, new_pos[0])),
                        max(by0 + 0.1, min(by1 - 0.1, new_pos[1])),
                    )
                    agent.engine_override_state(
                        position=new_pos,
                        velocity=(new_vx, new_vy),
                    )

        # =============================================================
        # Record to flight recorder
        # =============================================================
        if self._session_id and self._cycle % self._config.record_every_n == 0:
            self._recorder.record_snapshot(
                session_id=self._session_id,
                cycle_number=self._cycle,
                h_p=harmony.h_p,
                convergence_time_ms=convergence_result.convergence_time_ms,
                agent_projections=fields,
                shared_mvr=shared_mvr,
            )
            self._recorder.record_void_snapshot(
                session_id=self._session_id,
                cycle_number=self._cycle,
                total_void_volume=void_snap["total_void_volume"],
                void_zones_count=void_snap["void_zones_count"],
                void_collapse_flag=void_snap["void_collapse_flag"],
                collapse_delta=void_snap.get("collapse_delta"),
            )

            # Log deference events ≥ D1
            for action in deference_actions:
                if action.level >= DeferenceLevel.D1:
                    self._recorder.record_detection(
                        session_id=self._session_id,
                        cycle_number=self._cycle,
                        attack_type=f"deference_D{action.level}",
                        detection_latency_ms=action.latency_ms,
                        deference_level=f"D{action.level}",
                        details=action.details,
                    )

        # Build result
        # SOVEREIGNTY: trust scores are anonymized (keyed by index, not agent_id)
        result = CycleResult(
            cycle=self._cycle,
            harmony=harmony,
            convergence_time_ms=convergence_result.convergence_time_ms,
            agent_count=len(fields),
            deference_actions=deference_actions,
            void_snapshot=void_snap,
            shared_mvr=shared_mvr,
            trust_scores=self._argus.get_anonymized_scores(),
        )
        self._history.append(result)
        # Bound history to prevent memory leak in long-running sessions.
        # Flight recorder is the source of truth — _history is just a
        # convenience for tests and recent-state queries.
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        return result

    # =================================================================
    # Helpers
    # =================================================================

    def _build_environment(self) -> dict:
        """Build the environment dict that agents perceive in Phase 1.

        SOVEREIGNTY: this dict goes to ALL agents. It must contain only
        information that any agent can legitimately observe (boundary,
        cycle counter, public obstacles). It must NEVER contain
        per-agent state — that would leak identity and position to
        every other agent.

        For OmniscientCoordinator (internal reference only), the engine
        provides a separate backdoor channel via _push_omniscient_info().
        """
        return {
            "boundary": self._config.boundary,
            "cycle": self._cycle,
            "nearby_obstacles": [],
        }

    def _push_omniscient_info(self) -> None:
        """
        Backdoor channel for OmniscientCoordinator only.

        Agents that opt in by exposing _set_omniscient_info() receive
        global agent state. Normal agents do NOT have this method, so
        no information leaks. This is the structural enforcement of the
        rule that omniscient access is internal/reference-only.
        """
        # Use buffer index for consistent anonymous identification.



        snapshot = []
        for agent_id, agent in self._agents.items():
            idx = self._buffer.get_index_for_agent(agent_id)
            if idx is not None:
                snapshot.append({
                    "index": idx,
                    "position": agent.position,
                    "velocity": agent.velocity,
                })
        for agent_id, agent in self._agents.items():
            # Structural type check: only OmniscientCoordinator receives global state.



            if isinstance(agent, OmniscientCoordinator):
                own_idx = self._buffer.get_index_for_agent(agent_id)
                agent._set_omniscient_info(snapshot, own_index=own_idx)

    def _apply_deference(self, shared_mvr: dict, action) -> dict:
        """
        Modify shared MVR based on deference level.

        D0: pass through unchanged
        D1: add advisory flag
        D2: reduce max_speed constraint
        D3: set max_speed to 0 (commanded stop)
        D4: set max_speed to 0 + emergency flag
        """
        # Unconditional deepcopy prevents mutation of shared state.



        modified = copy.deepcopy(shared_mvr) if shared_mvr else {}

        if action.level == DeferenceLevel.D0:
            return modified

        constraints = modified.get("constraint_set", {})

        if action.level == DeferenceLevel.D1:
            modified["_advisory"] = {
                "delta_k": action.delta_k,
                "message": "Kinetic risk elevated — caution advised",
            }

        elif action.level == DeferenceLevel.D2:
            # Speed correction: reduce to 50% of current max
            current_max = constraints.get("max_speed", 5.0)
            constraints["max_speed"] = current_max * 0.5
            modified["constraint_set"] = constraints

        elif action.level >= DeferenceLevel.D3:
            # Commanded stop / emergency veto
            constraints["max_speed"] = 0.0
            modified["constraint_set"] = constraints
            if action.level == DeferenceLevel.D4:
                modified["_emergency_veto"] = True

        return modified

    # =================================================================
    # Query
    # =================================================================

    def get_harmony_history(self) -> list[tuple[int, float, str]]:
        """Get (cycle, h_p, status) history."""
        return [(r.cycle, r.harmony.h_p, r.harmony.status)
                for r in self._history]

    def get_last_result(self) -> Optional[CycleResult]:
        return self._history[-1] if self._history else None

    def get_session_id(self) -> Optional[str]:
        return self._session_id

    # =========================================================================
    # Scenario interface (internal benchmark use only)
    # These methods expose agent state for scenario runners and tests.
    # They are NOT part of the public API — external integrators should use
    # only the MVR wire format and CycleResult.
    # =========================================================================

    def get_agent_position(self, agent_id: str) -> tuple[float, float] | None:
        """Get current position of a registered agent. Returns None if not found."""
        agent = self._agents.get(agent_id)
        return agent._state.position if agent is not None else None

    def get_agent_speed(self, agent_id: str) -> float:
        """Get current speed of a registered agent. Returns 0.0 if not found."""
        agent = self._agents.get(agent_id)
        return getattr(agent._state, "speed", 0.0) if agent is not None else 0.0

    def get_agent_ids(self) -> list[str]:
        """Return list of all registered agent IDs."""
        return list(self._agents.keys())

    def get_agent_goal(self, agent_id: str) -> tuple[float, float] | None:
        """Return the goal of an agent if it has one. Returns None if not found."""
        agent = self._agents.get(agent_id)
        if agent is None:
            return None
        return getattr(agent, "_goal", None)

    def get_void_snapshot(self) -> dict:
        """Return current VoidIndex snapshot. For scenario runners and tests only."""
        return self._void.get_snapshot()

    def get_void_fraction(self) -> float:
        """Return current void fraction [0,1]. For scenario runners and tests only."""
        return self._void.void_fraction()

    def void_collapse_detected(self) -> bool:
        """Return True if VoidIndex detects a collapse attack this cycle."""
        return self._void.void_collapse_detected()

    def _get_internal_trust(self, agent_id: str) -> float:
        """
        INTERNAL/TESTING ONLY. Get trust score by agent_id.

        This method exists to allow internal testing and operator
        oversight (Supervisability axiom). It must NEVER be exposed
        through the public API or WebSocket interfaces — those use
        anonymized indices only.
        """
        return self._argus.get_trust_score(agent_id)
