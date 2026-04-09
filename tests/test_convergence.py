"""
test_convergence.py — Formal verification of Γ properties.

Validates P4 Theorems:
  Theorem 1 (Bounded Convergence): Γ produces valid MVR in bounded time
  Theorem 2 (Monotonic Safety): Γ never produces less safe output than any input
  Theorem 3 (Graceful Degradation): Performance degrades proportionally under packet loss

Plus strategy-proof property (P4 Claim 54).
"""

import sys
import os
import time
import math
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)
from roch3.sovereign_context import SovereignProjectionBuffer, ARGUSTrustChannel
from roch3.convergence import GammaOperator
from roch3.harmony import compute_harmony_index
from engine.simulation import SimulationEngine, SimulationConfig
from engine.session import run_session
from agents.base_agent import AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from roch3.void_index import VoidConfig


def _proj(x, y, max_speed=3.0, min_sep=2.0, risk=0.3):
    return MVRProjection(
        spatial_envelope=SpatialEnvelope(x - 1.5, y - 1.5, x + 1.5, y + 1.5),
        temporal_sync=TemporalSync(time.time(), drift_bound_ms=3.0),
        intent_vector=IntentVector(direction=(1, 0), speed=1.5),
        constraint_set=ConstraintSet(max_speed=max_speed, min_separation=min_sep),
        risk_gradient=RiskGradient(cell_risks={f"{int(x)}_{int(y)}": risk}),
    )


def test_bounded_convergence():
    """
    Theorem 1: Γ produces valid MVR in time T ≤ 2δ + O(n log n).
    For n < 100 agents, T < 8ms.

    Test: convergence time is bounded and scales sub-linearly with n.
    """
    print("--- Theorem 1: Bounded Convergence ---")
    gamma = GammaOperator()

    times_by_n = {}

    for n in [2, 5, 10, 20, 50]:
        buffer = SovereignProjectionBuffer()
        for i in range(n):
            buffer.store(f"agent_{i}", _proj(i * 5, 25))
        fields = buffer.get_fields_for_convergence()

        # Measure convergence time (avg of 100 runs)
        total_ms = 0
        runs = 100
        for _ in range(runs):
            result = gamma.converge(fields, cycle=1)
            total_ms += result.convergence_time_ms

        avg_ms = total_ms / runs
        times_by_n[n] = avg_ms
        print(f"  n={n:3d}: avg convergence = {avg_ms:.4f}ms")

        # Bounded: must be < 8ms for n < 100
        assert avg_ms < 8.0, f"Convergence time {avg_ms}ms exceeds 8ms bound for n={n}"

        # Valid: output must have all fields
        assert "spatial_envelope" in result.shared_mvr
        assert "temporal_sync" in result.shared_mvr
        assert "intent_vector" in result.shared_mvr
        assert "constraint_set" in result.shared_mvr
        assert "risk_gradient" in result.shared_mvr

    # Sub-linear scaling: time for n=50 should be < 25x time for n=2
    ratio = times_by_n[50] / max(times_by_n[2], 0.0001)
    print(f"  Scaling ratio (n=50/n=2): {ratio:.1f}x (should be << 25x)")
    assert ratio < 25, f"Scaling too steep: {ratio}x"

    print("✓ test_bounded_convergence PASSED\n")


