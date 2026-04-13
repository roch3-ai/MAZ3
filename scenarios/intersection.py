"""
Intersection Scenario — 4 heterogeneous agents resolve a 4-way intersection
without traffic signals or central coordination.

Layout:
        N (goal: S)
        │
        ↓
  W → ──┼──→  E (goal: W)
        │
        ↑
        S (goal: N)

  (E agent approaches from East, goal is West — head-on with W agent)

  - 4 agents, one from each cardinal direction
  - 60m × 60m field, intersection at center (30, 30)
  - Agents spawn 15m from center, goals are opposite spawns
  - No traffic signals, no central coordinator
  - Coordination only via MVR shared through Γ

This scenario tests:
  - Quorum-free coordination (Claim 73): no leader needed
  - Constraint relaxation under conflict (Claim 43)
  - Kinetic Deference graduated response (D0–D4)
  - Fairness: all 4 agents should cross without systematic starvation

Metrics produced:
  - resolution_cycles: cycles until all agents reach goal vicinity
  - critical_hp_events: cycles where H_p < 0.1 (proxy for severe spatial conflict).
    Note: not true physical collision detection — rename if direct proximity
    measurement is added in a future version.
  - min_h_p_during_crossing: worst Harmony Index at intersection zone
  - fairness_index: 1 - std(wait_times) / mean(wait_times), F=1 is perfect

Patent ref: P3 Claim 43 (constraint relaxation), P4 Claim 73 (quorum-free),
            P4 Claim 55 (strategy-proof)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.reference_random import ReferenceRandomAgent
from agents.reference_greedy import ReferenceGreedyAgent
from agents.adversarial_inflator import AdversarialInflatorAgent
from engine.simulation import SimulationEngine, SimulationConfig
from roch3.void_index import VoidConfig
from roch3.fairness import compute_fairness_index  # noqa: F401 — re-exported for scenario consumers


@dataclass
class IntersectionConfig:
    """Configuration for the Intersection scenario."""
    field_width: float = 60.0
    field_height: float = 60.0
    intersection_size: float = 10.0   # diameter of conflict zone at center
    approach_speed: float = 2.0       # m/s (slower than bottleneck — urban context)
    n_agents: int = 4                 # must be 4 for cardinal layout
    spawn_distance: float = 15.0      # meters from center to spawn point
    goal_tolerance: float = 3.0       # meters — distance to declare "goal reached"
    max_speed: float = 3.0
    min_separation: float = 2.0

    @property
    def center(self) -> tuple[float, float]:
        return (self.field_width / 2.0, self.field_height / 2.0)

    @property
    def spawn_positions(self) -> list[tuple[float, float]]:
        """N, S, E, W spawn positions."""
        cx, cy = self.center
        d = self.spawn_distance
        return [
            (cx, cy - d),   # North agent (approaches from top)
            (cx, cy + d),   # South agent (approaches from bottom)
            (cx + d, cy),   # East agent (approaches from right)
            (cx - d, cy),   # West agent (approaches from left)
        ]

    @property
    def goal_positions(self) -> list[tuple[float, float]]:
        """Each agent's goal is the opposite spawn."""
        cx, cy = self.center
        d = self.spawn_distance
        return [
            (cx, cy + d),   # North agent → goes to South side
            (cx, cy - d),   # South agent → goes to North side
            (cx - d, cy),   # East agent → goes to West side
            (cx + d, cy),   # West agent → goes to East side
        ]



@dataclass
class IntersectionResult:
    """Results of an Intersection scenario run."""
    session_id: Optional[str]
    cycles_run: int
    resolution_cycles: Optional[int]   # None if not all agents reached goal
    all_goals_reached: bool
    critical_hp_events: int            # cycles where H_p < 0.1 (severe conflict proxy)
    # NOTE: This is H_p-based, not direct proximity measurement.
    # True collision detection (distance < min_separation) is a future improvement.
    min_h_p: float
    avg_h_p: float
    fairness_index: float
    deference_counts: dict             # {D0: int, D1: int, D2+: int}
    wait_times: list[float]            # wait time per agent (cycles stalled)


def _agent_label(direction: str) -> str:
    return f"intersection_{direction}"


