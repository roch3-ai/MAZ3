"""
test_paso0_integration.py

End-to-end integration test of core protocol components.
  MVR → SovereignProjectionBuffer → ARGUS → Γ → Harmony → VoidIndex → FlightRecorder

Validates MVR, convergence, harmony, safety, void, and network jitter.
"""

import sys
import os
import time
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)
from roch3.sovereign_context import SovereignProjectionBuffer, ARGUSTrustChannel
from roch3.convergence import GammaOperator
from roch3.harmony import compute_harmony_index, THRESHOLD_HEALTHY
from roch3.void_index import VoidIndex, VoidConfig
from roch3.network_jitter import NetworkJitterModel, PROFILES
from roch3.kinetic_safety import KineticSafety, KineticState, DeferenceLevel
from api.models import FlightRecorder


def _make_proj(x, y, speed=1.0, risk_val=0.2):
    return MVRProjection(
        spatial_envelope=SpatialEnvelope(x - 1, y - 1, x + 1, y + 1),
        temporal_sync=TemporalSync(time.time(), drift_bound_ms=3.0),
        intent_vector=IntentVector(direction=(1.0, 0.0), speed=speed),
        constraint_set=ConstraintSet(max_speed=5.0, min_separation=2.0),
        risk_gradient=RiskGradient(cell_risks={f"{int(x)}_{int(y)}": risk_val}),
    )


def test_full_pipeline():
    """Complete Syncference cycle: project → converge → measure → record."""
    print("--- Full Pipeline Test ---")

    # 1. Create components
    buffer = SovereignProjectionBuffer()
    argus = ARGUSTrustChannel(buffer)
    gamma = GammaOperator()
    void = VoidIndex(VoidConfig(width=30, height=30, resolution=1.0))
    safety = KineticSafety()

    # 2. Agents project MVR
    agents = {
        "drone_A": _make_proj(5, 5, speed=2.0, risk_val=0.1),
        "drone_B": _make_proj(15, 15, speed=1.5, risk_val=0.3),
        "robot_C": _make_proj(25, 10, speed=0.5, risk_val=0.5),
    }

    for agent_id, proj in agents.items():
        buffer.store(agent_id, proj)
        argus.update_trust(agent_id, {"type": "consistent"})

    # 3. ARGUS pushes trust weights
    argus.push_weights_to_buffer()

    # 4. Γ converges
    fields = buffer.get_fields_for_convergence()
    assert len(fields) == 3, f"Expected 3 fields, got {len(fields)}"
    result = gamma.converge(fields, cycle=1)
    assert result.agent_count == 3
    assert result.convergence_time_ms >= 0
    print(f"  Γ converged in {result.convergence_time_ms:.3f}ms")

    # 5. Harmony Index
    harmony = compute_harmony_index(fields, cycle=1)
    print(f"  H_p = {harmony.h_p:.4f} ({harmony.status})")
    assert 0 <= harmony.h_p <= 1

    # 6. VoidIndex update
    envelopes = [f["spatial_envelope"] for f in fields]
    void.update(envelopes, cycle_number=1)
    snap = void.get_snapshot()
    print(f"  Void: {snap['void_zones_count']} zones, {snap['total_void_volume']:.1f}m²")

    # 7. Kinetic Safety
    ks_a = KineticState(position=(5, 5), velocity=(2, 0), timestamp=time.time())
    ks_b = KineticState(position=(15, 15), velocity=(-1, -1), timestamp=time.time())
    action = safety.evaluate(0, ks_a, [ks_b])
    print(f"  ΔK = {action.delta_k:.4f}, level = D{action.level}")

    # 8. Flight recorder
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    recorder = FlightRecorder(db_path)
    recorder.initialize()

    session_id = recorder.create_session("bottleneck", "industrial_ethernet", 3)
    recorder.record_snapshot(
        session_id=session_id,
        cycle_number=1,
        h_p=harmony.h_p,
        convergence_time_ms=result.convergence_time_ms,
        agent_projections=[f for f in fields],  # anonymous fields only
        shared_mvr=result.shared_mvr,
    )
    recorder.record_void_snapshot(
        session_id=session_id,
        cycle_number=1,
        total_void_volume=snap["total_void_volume"],
        void_zones_count=snap["void_zones_count"],
    )

    summary = recorder.get_session_summary(session_id)
    assert summary is not None
    assert summary["snapshot_count"] == 1
    print(f"  FlightRecorder: session {session_id[:8]}... saved")

    recorder.close()
    os.unlink(db_path)

    print("✓ test_full_pipeline PASSED\n")


def test_network_jitter_profiles():
    """Verify all 4 network profiles produce statistically valid results."""
    print("--- Network Jitter Profiles ---")
    for profile_name in PROFILES:
        model = NetworkJitterModel(profile_name, seed=42)
        stats = model.stats(n_samples=5000)

        expected_mean = PROFILES[profile_name]["latency_mean_ms"]
        actual_mean = stats["latency_mean"]
        tolerance = expected_mean * 0.15  # 15% tolerance

        assert abs(actual_mean - expected_mean) < tolerance, (
            f"{profile_name}: mean {actual_mean:.2f} too far from expected {expected_mean:.2f}"
        )

        print(
            f"  {profile_name:25s}: "
            f"mean={stats['latency_mean']:8.2f}ms "
            f"p95={stats['latency_p95']:8.2f}ms "
            f"loss={stats['packet_loss_observed']:.4f}"
        )

    print("✓ test_network_jitter_profiles PASSED\n")


