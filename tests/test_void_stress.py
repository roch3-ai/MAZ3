"""
test_void_stress.py

Tests for the Void Stress Test scenario — adversarial void collapse attack.

Claims validated:
  - VoidIndex: persistent void tracking on 2D grid
  - Void Collapse Attack detection: rapid void volume drop triggers alert
  - Trust penalty: attacker trust reaches 0 after sustained inflation

Tests:
  1. Baseline void formation: honest agents establish void zones before attack
  2. Attack detection: collapse_detected=True, latency <= collapse_window
  3. Void drop magnitude: post-attack void fraction < pre-attack
  4. Honest agent survival: H_p stays > 0 (system not destroyed by attack)
  5. Attacker trust penalized: trust reaches 0 or near-0 after sustained inflation
  6. No false positive: without attacker, collapse_detected stays False
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scenarios.void_stress import (
    VoidStressConfig,
    run_void_stress_test,
    create_void_stress_simulation,
)
from roch3.void_index import VoidIndex, VoidConfig


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Baseline void formation (no attacker active yet)
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_baseline_formation():
    """
    Before the attacker activates, honest agents should establish a stable
    void baseline on the 30×30 grid.
    Expected: void_fraction_pre_attack >= 0.50 (most of the grid is unclaimed).
    """
    print("\n--- Void Stress: Baseline Void Formation ---")

    # Run until just past activation so we have both pre and post
    result = run_void_stress_test(
        inflation_factor=8.0,
        activate_cycle=10,
        max_cycles=30,
        db_path=":memory:",
        jitter_seed=42,
    )

    print(f"  void_pre_attack:  {result.void_fraction_pre_attack:.3f}")
    print(f"  void_post_attack: {result.void_fraction_post_attack:.3f}")
    print(f"  cycles_run: {result.cycles_run}")

    # With 5 small agents on 30×30, most cells should be void
    assert result.void_fraction_pre_attack >= 0.50, (
        f"Pre-attack void fraction too low: {result.void_fraction_pre_attack:.3f}. "
        f"Honest agents are too large or too many."
    )

    print(f"  ✓ test_void_stress_baseline_formation PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Attack detection — collapse detected, latency within window
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_collapse_detected():
    """
    Adversarial inflator (factor=8.0) activates at cycle 10.
    Expected: void_collapse_detected() fires within collapse_window_cycles
    after activation. Detection latency <= 3 cycles.

    This is the primary VoidIndex test: the attack must be caught.
    Patent ref: P3 Void Collapse Attack detection.
    """
    print("\n--- Void Stress: Collapse Detection ---")

    cfg = VoidStressConfig()
    result = run_void_stress_test(
        inflation_factor=cfg.attacker_inflation_factor,
        activate_cycle=cfg.attacker_activate_cycle,
        max_cycles=100,
        db_path=":memory:",
        jitter_seed=42,
    )

    print(f"  collapse_detected: {result.collapse_detected}")
    print(f"  first_detection_cycle: {result.first_detection_cycle}")
    print(f"  detection_latency: {result.detection_latency} cycles")
    print(f"  void_drop: {result.void_drop_magnitude:.3f} ({result.void_drop_magnitude*100:.1f}%)")

    # Attack must be detected
    assert result.collapse_detected, (
        "VoidIndex failed to detect void collapse attack. "
        "Check attacker inflation_factor and VoidConfig thresholds."
    )

    # Detection must happen after activation
    assert result.first_detection_cycle is not None
    assert result.first_detection_cycle > cfg.attacker_activate_cycle, (
        f"Detection at cycle {result.first_detection_cycle} should be after "
        f"activation at {cfg.attacker_activate_cycle}"
    )

    # Detection latency must be within the collapse window
    assert result.detection_latency is not None
    assert result.detection_latency <= cfg.collapse_window_cycles, (
        f"Detection latency {result.detection_latency} exceeds "
        f"collapse_window_cycles={cfg.collapse_window_cycles}"
    )

    print(f"  ✓ test_void_stress_collapse_detected PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: Void drop magnitude post-activation
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_drop_magnitude():
    """
    After attacker activates, void volume should drop significantly.
    Expected: void_drop_magnitude >= collapse_delta_threshold (0.20).
    The inflator claims a large fraction of the 30×30 grid per cycle.
    """
    print("\n--- Void Stress: Drop Magnitude ---")

    result = run_void_stress_test(
        inflation_factor=8.0,
        activate_cycle=10,
        max_cycles=60,
        db_path=":memory:",
        jitter_seed=42,
    )

    print(f"  pre_attack void:  {result.void_fraction_pre_attack:.3f} ({result.void_fraction_pre_attack*100:.1f}%)")
    print(f"  post_attack void: {result.void_fraction_post_attack:.3f} ({result.void_fraction_post_attack*100:.1f}%)")
    print(f"  drop magnitude:   {result.void_drop_magnitude:.3f} ({result.void_drop_magnitude*100:.1f}%)")

    # Post-attack void must be lower than pre-attack
    assert result.void_fraction_post_attack < result.void_fraction_pre_attack, (
        f"Post-attack void ({result.void_fraction_post_attack:.3f}) should be "
        f"lower than pre-attack ({result.void_fraction_pre_attack:.3f})"
    )

    # Drop must exceed the detection threshold
    assert result.void_drop_magnitude >= 0.20, (
        f"Void drop {result.void_drop_magnitude:.3f} < 0.20 threshold. "
        f"Inflation factor may be too small for this grid size."
    )

    print(f"  ✓ test_void_stress_drop_magnitude PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Honest agent survival — H_p stays positive
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_honest_agents_survive():
    """
    The void collapse attack should not destroy the honest agents' coordination.
    Expected: avg_H_p > 0.50 — system degrades but does not collapse.

    If H_p collapses to ~0, the protocol has no resilience to declaration attacks.
    Honest agents' spatial envelopes are unaffected by the attacker's claims.
    """
    print("\n--- Void Stress: Honest Agent Survival ---")

    result = run_void_stress_test(
        inflation_factor=8.0,
        activate_cycle=10,
        max_cycles=150,
        db_path=":memory:",
        jitter_seed=42,
    )

    print(f"  avg_H_p: {result.avg_h_p:.4f}")
    print(f"  min_H_p: {result.min_h_p:.4f}")

    # System must not collapse
    assert result.avg_h_p > 0.50, (
        f"Honest agents' H_p collapsed under void attack: {result.avg_h_p:.4f}"
    )

    # H_p must be computable (non-zero)
    assert result.min_h_p > 0.0, (
        f"H_p hit zero — system crashed: min_H_p={result.min_h_p:.4f}"
    )

    print(f"  ✓ test_void_stress_honest_agents_survive PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Attacker trust penalized to 0
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_attacker_trust_penalized():
    """
    The ARGUS channel tracks trust by agent_id. The inflator's declared
    envelope is inconsistent with its movement — ARGUS penalizes it.
    Expected: attacker_final_trust == 0.0 after sustained inflation.

    This validates the trust floor property (closed decision):
    adversaries do not recover trust once penalized to zero.
    """
    print("\n--- Void Stress: Attacker Trust Penalty ---")

    result = run_void_stress_test(
        inflation_factor=8.0,
        activate_cycle=10,
        max_cycles=150,
        db_path=":memory:",
        jitter_seed=42,
    )

    print(f"  attacker_final_trust: {result.attacker_final_trust}")

    assert result.attacker_final_trust is not None, (
        "Could not read attacker trust score from engine"
    )

    # Trust should be at or near zero after sustained inflation
    assert result.attacker_final_trust <= 0.1, (
        f"Attacker trust not penalized: {result.attacker_final_trust:.3f}. "
        f"ARGUS may not be detecting inflation."
    )

    print(f"  ✓ test_void_stress_attacker_trust_penalized PASSED")


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: No false positive — honest-only simulation stays clean
# ─────────────────────────────────────────────────────────────────────────────

def test_void_stress_no_false_positive():
    """
    Without an adversarial inflator, void collapse should NOT be detected.
    Uses VoidIndex directly to simulate honest-only scenario.

    This validates that the detection mechanism has a reasonable threshold —
    normal agent movement does not trigger false alarms.
    """
    print("\n--- Void Stress: No False Positive ---")

    void = VoidIndex(VoidConfig(
        width=30.0,
        height=30.0,
        resolution=1.0,
        void_threshold_cycles=3,
        collapse_window_cycles=3,
        collapse_delta_threshold=0.20,
    ))

    # Simulate 5 honest agents with small, stable envelopes
    # Positions shift slightly each cycle (normal movement — small envelope changes)
    honest_positions = [
        (3.0, 3.0), (27.0, 3.0), (3.0, 27.0), (27.0, 27.0), (15.0, 15.0)
    ]

    false_positives = 0
    for cycle in range(80):
        # Small drift each cycle — normal agent movement
        envelopes = []
        for i, (bx, by) in enumerate(honest_positions):
            drift = (cycle * 0.05 * (-1 if i % 2 else 1)) % 2.0
            r = 1.5  # honest radius — no inflation
            envelopes.append({
                "x_min": bx + drift - r,
                "y_min": by - r,
                "x_max": bx + drift + r,
                "y_max": by + r,
            })
        void.update(envelopes, cycle)

        if cycle > 10 and void.void_collapse_detected():
            false_positives += 1
            print(f"  FALSE POSITIVE at cycle {cycle}: delta={void.collapse_delta():.3f}")

    print(f"  Total false positives (post warmup): {false_positives}")
    assert false_positives == 0, (
        f"VoidIndex produced {false_positives} false positives under honest agents. "
        f"Detection threshold may be too sensitive."
    )

    print(f"  ✓ test_void_stress_no_false_positive PASSED")
