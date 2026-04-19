"""
Asymmetric Risk Scenario — open field with a central high-risk zone.

Purpose:
    Designed to make the Sovereign Behavioral Equivalence (§5.2) experiment
    non-vacuous by decoupling the agents' own sensing from the ground-truth
    risk field. Bottleneck is dominated by local intent/separation logic and
    therefore produces identical sync/omni trajectories (see paso 8a findings).

Geometry:
    - 50m × 50m open field (no corridor, no walls)
    - 5 agents aligned at x=5 with y ∈ {10, 20, 25, 30, 40}
    - Each agent's goal is directly east: (45, y_start)
    - A 15m × 15m square risk zone centered at (25, 25) covers the central
      crossing band. All cells inside the zone have true risk = 0.8. Outside
      the zone, risk = 0.

Asymmetric sensing:
    - Syncference agents perceive risk_gradient only within a 5m radius of
      their current position (sensing_radius is broadcast via the
      environment dict; the agent's infer() honors it).
    - OmniscientCoordinatorV2 reads the full zone from SimulationConfig in
      _build_ground_truth_states — no radius restriction.

This gives lossless M* a tangible informational advantage over lossy M*:
the composed risk field differs, the Syncference act()'s cell-level check
triggers in more cells, and the two runs can produce distinguishable
trajectories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.reference_greedy import ReferenceGreedyAgent
from agents.orca import ORCAAgent
from engine.simulation import SimulationEngine, SimulationConfig
from roch3.void_index import VoidConfig


@dataclass
class AsymmetricRiskConfig:
    """Configuration for the Asymmetric Risk scenario."""
    field_width: float = 50.0
    field_height: float = 50.0
    risk_zone_center: tuple[float, float] = (25.0, 25.0)
    risk_zone_half_size: float = 7.5      # 15m × 15m total
    risk_zone_value: float = 0.8
    sensing_radius: float = 5.0           # Syncference sensing limit
    max_speed: float = 3.0
    min_separation: float = 2.0
    start_x: float = 5.0
    goal_x: float = 45.0
    start_ys: tuple[float, ...] = (10.0, 20.0, 25.0, 30.0, 40.0)


def create_asymmetric_risk_agents(
    cfg: AsymmetricRiskConfig,
    agent_types: str = "syncference",
    seed: int = 42,
) -> list[BaseAgent]:
    """
    Create 5 agents at (start_x, y) with goals at (goal_x, y).

    agent_types:
      "syncference"   — 5 ReferenceSyncferenceAgents
      "greedy"        — 5 ReferenceGreedyAgents
      "orca"          — 5 ORCAAgents
      "omniscient_v2" — 5 ReferenceSyncferenceAgents (coordinator selected
                        via SimulationConfig.coordinator_override)

    "mixed" is intentionally not supported here: Random has no goal, which
    would bias task_completion. The SBE experiment focuses on sync vs omni
    with greedy/orca as homogeneous baselines.
    """
    ys = cfg.start_ys
    agents: list[BaseAgent] = []

    if agent_types in ("syncference", "omniscient_v2"):
        prefix = "sync" if agent_types == "syncference" else "omni2"
        for i, y in enumerate(ys):
            agents.append(
                ReferenceSyncferenceAgent(
                    AgentConfig(
                        agent_id=f"{prefix}_{i}",
                        start_position=(cfg.start_x, float(y)),
                        max_speed=cfg.max_speed,
                        min_separation=cfg.min_separation,
                    ),
                    goal=(cfg.goal_x, float(y)),
                )
            )
    elif agent_types == "greedy":
        for i, y in enumerate(ys):
            agents.append(
                ReferenceGreedyAgent(
                    AgentConfig(
                        agent_id=f"greedy_{i}",
                        start_position=(cfg.start_x, float(y)),
                        max_speed=cfg.max_speed,
                        min_separation=cfg.min_separation,
                    ),
                    goal=(cfg.goal_x, float(y)),
                )
            )
    elif agent_types == "orca":
        for i, y in enumerate(ys):
            agents.append(
                ORCAAgent(
                    AgentConfig(
                        agent_id=f"orca_{i}",
                        start_position=(cfg.start_x, float(y)),
                        max_speed=cfg.max_speed,
                        min_separation=cfg.min_separation,
                    ),
                    goal=(cfg.goal_x, float(y)),
                )
            )
    else:
        raise ValueError(f"Unknown agent_types for asymmetric_risk: {agent_types}")

    return agents


def create_asymmetric_risk_simulation(
    agent_types: str = "syncference",
    network_profile: str = "ideal",
    max_cycles: int = 300,
    db_path: str = "maz3_asymmetric_risk.db",
    jitter_seed: int = 42,
) -> tuple[SimulationEngine, AsymmetricRiskConfig]:
    """Create a fully configured Asymmetric Risk simulation."""
    cfg = AsymmetricRiskConfig()

    risk_zones = [
        {
            "center": cfg.risk_zone_center,
            "half_size": cfg.risk_zone_half_size,
            "value": cfg.risk_zone_value,
        }
    ]

    sim_config = SimulationConfig(
        scenario="asymmetric_risk",
        network_profile=network_profile,
        dt=0.1,
        max_cycles=max_cycles,
        boundary=(0, 0, cfg.field_width, cfg.field_height),
        void_config=VoidConfig(
            width=cfg.field_width,
            height=cfg.field_height,
            resolution=1.0,
        ),
        db_path=db_path,
        jitter_seed=jitter_seed,
        risk_zones=risk_zones,
        sensing_radius=cfg.sensing_radius,
        coordinator_override=(
            "omniscient_v2" if agent_types == "omniscient_v2" else None
        ),
    )

    engine = SimulationEngine(sim_config)

    agents = create_asymmetric_risk_agents(cfg, agent_types, seed=jitter_seed)
    for agent in agents:
        engine.add_agent(agent)

    return engine, cfg
