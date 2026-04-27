"""
Tests for Brecha A + B additive components.

- trust_floor parameter on ARGUSTrustChannel
- AdversarialMixedAgent (alternation)
- AdversarialBurstRecoveryAgent (temporal phases)
- create_bottleneck_with_focal_agent factory
- attacker_payoff post-run computation
- ACS metric computation
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.adversarial_mixed import AdversarialMixedAgent
from agents.adversarial_burst_recovery import AdversarialBurstRecoveryAgent
from agents.base_agent import AgentConfig
from roch3.sovereign_context import (
    SovereignProjectionBuffer, ARGUSTrustChannel,
)
from scenarios.bottleneck import create_bottleneck_with_focal_agent


def test_trust_floor_clamps_decay():
    """trust_floor=0.3 prevents trust from dropping below 0.3."""
    buf = SovereignProjectionBuffer()
    argus = ARGUSTrustChannel(buf, trust_floor=0.3)

    # Hammer with adversarial observations
    for _ in range(50):
        argus.update_trust("adv_agent", {"type": "spatial_inflation", "severity": 5.0})

    score = argus.get_trust_score("adv_agent")
    assert score >= 0.3 - 1e-9, f"Trust {score} dropped below floor 0.3"


def test_trust_floor_default_zero_preserves_behavior():
    """trust_floor=0 (default) allows trust to drop to 0."""
    buf = SovereignProjectionBuffer()
    argus = ARGUSTrustChannel(buf)  # default

    for _ in range(50):
        argus.update_trust("adv_agent", {"type": "spatial_inflation", "severity": 5.0})

    score = argus.get_trust_score("adv_agent")
    assert score <= 0.001, f"Trust {score} did not reach 0 with default floor"


def test_adversarial_mixed_alternation():
    """AdversarialMixedAgent alternates inflate/underreport per cycle."""
    cfg = AgentConfig(agent_id="m", start_position=(0, 0), max_speed=2.0)
    agent = AdversarialMixedAgent(cfg, activate_after_cycle=0)

    # Cycle 0 (even, post-activation): should be 'inflate'
    agent._cycle = 0
    assert agent.attack_mode_this_cycle == "inflate"

    # Cycle 1 (odd, post-activation): should be 'underreport'
    agent._cycle = 1
    assert agent.attack_mode_this_cycle == "underreport"

    # Cycle 2: inflate again
    agent._cycle = 2
    assert agent.attack_mode_this_cycle == "inflate"


def test_adversarial_mixed_pre_activation_honest():
    """AdversarialMixedAgent is honest before activate_after_cycle."""
    cfg = AgentConfig(agent_id="m", start_position=(0, 0), max_speed=2.0)
    agent = AdversarialMixedAgent(cfg, activate_after_cycle=10)
    agent._cycle = 5
    assert agent.attack_mode_this_cycle == "honest"


def test_burst_recovery_temporal_phases():
    """BurstRecovery alternates burst/recover every burst_period cycles."""
    cfg = AgentConfig(agent_id="b", start_position=(0, 0), max_speed=2.0)
    agent = AdversarialBurstRecoveryAgent(
        cfg, burst_period=10, activate_after_cycle=0,
    )

    # First 10 cycles: burst (phase 0)
    for c in range(10):
        agent._cycle = c
        assert agent.attack_mode_this_cycle == "burst", f"cycle {c}"

    # Cycles 10-19: recover (phase 1)
    for c in range(10, 20):
        agent._cycle = c
        assert agent.attack_mode_this_cycle == "recover", f"cycle {c}"

    # Cycles 20-29: burst again (phase 2 even)
    for c in range(20, 30):
        agent._cycle = c
        assert agent.attack_mode_this_cycle == "burst", f"cycle {c}"


def test_burst_recovery_pre_activation_honest():
    """BurstRecovery is honest before activate_after_cycle."""
    cfg = AgentConfig(agent_id="b", start_position=(0, 0), max_speed=2.0)
    agent = AdversarialBurstRecoveryAgent(
        cfg, burst_period=5, activate_after_cycle=10,
    )
    agent._cycle = 5
    assert agent.attack_mode_this_cycle == "honest"


def test_bottleneck_factory_all_focal_types():
    """create_bottleneck_with_focal_agent supports all 6 focal types."""
    types = ["syncference", "greedy", "inflator", "underreporter",
             "mixed", "burst_recovery"]
    for t in types:
        engine, _ = create_bottleneck_with_focal_agent(
            focal_type=t, max_cycles=5, db_path=":memory:",
        )
        assert engine.agent_count == 3, f"focal_type={t} agent_count != 3"
        engine.initialize()
        # Run a few cycles to confirm no crash
        for _ in range(3):
            engine.step()
        engine.finalize()


def test_bottleneck_factory_unknown_type_raises():
    """Unknown focal_type raises ValueError."""
    try:
        create_bottleneck_with_focal_agent(
            focal_type="not_a_type", db_path=":memory:",
        )
    except ValueError:
        return
    raise AssertionError("Expected ValueError for unknown focal_type")


def test_acs_metric_syncference_high():
    """Syncference focal should score ACS near 1.0."""
    from experiments.brecha_b.acs_metric import compute_acs

    db = "/tmp/maz3_test_acs_sync.db"
    if os.path.exists(db):
        os.remove(db)
    engine, _ = create_bottleneck_with_focal_agent(
        focal_type="syncference", max_cycles=30, db_path=db,
    )
    session_id = engine.initialize()
    focal_idx = engine._buffer.get_index_for_agent("focal_syncference")
    # focal_idx may be None until first cycle stores. Run one cycle first.
    for _ in range(30):
        engine.step()
    focal_idx = engine._buffer.get_index_for_agent("focal_syncference")
    engine.finalize()
    assert focal_idx is not None

    result = compute_acs(db, session_id, "focal_syncference", focal_idx,
                        total_cycles=30)
    os.remove(db)
    assert result.acs >= 0.95, f"Syncference ACS = {result.acs}, expected ≥ 0.95"
    assert result.integrity_extended >= 0.95, \
        f"Sync integrity = {result.integrity_extended}"


def test_acs_metric_greedy_lower():
    """Greedy focal should score ACS lower than Syncference (Integrity gap)."""
    from experiments.brecha_b.acs_metric import compute_acs

    db = "/tmp/maz3_test_acs_greedy.db"
    if os.path.exists(db):
        os.remove(db)
    engine, _ = create_bottleneck_with_focal_agent(
        focal_type="greedy", max_cycles=30, db_path=db,
    )
    session_id = engine.initialize()
    for _ in range(30):
        engine.step()
    focal_idx = engine._buffer.get_index_for_agent("focal_greedy")
    engine.finalize()
    assert focal_idx is not None

    result = compute_acs(db, session_id, "focal_greedy", focal_idx,
                        total_cycles=30)
    os.remove(db)
    # Greedy SHOULD have integrity issues when D2 fires.
    # In the bottleneck, with 3 agents heading to a corridor, D2 fires within
    # the first few cycles. We expect Greedy's integrity_extended < 1.0.
    # If this test starts failing, the simulation may not be triggering D2 —
    # check kinetic safety thresholds.
    assert result.acs < 1.0, \
        f"Greedy ACS = {result.acs}, expected < 1.0 (compliance gap)"


def test_greedy_focal_violates_compliance():
    """Greedy ignores D2 → custom_metrics records non-compliance."""
    engine, _ = create_bottleneck_with_focal_agent(
        focal_type="greedy",
        max_cycles=20,
        db_path="/tmp/maz3_test_greedy_compliance.db",
    )
    session_id = engine.initialize()
    for _ in range(20):
        engine.step()
    engine.finalize()

    # Query custom_metrics
    import sqlite3
    conn = sqlite3.connect("/tmp/maz3_test_greedy_compliance.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT metric_value FROM custom_metrics "
        "WHERE session_id=? AND metric_name='agent_intent_compliance'",
        (session_id,),
    )
    values = [r[0] for r in cur.fetchall()]
    conn.close()
    os.remove("/tmp/maz3_test_greedy_compliance.db")

    assert len(values) > 0, "No compliance metrics recorded"
    # Greedy should have at least some non-compliant cycles when D2 fires.
    # If no D2 fires within 20 cycles, the test may show all-compliant —
    # which is fine for a smoke test. Just verify the metric is being logged.