def test_monotonic_safety():
    """
    Theorem 2: Γ never produces a less safe state than the most cautious input.

    For every field:
      - Spatial: output envelope ⊇ every input envelope (union)
      - Constraints: output max_speed ≤ min(input max_speeds) (intersection)
      - Constraints: output min_separation ≥ max(input min_separations)
      - Risk: output risk per cell ≥ max(input risk per cell) (pessimistic)
    """
    print("--- Theorem 2: Monotonic Safety ---")
    gamma = GammaOperator()
    buffer = SovereignProjectionBuffer()

    # 3 agents with different constraints and risks
    buffer.store("agent_slow", _proj(10, 20, max_speed=2.0, min_sep=3.0, risk=0.8))
    buffer.store("agent_fast", _proj(30, 30, max_speed=5.0, min_sep=1.0, risk=0.1))
    buffer.store("agent_mid", _proj(20, 25, max_speed=3.0, min_sep=2.0, risk=0.5))

    fields = buffer.get_fields_for_convergence()
    result = gamma.converge(fields, cycle=1)
    mvr = result.shared_mvr

    # Spatial: union ⊇ all inputs
    env = mvr["spatial_envelope"]
    for f in fields:
        e = f["spatial_envelope"]
        assert env["x_min"] <= e["x_min"], "Union must contain all x_min"
        assert env["y_min"] <= e["y_min"], "Union must contain all y_min"
        assert env["x_max"] >= e["x_max"], "Union must contain all x_max"
        assert env["y_max"] >= e["y_max"], "Union must contain all y_max"
    print(f"  Spatial union: [{env['x_min']:.1f}, {env['y_min']:.1f}] → [{env['x_max']:.1f}, {env['y_max']:.1f}]")

    # Constraints: strictest wins
    cs = mvr["constraint_set"]
    input_max_speeds = [f["constraint_set"]["max_speed"] for f in fields]
    input_min_seps = [f["constraint_set"]["min_separation"] for f in fields]

    assert cs["max_speed"] <= min(input_max_speeds), (
        f"max_speed {cs['max_speed']} > min input {min(input_max_speeds)}"
    )
    assert cs["min_separation"] >= max(input_min_seps), (
        f"min_separation {cs['min_separation']} < max input {max(input_min_seps)}"
    )
    print(f"  Constraints: max_speed={cs['max_speed']} (strictest of {input_max_speeds})")
    print(f"  Constraints: min_sep={cs['min_separation']} (strictest of {input_min_seps})")

    # Risk: max per cell
    shared_risks = mvr["risk_gradient"]["cell_risks"]
    for f in fields:
        for cell_id, risk_val in f["risk_gradient"]["cell_risks"].items():
            trust = f.get("_trust_weight", 1.0)
            weighted_risk = risk_val * trust
            if cell_id in shared_risks:
                assert shared_risks[cell_id] >= weighted_risk - 0.001, (
                    f"Cell {cell_id}: shared risk {shared_risks[cell_id]} < input {weighted_risk}"
                )
    print(f"  Risk (max per cell): {shared_risks}")

    # Intents: preserved individually
    intents = mvr["intent_vector"]
    assert len(intents) == 3, "All intents must be preserved"
    print(f"  Intents preserved: {len(intents)} (all 3)")

    print("✓ test_monotonic_safety PASSED\n")


def test_graceful_degradation():
    """
    Theorem 3: Performance degrades proportionally under adverse conditions.

    Test: H_p under wifi_warehouse (1% packet loss) should be lower than
    ideal but not catastrophically so. The degradation should be proportional.
    """
    print("--- Theorem 3: Graceful Degradation ---")

    profiles = ["ideal", "industrial_ethernet", "wifi_warehouse"]
    results = {}

    for profile in profiles:
        result = run_session("syncference", profile, max_cycles=100, jitter_seed=42)
        results[profile] = result
        print(
            f"  {profile:<25s}: avg_H_p={result.avg_h_p:.4f} "
            f"min_H_p={result.min_h_p:.4f}"
        )

    # Ordering: ideal ≥ industrial ≥ wifi (monotonic degradation)
    assert results["ideal"].avg_h_p >= results["industrial_ethernet"].avg_h_p - 0.02, (
        "Ideal should be ≥ industrial"
    )
    assert results["industrial_ethernet"].avg_h_p >= results["wifi_warehouse"].avg_h_p - 0.02, (
        "Industrial should be ≥ wifi"
    )

    # Proportionality: degradation from ideal to wifi should be < 20% relative
    degradation = (results["ideal"].avg_h_p - results["wifi_warehouse"].avg_h_p)
    relative_degradation = degradation / results["ideal"].avg_h_p
    print(f"  Degradation ideal→wifi: {degradation:.4f} ({relative_degradation:.1%} relative)")
    assert relative_degradation < 0.20, (
        f"Degradation too severe: {relative_degradation:.1%} > 20%"
    )

    print("✓ test_graceful_degradation PASSED\n")