def test_jitter_lognormal_sigma():
    """
    Verify the lognormal sigma bug fix.
    The corrected formula should produce mean ≈ configured mean.
    """
    print("--- Lognormal Sigma Bug Fix ---")
    model = NetworkJitterModel("wifi_warehouse", seed=123)
    stats = model.stats(n_samples=20000)

    configured_mean = 12.0
    actual_mean = stats["latency_mean"]
    # With correct sigma, mean should be within 5% of configured
    assert abs(actual_mean - configured_mean) / configured_mean < 0.05, (
        f"Lognormal mean {actual_mean:.2f} deviates >5% from {configured_mean}"
    )
    print(f"  wifi_warehouse mean: configured={configured_mean}, actual={actual_mean:.2f}")
    print("✓ test_jitter_lognormal_sigma PASSED\n")


def test_void_collapse_detection():
    """Verify void collapse attack detection."""
    print("--- Void Collapse Detection ---")
    void = VoidIndex(VoidConfig(
        width=20, height=20, resolution=1.0,
        void_threshold_cycles=2,
        collapse_window_cycles=2,
        collapse_delta_threshold=0.15,
    ))

    # First few cycles: no agents → everything becomes void
    for cycle in range(5):
        void.update([], cycle)

    void_before = void.total_void_volume()
    print(f"  Void volume (no agents): {void_before:.0f}m²")
    assert void_before > 0

    # Sudden massive claim (simulating void collapse attack)
    massive_claim = [{"x_min": 0, "y_min": 0, "x_max": 18, "y_max": 18}]
    void.update(massive_claim, 5)

    # Check immediately after the collapse happens
    collapsed = void.void_collapse_detected()
    print(f"  Void collapse detected: {collapsed}")
    assert collapsed, "Failed to detect void collapse attack"

    print("✓ test_void_collapse_detection PASSED\n")


def test_deference_escalation():
    """Verify D0→D4 escalation under increasing kinetic risk."""
    print("--- Deference Escalation ---")
    safety = KineticSafety(min_separation=5.0)

    t = time.time()

    # Two agents far apart → D0
    a = KineticState(position=(0, 0), velocity=(0, 0), timestamp=t)
    b = KineticState(position=(50, 50), velocity=(0, 0), timestamp=t)
    action = safety.evaluate(0, a, [b])
    print(f"  Far apart:     D{action.level} (ΔK={action.delta_k:.3f})")
    assert action.level == DeferenceLevel.D0

    # Approaching at moderate speed
    a2 = KineticState(position=(10, 0), velocity=(3, 0), timestamp=t + 1)
    b2 = KineticState(position=(18, 0), velocity=(-2, 0), timestamp=t + 1)
    action2 = safety.evaluate(1, a2, [b2])
    print(f"  Approaching:   D{action2.level} (ΔK={action2.delta_k:.3f})")

    # Head-on collision course
    a3 = KineticState(position=(8, 0), velocity=(5, 0), timestamp=t + 2)
    b3 = KineticState(position=(12, 0), velocity=(-5, 0), timestamp=t + 2)
    action3 = safety.evaluate(2, a3, [b3])
    print(f"  Head-on:       D{action3.level} (ΔK={action3.delta_k:.3f})")
    assert action3.level >= DeferenceLevel.D1, "Head-on should escalate"

    print("✓ test_deference_escalation PASSED\n")


def test_mvr_validation():
    """Verify MVR validation catches bad projections."""
    print("--- MVR Validation ---")

    # Valid
    good = _make_proj(5, 5)
    assert good.validate() == [], f"Valid projection failed: {good.validate()}"

    # Degenerate envelope
    bad_env = MVRProjection(
        spatial_envelope=SpatialEnvelope(10, 10, 5, 5),  # min > max
        temporal_sync=TemporalSync(time.time(), 3.0),
        intent_vector=IntentVector((1, 0), 1.0),
        constraint_set=ConstraintSet(5.0, 2.0),
        risk_gradient=RiskGradient(),
    )
    errors = bad_env.validate()
    assert len(errors) > 0, "Should reject degenerate envelope"
    print(f"  Degenerate envelope: {len(errors)} error(s) caught")

    # Negative speed
    bad_speed = _make_proj(5, 5)
    bad_speed.intent_vector.speed = -1.0
    errors = bad_speed.validate()
    assert len(errors) > 0, "Should reject negative speed"
    print(f"  Negative speed: {len(errors)} error(s) caught")

    # Bad risk value
    bad_risk = _make_proj(5, 5)
    bad_risk.risk_gradient.cell_risks["cell_x"] = 1.5
    errors = bad_risk.validate()
    assert len(errors) > 0, "Should reject risk > 1.0"
    print(f"  Bad risk: {len(errors)} error(s) caught")

    print("✓ test_mvr_validation PASSED\n")


def test_buffer_rejects_invalid_projection():
    """SovereignProjectionBuffer should reject invalid MVR."""
    print("--- Buffer Validation ---")
    buffer = SovereignProjectionBuffer()

    bad = MVRProjection(
        spatial_envelope=SpatialEnvelope(10, 10, 5, 5),
        temporal_sync=TemporalSync(time.time(), 3.0),
        intent_vector=IntentVector((1, 0), 1.0),
        constraint_set=ConstraintSet(5.0, 2.0),
        risk_gradient=RiskGradient(),
    )

    try:
        buffer.store("bad_agent", bad)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Rejected: {e}")

    print("✓ test_buffer_rejects_invalid_projection PASSED\n")


if __name__ == "__main__":
    test_full_pipeline()
    test_network_jitter_profiles()
    test_jitter_lognormal_sigma()
    test_void_collapse_detection()
    test_deference_escalation()
    test_mvr_validation()
    test_buffer_rejects_invalid_projection()
    print("=" * 50)
    print("=== ALL PASO 0 INTEGRATION TESTS PASSED ===")
    print("=" * 50)
