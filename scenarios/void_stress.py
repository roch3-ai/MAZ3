"""
Void Stress Test — Adversarial void collapse attack on compact operational grid.

Layout: 30m × 30m field, 5 honest agents + 1 attacker

  ┌───────────────────────────────┐
  │ [A1]              [A2]        │
  │                               │
  │         [A5]                  │
  │                               │
  │ [A3]              [A4]        │
  │                  [ATTACKER]   │
  └───────────────────────────────┘

  Grid sizing: 30×30 is chosen deliberately. With 5 honest agents (radius 1.5m)
  and an attacker using factor 8.0 (radius 12m → ~576m² claimed per cycle),
  the attacker can reduce void fraction by >40% in a single cycle — well above
  the 20% collapse_delta_threshold. A 100×100 grid would require a much larger
  inflation factor to produce a detectable signal with this agent count.

  The Void Collapse Attack: not a physical intrusion but a declaration attack —
  the attacker claims space it does not occupy to deny void to the system.

Attack mechanics:
  - Attacker uses AdversarialInflatorAgent with high inflation_factor
  - Activates at cycle 5 (early, after minimal trust buildup)
  - Envelope radius 1.5m × factor 8.0 = 12m radius → 576m² per claim
  - In 1 cycle, the attacker claims ~576m² of the 30×30 (900m²) field → >60%
  - VoidIndex should detect: void volume drops >20% in 3-cycle window

What we measure:
  - void_collapse_detected(): must trigger after attacker activates
  - detection_latency: cycles between activation and first detection
  - void_stability_pre: void fraction before activation (baseline)
  - void_drop_magnitude: how much void disappears after activation
  - honest_h_p: H_p of honest agents should remain > 0 (system survives)

Patent ref: P3 VoidIndex claims, P4 Void Collapse Attack detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agents.base_agent import BaseAgent, AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.adversarial_inflator import AdversarialInflatorAgent
from engine.simulation import SimulationEngine, SimulationConfig
from roch3.void_index import VoidIndex, VoidConfig


@dataclass
class VoidStressConfig:
    """Configuration for the Void Stress Test scenario.

    Grid sizing rationale:
      30x30 field with 5 honest agents (radius 1.5m each) claims ~9m2/agent
      leaving ~855m2 (~95%) as potential void. After void_threshold_cycles,
      those cells become void zones.
      Attacker with radius 1.5m x factor 8.0 = 12m radius claims ~576m2 in
      ONE cycle — a >50% drop in void volume, well above collapse_delta=0.20.
      This ensures reliable detection within collapse_window_cycles=3 cycles.
    """
    field_width: float = 30.0
    field_height: float = 30.0
    n_honest_agents: int = 5
    attacker_inflation_factor: float = 8.0    # 8x -> 12m radius -> 576m2 per claim
    attacker_activate_cycle: int = 10          # let voids establish first
    max_speed: float = 2.0
    min_separation: float = 2.0
    # VoidIndex config tuned for 30x30 grid
    void_threshold_cycles: int = 3
    collapse_window_cycles: int = 3
    collapse_delta_threshold: float = 0.20    # 20% drop triggers detection


# Honest agent positions: corners and center of 30x30 field
_HONEST_SPAWNS = [
    (3.0,  3.0),
    (27.0, 3.0),
    (3.0,  27.0),
    (27.0, 27.0),
    (13.0, 17.0),
]

_HONEST_GOALS = [
    (5.0,  5.0),
    (25.0, 5.0),
    (5.0,  25.0),
    (25.0, 25.0),
    (18.0, 12.0),
]

# Attacker starts at center (15,15) — no spawn collision with honest agents.
# Honest agent 5 is at (13,17), distinct from attacker position.
_ATTACKER_SPAWN = (15.0, 15.0)
_ATTACKER_GOAL = (20.0, 20.0)


def create_void_stress_simulation(
    inflation_factor: float = 8.0,
    activate_cycle: int = 5,
    network_profile: str = "ideal",
    max_cycles: int = 200,
    db_path: str = "maz3_void_stress.db",
    jitter_seed: int = 42,
) -> tuple[SimulationEngine, VoidStressConfig]:
    """
    Create a Void Stress Test simulation with custom VoidConfig.
    Returns (engine, void_stress_config).
    """
    cfg = VoidStressConfig(
        attacker_inflation_factor=inflation_factor,
        attacker_activate_cycle=activate_cycle,
    )

    # Sensitive VoidConfig for stress test — faster detection on big grid
    void_cfg = VoidConfig(
        width=cfg.field_width,
        height=cfg.field_height,
        resolution=1.0,
        void_threshold_cycles=cfg.void_threshold_cycles,
        collapse_window_cycles=cfg.collapse_window_cycles,
        collapse_delta_threshold=cfg.collapse_delta_threshold,
    )

    sim_config = SimulationConfig(
        scenario="void_stress",
        network_profile=network_profile,
        dt=0.1,
        max_cycles=max_cycles,
        boundary=(0.0, 0.0, cfg.field_width, cfg.field_height),
        void_config=void_cfg,
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    engine = SimulationEngine(sim_config)

    # Add honest agents
    for i in range(cfg.n_honest_agents):
        honest_cfg = AgentConfig(
            agent_id=f"void_honest_{i+1}",
            start_position=_HONEST_SPAWNS[i],
            max_speed=cfg.max_speed,
            min_separation=cfg.min_separation,
        )
        engine.add_agent(
            ReferenceSyncferenceAgent(honest_cfg, goal=_HONEST_GOALS[i])
        )

    # Add attacker — large inflation to maximize void collapse
    attacker_cfg = AgentConfig(
        agent_id="void_attacker",
        start_position=_ATTACKER_SPAWN,
        max_speed=cfg.max_speed,
        min_separation=cfg.min_separation,
        envelope_radius=1.5,  # real size — the inflation multiplies this
    )
    engine.add_agent(
        AdversarialInflatorAgent(
            attacker_cfg,
            goal=_ATTACKER_GOAL,
            inflation_factor=inflation_factor,
            activate_after_cycle=activate_cycle,
        )
    )

    return engine, cfg


@dataclass
class VoidStressResult:
    """Results of a Void Stress Test run."""
    session_id: Optional[str]
    cycles_run: int

    # Void dynamics
    void_fraction_pre_attack: float     # avg void fraction before attacker activates
    void_fraction_post_attack: float    # avg void fraction after activation
    void_drop_magnitude: float          # pre - post (absolute)

    # Detection
    collapse_detected: bool             # did VoidIndex ever fire void_collapse?
    first_detection_cycle: Optional[int]  # cycle of first detection
    detection_latency: Optional[int]    # cycles between activation and detection

    # System health
    avg_h_p: float
    min_h_p: float

    # Attacker trust
    attacker_final_trust: Optional[float]


def run_void_stress_test(
    inflation_factor: float = 8.0,
    activate_cycle: int = 5,
    network_profile: str = "ideal",
    max_cycles: int = 200,
    db_path: str = ":memory:",
    jitter_seed: int = 42,
) -> VoidStressResult:
    """
    Run a complete Void Stress Test and return structured results.
    """
    engine, cfg = create_void_stress_simulation(
        inflation_factor=inflation_factor,
        activate_cycle=activate_cycle,
        network_profile=network_profile,
        max_cycles=max_cycles,
        db_path=db_path,
        jitter_seed=jitter_seed,
    )

    session_id = engine.initialize()

    # Access void state via public scenario interface

    all_h_p: list[float] = []
    void_fractions: list[tuple[int, float]] = []  # (cycle, fraction)
    collapse_detected = False
    first_detection_cycle: Optional[int] = None

    for _ in range(max_cycles):
        result = engine.step()
        cycle = result.cycle
        all_h_p.append(result.harmony.h_p)

        # Sample void state via public scenario interface
        vf = engine.get_void_fraction()
        void_fractions.append((cycle, vf))

        # Check collapse detection
        if engine.void_collapse_detected():
            if not collapse_detected:
                first_detection_cycle = cycle
            collapse_detected = True

    engine.finalize()

    # Separate pre/post fractions
    pre_fracs = [vf for c, vf in void_fractions if c <= activate_cycle]
    post_fracs = [vf for c, vf in void_fractions if c > activate_cycle]

    void_pre = sum(pre_fracs) / len(pre_fracs) if pre_fracs else 0.0
    void_post = sum(post_fracs) / len(post_fracs) if post_fracs else 0.0

    # Attacker trust: read via engine public API
    attacker_trust: Optional[float] = None
    try:
        attacker_trust = engine._get_internal_trust("void_attacker")
    except (AttributeError, KeyError):
        attacker_trust = None

    detection_latency: Optional[int] = None
    if first_detection_cycle is not None:
        detection_latency = first_detection_cycle - activate_cycle

    return VoidStressResult(
        session_id=session_id,
        cycles_run=len(all_h_p),
        void_fraction_pre_attack=void_pre,
        void_fraction_post_attack=void_post,
        void_drop_magnitude=void_pre - void_post,
        collapse_detected=collapse_detected,
        first_detection_cycle=first_detection_cycle,
        detection_latency=detection_latency,
        avg_h_p=sum(all_h_p) / len(all_h_p) if all_h_p else 0.0,
        min_h_p=min(all_h_p) if all_h_p else 0.0,
        attacker_final_trust=attacker_trust,
    )