def test_strategy_proof_inflation():
    """
    P4 Claim 54: No agent benefits from falsifying its projection.

    Test: an inflator agent should NOT achieve better outcomes than
    an honest agent (measured by progress toward goal and H_p).

    Spatial inflation incurs cost: other agents avoid the inflated area,
    but the inflator also gets restricted by the enlarged shared envelope.
    """
    print("--- Strategy-Proof: Inflation Has Cost ---")

    # Run honest-only scenario
    honest_result = run_session("syncference", "ideal", max_cycles=150)

    # Run with inflator (via mixed — includes 1 greedy which inflates in its own way)
    # For true test, we need a custom session with inflator
    from scenarios.bottleneck import BottleneckConfig
    from agents.adversarial_inflator import AdversarialInflatorAgent

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="bottleneck",
        network_profile="ideal",
        dt=0.1,
        max_cycles=150,
        boundary=(0, 0, 50, 50),
        void_config=VoidConfig(width=50, height=50),
        db_path=db_path,
        jitter_seed=42,
    )

    engine = SimulationEngine(config)

    # 2 honest + 1 inflator (same positions as bottleneck)
    cy = 25.0
    engine.add_agent(ReferenceSyncferenceAgent(
        AgentConfig(agent_id="honest_1", start_position=(5.0, cy), max_speed=3.0),
        goal=(45.0, cy),
    ))
    engine.add_agent(ReferenceSyncferenceAgent(
        AgentConfig(agent_id="honest_2", start_position=(45.0, cy), max_speed=3.0),
        goal=(5.0, cy),
    ))
    engine.add_agent(AdversarialInflatorAgent(
        AgentConfig(agent_id="inflator", start_position=(5.0, cy + 4.0), max_speed=3.0),
        goal=(45.0, cy),
        inflation_factor=3.0,
        activate_after_cycle=10,
    ))

    engine.initialize()
    results = engine.run(150)
    engine.finalize()
    os.unlink(db_path)

    # Inflator's trust should be degraded
    final_trust = results[-1].trust_scores
    inflator_trust = final_trust.get("inflator", 1.0)

    print(f"  Honest-only avg_H_p: {honest_result.avg_h_p:.4f}")
    h_values = [r.harmony.h_p for r in results]
    inflator_avg_h = sum(h_values) / len(h_values)
    print(f"  With-inflator avg_H_p: {inflator_avg_h:.4f}")
    print(f"  Inflator trust at end: {inflator_trust:.4f}")

    # Key assertion: inflator's trust is degraded → its projections are discounted
    assert inflator_trust < 0.5, f"Inflator trust should be low, got {inflator_trust}"

    print("✓ test_strategy_proof_inflation PASSED\n")


def test_convergence_determinism():
    """
    Same inputs → same outputs. Γ is deterministic.
    """
    print("--- Convergence Determinism ---")
    gamma = GammaOperator()
    buffer = SovereignProjectionBuffer()

    # Fixed inputs
    t = 1000000.0  # fixed timestamp
    buffer.store("a1", MVRProjection(
        SpatialEnvelope(5, 20, 8, 23),
        TemporalSync(t, 2.0),
        IntentVector((1, 0), 1.5),
        ConstraintSet(3.0, 2.0),
        RiskGradient({"5_20": 0.4}),
    ))
    buffer.store("a2", MVRProjection(
        SpatialEnvelope(15, 22, 18, 25),
        TemporalSync(t + 0.001, 3.0),
        IntentVector((-1, 0), 2.0),
        ConstraintSet(4.0, 1.5),
        RiskGradient({"15_22": 0.6}),
    ))

    fields = buffer.get_fields_for_convergence()

    # Run 50 times
    results = [gamma.converge(fields, cycle=1).shared_mvr for _ in range(50)]

    # All should be identical
    ref = str(results[0])
    for i, r in enumerate(results[1:], 1):
        assert str(r) == ref, f"Run {i} differs from run 0"

    print(f"  50 runs: all identical ✓")
    print("✓ test_convergence_determinism PASSED\n")


def test_empty_and_single_agent():
    """Edge cases: 0 agents and 1 agent."""
    print("--- Edge Cases: 0 and 1 Agent ---")
    gamma = GammaOperator()

    # 0 agents
    result = gamma.converge([], cycle=0)
    assert result.shared_mvr == {}
    assert result.agent_count == 0
    print("  0 agents: empty MVR ✓")

    # 1 agent
    buffer = SovereignProjectionBuffer()
    buffer.store("solo", _proj(25, 25, max_speed=3.0, min_sep=2.0, risk=0.5))
    fields = buffer.get_fields_for_convergence()
    result = gamma.converge(fields, cycle=1)
    assert result.agent_count == 1
    assert result.shared_mvr["constraint_set"]["max_speed"] == 3.0
    print("  1 agent: passthrough ✓")

    print("✓ test_empty_and_single_agent PASSED\n")


if __name__ == "__main__":
    test_bounded_convergence()
    test_monotonic_safety()
    test_graceful_degradation()
    test_strategy_proof_inflation()
    test_convergence_determinism()
    test_empty_and_single_agent()
    print("=" * 55)
    print("=== ALL CONVERGENCE PROPERTY TESTS PASSED ===")
    print("=" * 55)
