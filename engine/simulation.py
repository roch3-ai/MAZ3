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
import time
from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent
from agents.baseline_agent import BaselineAgent
from agents.omniscient_coordinator_v2 import (
    AgentGroundTruth, OmniscientCoordinatorV2,
)
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
    # When set, the engine replaces GammaOperator with an alternative
    # coordinator for Phase 4. Currently supported: "omniscient_v2".
    coordinator_override: Optional[str] = None
    # Environmental risk zones published in the environment dict (seen by
    # agents subject to sensing_radius) AND injected lossless into
    # OmniscientCoordinatorV2's ground-truth risk field. Each zone is a dict:
    # {"center": (cx, cy), "half_size": float, "value": risk in [0,1]}.
    # Empty by default — Bottleneck and other scenarios are unaffected.
    risk_zones: list[dict] = field(default_factory=list)
    # Syncference sensing radius for risk_zones. Defaults to infinity so
    # pre-existing scenarios (no risk_zones) remain bit-identical.
    sensing_radius: float = float("inf")


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
    # Paper 1 v4 instrumentation (not used by sovereignty path):
    collisions: int = 0            # pair-wise distance < min_separation/2 violations this cycle
    mean_agent_speed: float = 0.0  # average |velocity| across all agents this cycle


class SimulationEngine:
    """
    Main simulation engine for MAZ3.

    Drives the Syncference loop and coordinates all subsystems.
    """

    def __init__(self, config: SimulationConfig) -> None:
        self._config = config
        self._agents: dict[str, BaseAgent] = {}  # {agent_id: agent}

        # Core subsystems (Paso 0 components)
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

        # Alternate coordinator (omniscient_v2). See Phase 4 branch in step().
        self._omni_v2: Optional[OmniscientCoordinatorV2] = None
        if config.coordinator_override == "omniscient_v2":
            self._omni_v2 = OmniscientCoordinatorV2(horizon=2.0, dt=config.dt)
        elif config.coordinator_override is not None:
            raise ValueError(
                f"Unknown coordinator_override: {config.coordinator_override!r}"
            )

        # State
        self._cycle: int = 0
        self._session_id: Optional[str] = None
        self._running: bool = False
        self._history: list[CycleResult] = []
        self._max_history: int = 1000  # bound to prevent memory leak

    def add_agent(self, agent: BaseAgent) -> None:
        """Register an agent for the simulation.

        If the agent is a BaselineAgent, attach the engine hook that exposes
        ground-truth neighbor information. Sovereign agents do not receive
        this hook — sovereignty is architectural, not policy.
        """
        self._agents[agent.agent_id] = agent
        if isinstance(agent, BaselineAgent):
            agent._engine_hook = self

    def get_neighbors(
        self, agent_id: str, radius: float,
    ) -> list[tuple[str, tuple[float, float], tuple[float, float], float]]:
        """
        Return ground-truth state of agents within `radius` of `agent_id`.

        ONLY invoked by BaselineAgent subclasses (via _engine_hook). Sovereign
        agents never reach this code path.

        Returns a list of (neighbor_id, position, velocity, envelope_radius).
        """
        me = self._agents.get(agent_id)
        if me is None:
            return []
        mx, my = me.position
        result = []
        for other_id, other in self._agents.items():
            if other_id == agent_id:
                continue
            ox, oy = other.position
            d = ((ox - mx) ** 2 + (oy - my) ** 2) ** 0.5
            if d <= radius:
                result.append(
                    (other_id, (ox, oy), other.velocity,
                     other._config.envelope_radius)
                )
        return result

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
        if self._omni_v2 is not None:
            # OmniscientCoordinator v2 path: bypass the sovereign buffer.
            # Build lossless ground-truth states from engine-internal data
            # and compose them through the SAME GammaOperator. The ONLY
            # difference between syncference and omniscient_v2 is input
            # fidelity, not composition logic.
            gt_states = self._build_ground_truth_states()
            convergence_result = self._omni_v2.coordinate(gt_states, self._cycle)
            shared_mvr = convergence_result.shared_mvr
            fields = self._omni_v2.last_fields()
        else:
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

        # Paper 1 v4 instrumentation: pair-wise collisions + mean speed.
        # Computed AFTER physical enforcement so the counts reflect what
        # actually happened, not what agents proposed.
        collisions_this_cycle = 0
        speeds: list[float] = []
        agents_snapshot = list(self._agents.values())
        for i in range(len(agents_snapshot)):
            vi = agents_snapshot[i].velocity
            speeds.append((vi[0] * vi[0] + vi[1] * vi[1]) ** 0.5)
            ax, ay = agents_snapshot[i].position
            min_sep_i = agents_snapshot[i]._config.min_separation
            for j in range(i + 1, len(agents_snapshot)):
                bx, by = agents_snapshot[j].position
                min_sep_j = agents_snapshot[j]._config.min_separation
                threshold = min(min_sep_i, min_sep_j) / 2.0
                dx = ax - bx
                dy = ay - by
                if (dx * dx + dy * dy) ** 0.5 < threshold:
                    collisions_this_cycle += 1
        mean_speed = sum(speeds) / len(speeds) if speeds else 0.0

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
            collisions=collisions_this_cycle,
            mean_agent_speed=mean_speed,
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
            "risk_zones": list(self._config.risk_zones),
            "sensing_radius": self._config.sensing_radius,
        }

    def _push_omniscient_info(self) -> None:
        """
        Backdoor channel for OmniscientCoordinator only.

        Agents that opt in by exposing _set_omniscient_info() receive
        global agent state. Normal agents do NOT have this method, so
        no information leaks. This is the structural enforcement of the
        rule that omniscient access is internal/reference-only.
        """
        # AUDIT ROUND 2 FIX C1: Use anonymous indices, never agent_ids.
        # Even the omniscient backdoor must not leak identity —
        # sovereignty is architecture, not policy.
        snapshot = [
            {
                "index": idx,
                "position": a.position,
                "velocity": a.velocity,
            }
            for idx, a in enumerate(self._agents.values())
        ]
        for agent in self._agents.values():
            if hasattr(agent, "_set_omniscient_info"):
                # Only agents that explicitly opt in receive this
                agent._set_omniscient_info(snapshot)

    def _build_ground_truth_states(self) -> dict[str, AgentGroundTruth]:
        """
        Build per-agent ground-truth state for OmniscientCoordinatorV2.

        This is a backdoor analogous to _push_omniscient_info() but far
        richer: it exposes the exact state that a perfectly-informed
        observer would have. NEVER reachable from sovereign agents — only
        the engine constructs it, and only for the omniscient_v2 path.

        Risk field heuristic: for each agent, populate the cells around
        OTHER agents' positions with a risk proportional to how close that
        neighbor is relative to min_separation. This is still "lossless"
        because the engine knows exactly where every agent is; the field
        is deterministic given agent positions.
        """
        states: dict[str, AgentGroundTruth] = {}
        now = time.time()
        agents_list = list(self._agents.items())

        for agent_id, agent in agents_list:
            # Planned intent: prefer explicit _desired_* attrs, fall back to
            # current velocity. ReferenceSyncferenceAgent sets these in infer().
            planned_dir = getattr(agent, "_desired_direction", None)
            planned_spd = getattr(agent, "_desired_speed", None)
            if planned_dir is None or planned_spd is None:
                vx, vy = agent.velocity
                spd = (vx * vx + vy * vy) ** 0.5
                if spd > 1e-6:
                    planned_dir = (vx / spd, vy / spd)
                    planned_spd = spd
                else:
                    planned_dir = (1.0, 0.0)
                    planned_spd = 0.0
            action_type = "move" if (planned_spd or 0.0) > 0.01 else "stop"

            # Risk field: high-risk cells are those occupied by OTHER agents
            # when their distance to this agent is < 2 × min_separation.
            risk_field: dict[str, float] = {}
            ax, ay = agent.position
            min_sep = agent._config.min_separation
            for other_id, other in agents_list:
                if other_id == agent_id:
                    continue
                ox, oy = other.position
                d = ((ox - ax) ** 2 + (oy - ay) ** 2) ** 0.5
                if d < 2.0 * min_sep:
                    cell = f"{int(ox)}_{int(oy)}"
                    risk = max(0.0, min(1.0, 1.0 - d / (2.0 * min_sep)))
                    # Keep the max per cell (conservative)
                    if risk > risk_field.get(cell, 0.0):
                        risk_field[cell] = risk

            # Omniscient sees configured risk zones in full — no radius filter.
            # This is the information asymmetry that makes SBE non-vacuous:
            # Syncference agents sense zones only within sensing_radius in
            # their own infer(), while the omniscient coordinator composes
            # over the complete zone.
            for zone in self._config.risk_zones:
                zc_x, zc_y = zone["center"]
                hs = zone["half_size"]
                val = zone["value"]
                for ix in range(int(zc_x - hs), int(zc_x + hs) + 1):
                    for iy in range(int(zc_y - hs), int(zc_y + hs) + 1):
                        cell = f"{ix}_{iy}"
                        if val > risk_field.get(cell, 0.0):
                            risk_field[cell] = val

            states[agent_id] = AgentGroundTruth(
                position=tuple(agent.position),
                velocity=tuple(agent.velocity),
                radius=agent._config.envelope_radius,
                global_time=now,
                planned_direction=tuple(planned_dir),
                planned_speed=float(planned_spd),
                action_type=action_type,
                true_max_speed=agent._config.max_speed,
                true_min_separation=agent._config.min_separation,
                true_risk_field=risk_field,
                true_restricted_zones=[],
            )
        return states

    def _apply_deference(self, shared_mvr: dict, action) -> dict:
        """
        Modify shared MVR based on deference level.

        D0: pass through unchanged
        D1: add advisory flag
        D2: reduce max_speed constraint
        D3: set max_speed to 0 (commanded stop)
        D4: set max_speed to 0 + emergency flag
        """
        if action.level == DeferenceLevel.D0:
            return shared_mvr

        # Deep copy to prevent mutation of shared state
        # (shallow dict() copy was leaking nested mutations)
        modified = copy.deepcopy(shared_mvr) if shared_mvr else {}
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

    def _get_internal_trust(self, agent_id: str) -> float:
        """
        INTERNAL/TESTING ONLY. Get trust score by agent_id.

        This method exists to allow internal testing and operator
        oversight (Supervisability axiom). It must NEVER be exposed
        through the public API or WebSocket interfaces — those use
        anonymized indices only.
        """
        return self._argus.get_trust_score(agent_id)