def create_intersection_agents(
    cfg: IntersectionConfig,
    agent_types: str = "syncference",
    seed: int = 42,
) -> list[BaseAgent]:
    """
    Create 4 agents for the Intersection scenario.

    agent_types:
      "syncference" — all 4 Syncference (ideal coordination, validates Claim 73)
      "mixed"       — 2 Syncference + 1 Greedy + 1 Random
      "adversarial" — 3 Syncference + 1 AdversarialInflator (attack resilience)
    """
    labels = ["north", "south", "east", "west"]
    spawns = cfg.spawn_positions
    goals = cfg.goal_positions
    agents: list[BaseAgent] = []

    def _base_config(i: int) -> AgentConfig:
        return AgentConfig(
            agent_id=_agent_label(labels[i]),
            start_position=spawns[i],
            max_speed=cfg.max_speed,
            min_separation=cfg.min_separation,
        )

    if agent_types == "syncference":
        for i in range(4):
            agents.append(
                ReferenceSyncferenceAgent(_base_config(i), goal=goals[i])
            )

    elif agent_types == "mixed":
        # N: Syncference, S: Syncference, E: Greedy, W: Random
        agents.append(ReferenceSyncferenceAgent(_base_config(0), goal=goals[0]))
        agents.append(ReferenceSyncferenceAgent(_base_config(1), goal=goals[1]))
        agents.append(ReferenceGreedyAgent(_base_config(2), goal=goals[2]))
        agents.append(ReferenceRandomAgent(_base_config(3), seed=seed))

    elif agent_types == "adversarial":
        # N/S/W: Syncference, E: Inflator (activates after cycle 10)
        agents.append(ReferenceSyncferenceAgent(_base_config(0), goal=goals[0]))
        agents.append(ReferenceSyncferenceAgent(_base_config(1), goal=goals[1]))
        agents.append(AdversarialInflatorAgent(
            _base_config(2),
            goal=goals[2],
            inflation_factor=3.0,
            activate_after_cycle=10,
        ))
        agents.append(ReferenceSyncferenceAgent(_base_config(3), goal=goals[3]))

    else:
        raise ValueError(f"Unknown agent_types: {agent_types!r}. "
                         f"Expected 'syncference', 'mixed', or 'adversarial'.")

    return agents


def create_intersection_simulation(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 300,
    db_path: str = "maz3_intersection.db",
    jitter_seed: int = 42,
    intersection_size: float = 10.0,
    approach_speed: float = 2.0,
    n_agents: int = 4,
) -> tuple[SimulationEngine, IntersectionConfig]:
    """
    Create a fully configured Intersection simulation.
    Returns (engine, intersection_config).
    """
    icfg = IntersectionConfig(
        intersection_size=intersection_size,
        approach_speed=approach_speed,
        n_agents=n_agents,
    )

    sim_config = SimulationConfig(
        scenario="intersection",
        network_profile=network_profile,
        dt=0.1,
        max_cycles=max_cycles,
        boundary=(0.0, 0.0, icfg.field_width, icfg.field_height),
        void_config=VoidConfig(
            width=icfg.field_width,
            height=icfg.field_height,
            resolution=1.0,
        ),
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    engine = SimulationEngine(sim_config)

    agents = create_intersection_agents(icfg, agent_types, seed=jitter_seed)
    for agent in agents:
        engine.add_agent(agent)

    return engine, icfg


def run_intersection_scenario(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 300,
    db_path: str = ":memory:",
    jitter_seed: int = 42,
) -> IntersectionResult:
    """
    Run a complete Intersection scenario and return structured results.

    This is the high-level API for tests and Paper 1 data collection.
    """
    engine, icfg = create_intersection_simulation(
        agent_types=agent_types,
        network_profile=network_profile,
        max_cycles=max_cycles,
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    session_id = engine.initialize()

    goals = icfg.goal_positions
    agent_ids = [_agent_label(d) for d in ["north", "south", "east", "west"]]
    goal_reached = {aid: False for aid in agent_ids}
    wait_times = {aid: 0.0 for aid in agent_ids}  # cycles stalled (speed < 0.1)

    all_h_p: list[float] = []
    critical_hp_events = 0
    resolution_cycles: Optional[int] = None

    deference_counts = {"D0": 0, "D1": 0, "D2+": 0}

    for _ in range(max_cycles):
        result = engine.step()

        # Track H_p
        all_h_p.append(result.harmony.h_p)

        # Track deference events
        for action in result.deference_actions:
            lvl = action.level.value  # DeferenceLevel enum value (0,1,2,3,4)
            if lvl == 0:
                deference_counts["D0"] += 1
            elif lvl == 1:
                deference_counts["D1"] += 1
            else:
                deference_counts["D2+"] += 1

        # Critical H_p events: H_p < 0.1 as proxy for severe spatial conflict.
        # Not true physical collision detection — a future version should measure
        # pairwise agent distances directly against min_separation.
        if result.harmony.h_p < 0.1:
            critical_hp_events += 1

        # Track per-agent position and goal proximity (via public scenario interface)
        for i, aid in enumerate(agent_ids):
            if goal_reached[aid]:
                continue
            pos = engine.get_agent_position(aid)
            if pos is None:
                continue
            gx, gy = goals[i]
            dist = ((pos[0] - gx) ** 2 + (pos[1] - gy) ** 2) ** 0.5
            speed = engine.get_agent_speed(aid)
            if speed < 0.1:
                wait_times[aid] += 1.0
            if dist <= icfg.goal_tolerance:
                goal_reached[aid] = True

        # Check if all goals reached
        if all(goal_reached.values()) and resolution_cycles is None:
            resolution_cycles = result.cycle

    engine.finalize()

    wait_list = list(wait_times.values())
    min_h_p = min(all_h_p) if all_h_p else 0.0
    avg_h_p = sum(all_h_p) / len(all_h_p) if all_h_p else 0.0

    return IntersectionResult(
        session_id=session_id,
        cycles_run=len(all_h_p),
        resolution_cycles=resolution_cycles,
        all_goals_reached=all(goal_reached.values()),
        critical_hp_events=critical_hp_events,
        min_h_p=min_h_p,
        avg_h_p=avg_h_p,
        fairness_index=compute_fairness_index(wait_list),
        deference_counts=deference_counts,
        wait_times=wait_list,
    )
