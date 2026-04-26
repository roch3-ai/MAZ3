"""
Corridor Scenario — Bidirectional traffic in a narrow passage.

Layout (top view, N=6 agents, 3 per direction):

    ←───────────────────────── 30m ─────────────────────────→
    ┌─────────────────────────────────────────────────────────┐
    │  [R3 ←]  [R2 ←]  [R1 ←]  │  [L1 →]  [L2 →]  [L3 →]  │ 3m
    └─────────────────────────────────────────────────────────┘

  - Corridor: 30m long × 3m wide (single-lane: only 1 agent fits width-wise)
  - Left-group (L): starts at x=0..5, moves right toward x=25..30
  - Right-group (R): starts at x=25..30, moves left toward x=0..5
  - The passage is too narrow for side-by-side: someone must yield (D2/D3)
  - Head-on conflict guaranteed in the central section

This scenario tests:
  - Kinetic Deference graduation (D0→D1→D2→D3) under sustained spatial pressure
  - Strategy-proof property (Claim 55): greedy agents can't force honest ones out
  - Throughput fairness: both directions should complete eventually
  - H_p behavior under unresolvable overlap without yield protocol

NOTE: Like Intersection, a pure Syncference run will exhibit the symmetric
deadlock property when agents are head-on. This is expected — it documents
the known limitation of Syncference without Claim 43 (constraint relaxation).
The relevant metric here is D-level distribution and H_p under pressure, not
goal completion.

Metrics produced:
  - throughput: agents that complete per 100 cycles (0 if deadlock)
  - fairness: Fairness Index of completion order (if any)
  - avg_h_p, min_h_p: Harmony under bidirectional pressure
  - d_level_distribution: {D0, D1, D2+} counts
  - deference_events_per_agent: D1+ events normalized by agent count

Patent ref: P3 Claim 55 (strategy-proof), P3 Kinetic Deference D0-D4
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.reference_greedy import ReferenceGreedyAgent
from agents.reference_random import ReferenceRandomAgent
from engine.simulation import SimulationEngine, SimulationConfig
from roch3.void_index import VoidConfig
from roch3.fairness import compute_fairness_index


@dataclass
class CorridorConfig:
    """Configuration for the Corridor scenario."""
    corridor_length: float = 30.0    # meters (x-axis)
    corridor_width: float = 3.0      # meters (y-axis) — narrow, 1-agent wide
    n_agents: int = 6                # must be even — half per direction
    max_speed: float = 2.0           # slower than open field — corridor context
    min_separation: float = 1.5      # tighter than bottleneck — narrow passage
    goal_tolerance: float = 2.0      # meters to declare goal reached
    # Field is corridor + margins
    margin: float = 5.0              # margin outside corridor on each side

    @property
    def field_width(self) -> float:
        return self.corridor_length + 2 * self.margin

    @property
    def field_height(self) -> float:
        return self.corridor_width + 2 * self.margin

    @property
    def corridor_y_center(self) -> float:
        return self.field_height / 2.0

    @property
    def corridor_x_start(self) -> float:
        return self.margin

    @property
    def corridor_x_end(self) -> float:
        return self.margin + self.corridor_length

    @property
    def n_per_direction(self) -> int:
        return self.n_agents // 2


def _stagger_y(cfg: CorridorConfig, i: int, n: int) -> float:
    """
    Compute y-position for agent i of n agents in the corridor.
    Agents are staggered slightly in y to break perfect symmetry,
    which helps the protocol find a deference resolution.
    Max stagger is corridor_width/4 to stay within the passage.
    """
    cy = cfg.corridor_y_center
    if n <= 1:
        return cy
    stagger_range = cfg.corridor_width * 0.25
    offset = (i / (n - 1) - 0.5) * 2 * stagger_range
    return cy + offset


def create_corridor_agents(
    cfg: CorridorConfig,
    agent_types: str = "syncference",
    seed: int = 42,
) -> list[BaseAgent]:
    """
    Create agents for the Corridor scenario.

    Left group: spawn at x_start + small offset, goal at x_end - small offset.
    Right group: spawn at x_end - small offset, goal at x_start + small offset.

    Slight y-stagger breaks pure symmetry so deference can resolve.

    agent_types:
      "syncference"  — all Syncference (tests D-level graduation)
      "mixed"        — left: Syncference, right: Greedy (tests strategy-proof)
      "greedy_all"   — all Greedy (worst-case throughput baseline)
    """
    n = cfg.n_per_direction
    agents: list[BaseAgent] = []

    x_left_spawn = cfg.corridor_x_start + 1.0
    x_right_spawn = cfg.corridor_x_end - 1.0
    x_left_goal = cfg.corridor_x_end - 1.0
    x_right_goal = cfg.corridor_x_start + 1.0

    for i in range(n):
        y = _stagger_y(cfg, i, n)
        left_cfg = AgentConfig(
            agent_id=f"corridor_L{i+1}",
            start_position=(x_left_spawn, y),
            max_speed=cfg.max_speed,
            min_separation=cfg.min_separation,
        )
        right_cfg = AgentConfig(
            agent_id=f"corridor_R{i+1}",
            start_position=(x_right_spawn, y),
            max_speed=cfg.max_speed,
            min_separation=cfg.min_separation,
        )

        if agent_types == "syncference":
            agents.append(ReferenceSyncferenceAgent(left_cfg, goal=(x_left_goal, y)))
            agents.append(ReferenceSyncferenceAgent(right_cfg, goal=(x_right_goal, y)))

        elif agent_types == "mixed":
            # Left: honest Syncference, Right: Greedy (tests Claim 55)
            agents.append(ReferenceSyncferenceAgent(left_cfg, goal=(x_left_goal, y)))
            agents.append(ReferenceGreedyAgent(right_cfg, goal=(x_right_goal, y)))

        elif agent_types == "greedy_all":
            agents.append(ReferenceGreedyAgent(left_cfg, goal=(x_left_goal, y)))
            agents.append(ReferenceGreedyAgent(right_cfg, goal=(x_right_goal, y)))

        else:
            raise ValueError(
                f"Unknown agent_types: {agent_types!r}. "
                f"Expected 'syncference', 'mixed', or 'greedy_all'."
            )

    return agents


def create_corridor_simulation(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 400,
    db_path: str = "maz3_corridor.db",
    jitter_seed: int = 42,
    corridor_width: float = 3.0,
    corridor_length: float = 30.0,
    n_agents: int = 6,
) -> tuple[SimulationEngine, CorridorConfig]:
    """
    Create a fully configured Corridor simulation.
    Returns (engine, corridor_config).
    """
    cfg = CorridorConfig(
        corridor_length=corridor_length,
        corridor_width=corridor_width,
        n_agents=n_agents,
    )

    sim_config = SimulationConfig(
        scenario="corridor",
        network_profile=network_profile,
        dt=0.1,
        max_cycles=max_cycles,
        boundary=(0.0, 0.0, cfg.field_width, cfg.field_height),
        void_config=VoidConfig(
            width=cfg.field_width,
            height=cfg.field_height,
            resolution=1.0,
        ),
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    engine = SimulationEngine(sim_config)

    agents = create_corridor_agents(cfg, agent_types, seed=jitter_seed)
    for agent in agents:
        engine.add_agent(agent)

    return engine, cfg


@dataclass
class CorridorResult:
    """Results of a Corridor scenario run."""
    session_id: Optional[str]
    cycles_run: int
    agents_completed: int         # agents that reached their goal
    total_agents: int
    throughput: float             # completed / cycles_run * 100 (per 100 cycles)
    avg_h_p: float
    min_h_p: float
    fairness_index: float         # fairness of completion order
    deference_counts: dict        # {D0: int, D1: int, D2+: int}
    deference_per_agent: float    # (D1+D2+) / n_agents — normalized pressure
    d1_plus_events: int


def run_corridor_scenario(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 400,
    db_path: str = ":memory:",
    jitter_seed: int = 42,
) -> CorridorResult:
    """
    Run a complete Corridor scenario and return structured results.
    """
    engine, cfg = create_corridor_simulation(
        agent_types=agent_types,
        network_profile=network_profile,
        max_cycles=max_cycles,
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    session_id = engine.initialize()

    # Track per-agent goal completion
    all_agent_ids = engine.get_agent_ids()
    goal_reached: dict[str, bool] = {aid: False for aid in all_agent_ids}
    completion_cycle: dict[str, int] = {}  # agent_id → cycle when goal reached

    all_h_p: list[float] = []
    deference_counts = {"D0": 0, "D1": 0, "D2+": 0}

    # Build goal map from agent start positions and config
    # Build goal map via public scenario interface
    goals: dict[str, tuple[float, float]] = {}
    for aid in engine.get_agent_ids():
        goal = engine.get_agent_goal(aid)
        goals[aid] = goal if goal is not None else (0.0, 0.0)

    for _ in range(max_cycles):
        result = engine.step()
        all_h_p.append(result.harmony.h_p)

        # Tally deference
        for action in result.deference_actions:
            lvl = action.level.value
            if lvl == 0:
                deference_counts["D0"] += 1
            elif lvl == 1:
                deference_counts["D1"] += 1
            else:
                deference_counts["D2+"] += 1

        # Check goal proximity
        # Track per-agent goal proximity via public scenario interface
        for aid in engine.get_agent_ids():
            if goal_reached[aid]:
                continue
            pos = engine.get_agent_position(aid)
            if pos is None:
                continue
            gx, gy = goals.get(aid, (0.0, 0.0))
            dist = ((pos[0] - gx) ** 2 + (pos[1] - gy) ** 2) ** 0.5
            if dist <= cfg.goal_tolerance:
                goal_reached[aid] = True
                completion_cycle[aid] = result.cycle

    engine.finalize()

    agents_completed = sum(1 for v in goal_reached.values() if v)
    n = len(all_agent_ids)
    d1_plus = deference_counts["D1"] + deference_counts["D2+"]

    # Fairness of completion timing: keyed by agent_id (not iteration order).
    # Agents that didn't finish get max_cycles as their completion time.
    completion_times = [
        float(completion_cycle[aid]) if aid in completion_cycle else float(max_cycles)
        for aid in all_agent_ids
    ]

    return CorridorResult(
        session_id=session_id,
        cycles_run=len(all_h_p),
        agents_completed=agents_completed,
        total_agents=n,
        throughput=agents_completed / len(all_h_p) * 100 if all_h_p else 0.0,
        avg_h_p=sum(all_h_p) / len(all_h_p) if all_h_p else 0.0,
        min_h_p=min(all_h_p) if all_h_p else 0.0,
        fairness_index=compute_fairness_index(completion_times),
        deference_counts=deference_counts,
        deference_per_agent=d1_plus / n if n > 0 else 0.0,
        d1_plus_events=d1_plus,
    )
