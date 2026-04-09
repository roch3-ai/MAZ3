"""
Bottleneck Scenario — Narrow corridor with forced spatial conflict.

Layout:
  ┌──────────────────────────────────────────────────┐
  │                                                  │
  │   A1 →           ┌─────────┐           ← A2     │
  │                   │ CORRIDOR │                    │
  │   A3 →           └─────────┘                     │
  │                                                  │
  └──────────────────────────────────────────────────┘

  - 50m × 50m field
  - Corridor: 20m long × 4m wide centered at y=25
  - Walls above and below corridor force agents through narrow passage
  - Agents start on opposite sides → head-on conflict in corridor

This scenario produces:
  - Spatial envelope overlap (multiple agents in narrow corridor)
  - H_p drops when agents compete for corridor space
  - ΔK rises as agents approach each other in confined space
  - Deference escalation (D1→D2→D3 depending on speeds)
  - VoidIndex shows corridor as non-void, open areas as void

This is the PRIMARY scenario for Paper 1 data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.reference_random import ReferenceRandomAgent
from agents.reference_greedy import ReferenceGreedyAgent
from engine.simulation import SimulationEngine, SimulationConfig
from roch3.void_index import VoidConfig


@dataclass
class BottleneckConfig:
    """Configuration for the Bottleneck scenario."""
    field_width: float = 50.0
    field_height: float = 50.0
    corridor_x_start: float = 15.0
    corridor_x_end: float = 35.0
    corridor_y_center: float = 25.0
    corridor_half_width: float = 2.0  # 4m total width
    max_speed: float = 3.0
    min_separation: float = 2.0


@dataclass
class BottleneckObstacles:
    """Obstacles defining the corridor walls."""
    walls: list[dict] = field(default_factory=list)

    @classmethod
    def from_config(cls, cfg: BottleneckConfig) -> BottleneckObstacles:
        """Generate wall obstacles that form the corridor."""
        # Upper wall: blocks movement above corridor
        upper_wall = {
            "type": "wall",
            "x_min": cfg.corridor_x_start,
            "y_min": cfg.corridor_y_center + cfg.corridor_half_width,
            "x_max": cfg.corridor_x_end,
            "y_max": cfg.field_height,
        }
        # Lower wall: blocks movement below corridor
        lower_wall = {
            "type": "wall",
            "x_min": cfg.corridor_x_start,
            "y_min": 0.0,
            "x_max": cfg.corridor_x_end,
            "y_max": cfg.corridor_y_center - cfg.corridor_half_width,
        }
        return cls(walls=[upper_wall, lower_wall])


def create_bottleneck_agents(
    bottleneck_cfg: BottleneckConfig,
    agent_types: str = "syncference",
    seed: int = 42,
) -> list[BaseAgent]:
    """
    Create agents for the Bottleneck scenario.

    Agent placements:
    - Agent 1: left side, heading right through corridor
    - Agent 2: right side, heading left through corridor (head-on)
    - Agent 3: left side, slightly offset, heading right

    agent_types:
      "syncference" — all 3 are Syncference (ideal coordination)
      "mixed"       — 1 Syncference + 1 Greedy + 1 Random
      "greedy"      — all 3 are Greedy (worst case)
    """
    cfg = bottleneck_cfg
    cy = cfg.corridor_y_center
    agents = []

    if agent_types == "syncference":
        agents = [
            ReferenceSyncferenceAgent(
                AgentConfig(
                    agent_id="sync_left_1",
                    start_position=(5.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(45.0, cy),
            ),
            ReferenceSyncferenceAgent(
                AgentConfig(
                    agent_id="sync_right_1",
                    start_position=(45.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(5.0, cy),
            ),
            ReferenceSyncferenceAgent(
                AgentConfig(
                    agent_id="sync_left_2",
                    start_position=(5.0, cy + 4.0),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(45.0, cy),
            ),
        ]
    elif agent_types == "mixed":
        agents = [
            ReferenceSyncferenceAgent(
                AgentConfig(
                    agent_id="sync_left_1",
                    start_position=(5.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(45.0, cy),
            ),
            ReferenceGreedyAgent(
                AgentConfig(
                    agent_id="greedy_right_1",
                    start_position=(45.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(5.0, cy),
            ),
            ReferenceRandomAgent(
                AgentConfig(
                    agent_id="random_left_1",
                    start_position=(5.0, cy + 4.0),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                seed=seed,
            ),
        ]
    elif agent_types == "greedy":
        agents = [
            ReferenceGreedyAgent(
                AgentConfig(
                    agent_id="greedy_left_1",
                    start_position=(5.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(45.0, cy),
            ),
            ReferenceGreedyAgent(
                AgentConfig(
                    agent_id="greedy_right_1",
                    start_position=(45.0, cy),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(5.0, cy),
            ),
            ReferenceGreedyAgent(
                AgentConfig(
                    agent_id="greedy_left_2",
                    start_position=(5.0, cy + 4.0),
                    max_speed=cfg.max_speed,
                    min_separation=cfg.min_separation,
                ),
                goal=(45.0, cy),
            ),
        ]
    else:
        raise ValueError(f"Unknown agent_types: {agent_types}")

    return agents


def create_bottleneck_simulation(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 200,
    db_path: str = "maz3_bottleneck.db",
    jitter_seed: int = 42,
) -> tuple[SimulationEngine, BottleneckConfig]:
    """
    Create a fully configured Bottleneck simulation.
    Returns (engine, bottleneck_config).
    """
    bcfg = BottleneckConfig()
    obstacles = BottleneckObstacles.from_config(bcfg)

    sim_config = SimulationConfig(
        scenario="bottleneck",
        network_profile=network_profile,
        dt=0.1,
        max_cycles=max_cycles,
        boundary=(0, 0, bcfg.field_width, bcfg.field_height),
        void_config=VoidConfig(
            width=bcfg.field_width,
            height=bcfg.field_height,
            resolution=1.0,
        ),
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    engine = SimulationEngine(sim_config)

    agents = create_bottleneck_agents(bcfg, agent_types, seed=jitter_seed)
    for agent in agents:
        engine.add_agent(agent)

    return engine, bcfg
