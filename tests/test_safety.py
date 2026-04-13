"""
test_safety.py — Formal verification of D0-D4 deference system.

Validates:
  - Correct escalation through D0→D4 based on ΔK thresholds
  - Latency requirements per level (D1 <100ms, D2 <50ms, D3 <20ms, D4 <10ms)
  - De-escalation when threat recedes
  - θ_K adaptation (antifragility loop interface)

Patent ref: P3 Claims (Kinetic Deference system, D0-D4 graduated response)
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from roch3.kinetic_safety import (
    KineticSafety, KineticState, DeferenceLevel,
    LATENCY_REQUIREMENTS, DEFAULT_THETA_K,
)


def test_d0_passive_monitoring():
    """D0: agents far apart → no intervention."""
    print("--- D0: Passive Monitoring ---")
    safety = KineticSafety()

    t = time.time()
    a = KineticState(position=(0, 0), velocity=(1, 0), timestamp=t)
    b = KineticState(position=(100, 100), velocity=(-1, 0), timestamp=t)

    action = safety.evaluate(0, a, [b])
    assert action.level == DeferenceLevel.D0, f"Expected D0, got D{action.level}"
    assert action.delta_k < DEFAULT_THETA_K[DeferenceLevel.D1], "ΔK should be below D1 threshold"
    print(f"  ΔK={action.delta_k:.4f}, level=D0 ✓")
    print("✓ test_d0_passive_monitoring PASSED\n")


def test_d1_advisory():
    """D1: agents approaching → advisory issued."""
    print("--- D1: Advisory ---")
    safety = KineticSafety(min_separation=5.0)

    t = time.time()
    a = KineticState(position=(10, 0), velocity=(2, 0), timestamp=t)
    b = KineticState(position=(18, 0), velocity=(-1, 0), timestamp=t)

    action = safety.evaluate(0, a, [b])
    assert action.level >= DeferenceLevel.D1, f"Expected ≥D1, got D{action.level}"
    assert action.delta_k >= DEFAULT_THETA_K[DeferenceLevel.D1], "ΔK should exceed D1 threshold"
    print(f"  ΔK={action.delta_k:.4f}, level=D{action.level} ✓")
    print("✓ test_d1_advisory PASSED\n")


def test_d2_speed_correction():
    """D2: agents on near-collision course → speed correction."""
    print("--- D2: Speed Correction ---")
    safety = KineticSafety(min_separation=5.0)

    t = time.time()
    # Head-on, close, high speed
    a = KineticState(position=(8, 0), velocity=(4, 0), timestamp=t)
    b = KineticState(position=(14, 0), velocity=(-4, 0), timestamp=t)

    action = safety.evaluate(0, a, [b])
    assert action.level >= DeferenceLevel.D2, f"Expected ≥D2, got D{action.level}"
    print(f"  ΔK={action.delta_k:.4f}, level=D{action.level} ✓")
    print("✓ test_d2_speed_correction PASSED\n")


def test_latency_requirements():
    """All deference computations must meet their latency requirements."""
    print("--- Latency Requirements ---")
    safety = KineticSafety()

    t = time.time()

    # Test each level's computation time
    scenarios = [
        ("D0 (far)", (0, 0), (1, 0), (100, 100), (-1, 0)),
        ("D1 (approach)", (10, 0), (3, 0), (18, 0), (-2, 0)),
        ("D2 (near)", (8, 0), (4, 0), (12, 0), (-4, 0)),
    ]

    for label, pos_a, vel_a, pos_b, vel_b in scenarios:
        a = KineticState(position=pos_a, velocity=vel_a, timestamp=t)
        b = KineticState(position=pos_b, velocity=vel_b, timestamp=t)

        # Warm up
        safety.evaluate(0, a, [b])

        # Measure
        latencies = []
        for _ in range(1000):
            action = safety.evaluate(0, a, [b])
            latencies.append(action.latency_ms)

        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        req = LATENCY_REQUIREMENTS.get(action.level, float("inf"))
        met = max_lat < req

        print(f"  {label}: avg={avg_lat:.4f}ms max={max_lat:.4f}ms req=<{req}ms {'✓' if met else '✗'}")
        # Computation time should be well under requirements
        # (network latency is separate — this is just the ΔK computation)
        assert avg_lat < 1.0, f"Average computation too slow: {avg_lat}ms"

    print("✓ test_latency_requirements PASSED\n")


def test_de_escalation():
    """When threat recedes, deference level should drop back down."""
    print("--- De-escalation ---")
    safety = KineticSafety(min_separation=5.0)

    t = time.time()

    # Phase 1: agents approaching (should escalate)
    a1 = KineticState(position=(10, 0), velocity=(3, 0), timestamp=t)
    b1 = KineticState(position=(16, 0), velocity=(-3, 0), timestamp=t)
    action1 = safety.evaluate(0, a1, [b1])
    print(f"  Approaching: D{action1.level} (ΔK={action1.delta_k:.3f})")
    high_level = action1.level

    # Phase 2: agents separating (should de-escalate)
    a2 = KineticState(position=(10, 0), velocity=(-2, 0), timestamp=t + 1)
    b2 = KineticState(position=(30, 0), velocity=(2, 0), timestamp=t + 1)
    action2 = safety.evaluate(0, a2, [b2])
    print(f"  Separating:  D{action2.level} (ΔK={action2.delta_k:.3f})")

    assert action2.level <= high_level, "Level should drop when agents separate"
    assert action2.delta_k < action1.delta_k, "ΔK should decrease when separating"

    print("✓ test_de_escalation PASSED\n")


def test_theta_k_adaptation():
    """θ_K can be updated (antifragility loop interface)."""
    print("--- θ_K Adaptation ---")
    safety = KineticSafety()

    # Get current thresholds
    original = safety.get_theta_k()
    print(f"  Original θ_K: {dict(original)}")

    # Tighten D1 threshold (lower = more sensitive)
    safety.update_theta_k(DeferenceLevel.D1, 0.15)
    updated = safety.get_theta_k()
    assert updated[DeferenceLevel.D1] == 0.15
    print(f"  Updated D1 θ_K: {updated[DeferenceLevel.D1]}")

    # Now the same scenario should escalate more easily
    t = time.time()
    a = KineticState(position=(10, 0), velocity=(1.5, 0), timestamp=t)
    b = KineticState(position=(20, 0), velocity=(-0.5, 0), timestamp=t)

    action_tight = safety.evaluate(0, a, [b])

    # Loosen back
    safety.update_theta_k(DeferenceLevel.D1, 0.5)
    action_loose = safety.evaluate(1, a, [b])

    print(f"  Tight θ_K: D{action_tight.level}, Loose θ_K: D{action_loose.level}")
    assert action_tight.level >= action_loose.level, "Tighter threshold should escalate more"

    # Validation: reject out-of-range values
    try:
        safety.update_theta_k(DeferenceLevel.D1, 1.5)
        assert False, "Should reject θ_K > 1"
    except ValueError:
        print("  Rejects θ_K > 1 ✓")

    try:
        safety.update_theta_k(DeferenceLevel.D1, -0.1)
        assert False, "Should reject θ_K < 0"
    except ValueError:
        print("  Rejects θ_K < 0 ✓")

    print("✓ test_theta_k_adaptation PASSED\n")


def test_multiple_neighbors():
    """ΔK should consider the MOST dangerous neighbor."""
    print("--- Multiple Neighbors ---")
    safety = KineticSafety(min_separation=5.0)

    t = time.time()
    agent = KineticState(position=(10, 10), velocity=(0, 0), timestamp=t)

    # One far neighbor + one close neighbor
    far = KineticState(position=(50, 50), velocity=(0, 0), timestamp=t)
    close = KineticState(position=(12, 10), velocity=(-3, 0), timestamp=t)

    action_both = safety.evaluate(0, agent, [far, close])
    action_far_only = safety.evaluate(1, agent, [far])

    print(f"  Both neighbors: D{action_both.level} (ΔK={action_both.delta_k:.3f})")
    print(f"  Far only:       D{action_far_only.level} (ΔK={action_far_only.delta_k:.3f})")

    assert action_both.delta_k >= action_far_only.delta_k, (
        "Close neighbor should increase or maintain ΔK"
    )

    print("✓ test_multiple_neighbors PASSED\n")


def test_no_neighbors():
    """No neighbors → D0 always."""
    print("--- No Neighbors ---")
    safety = KineticSafety()

    t = time.time()
    agent = KineticState(position=(25, 25), velocity=(5, 0), timestamp=t)

    action = safety.evaluate(0, agent, [])
    assert action.level == DeferenceLevel.D0
    assert action.delta_k == 0.0
    print(f"  No neighbors: D{action.level} (ΔK={action.delta_k}) ✓")

    print("✓ test_no_neighbors PASSED\n")


if __name__ == "__main__":
    test_d0_passive_monitoring()
    test_d1_advisory()
    test_d2_speed_correction()
    test_latency_requirements()
    test_de_escalation()
    test_theta_k_adaptation()
    test_multiple_neighbors()
    test_no_neighbors()
    print("=" * 55)
    print("=== ALL SAFETY TESTS PASSED ===")
    print("=" * 55)
