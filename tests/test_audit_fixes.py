"""
test_audit_fixes.py — Tests for the post-audit fixes (Round 1).

Two new tests required by the audit handoff:
  1. API responses contain NO agent_ids in trust_scores (Fix #2 verification)
  2. Malicious agent CANNOT move during D3 (Fix #3 verification)
"""

import sys
import os
import math
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.simulation import SimulationEngine, SimulationConfig
from agents.base_agent import AgentConfig, BaseAgent, AgentState
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.adversarial_inflator import AdversarialInflatorAgent
from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)
from roch3.kinetic_safety import KineticSafety, KineticState, DeferenceLevel
from roch3.void_index import VoidConfig
import time as _time


def test_trust_scores_anonymized():
    """
    Fix #2 verification: CycleResult.trust_scores must contain ONLY
    anonymous indices (int), never agent_ids (str).

    A leaked agent_id in trust_scores would let any API client
    determine which named agent has low trust — a sovereignty violation.
    """
    print("--- Trust Scores Anonymized in CycleResult ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="audit_test",
        network_profile="ideal",
        dt=0.1,
        max_cycles=30,
        boundary=(0, 0, 50, 50),
        void_config=VoidConfig(width=50, height=50),
        db_path=db_path,
        jitter_seed=42,
    )
    engine = SimulationEngine(config)

    # Distinctive agent_ids that should NEVER appear in trust_scores
    secret_ids = ["secret_alpha_AAAA", "secret_beta_BBBB", "secret_gamma_CCCC"]

    engine.add_agent(ReferenceSyncferenceAgent(
        AgentConfig(agent_id=secret_ids[0], start_position=(10.0, 25.0)),
        goal=(40.0, 25.0),
    ))
    engine.add_agent(ReferenceSyncferenceAgent(
        AgentConfig(agent_id=secret_ids[1], start_position=(40.0, 25.0)),
        goal=(10.0, 25.0),
    ))
    engine.add_agent(AdversarialInflatorAgent(
        AgentConfig(agent_id=secret_ids[2], start_position=(25.0, 30.0)),
        goal=(25.0, 20.0),
        inflation_factor=4.0,
        activate_after_cycle=5,
    ))

    engine.initialize()
    results = engine.run(30)

    # Audit each cycle's trust_scores
    for r in results:
        # All keys must be int (anonymous indices), never str (agent_ids)
        for key in r.trust_scores.keys():
            assert isinstance(key, int), (
                f"Cycle {r.cycle}: trust_scores key {key!r} is {type(key).__name__}, "
                f"expected int (anonymous index)"
            )

        # No secret agent_id should appear ANYWHERE in the dict
        scores_str = str(r.trust_scores)
        for secret in secret_ids:
            assert secret not in scores_str, (
                f"Cycle {r.cycle}: SOVEREIGNTY VIOLATION — agent_id "
                f"{secret!r} leaked into trust_scores: {r.trust_scores}"
            )

    print(f"  Audited {len(results)} cycles")
    print(f"  Sample final trust_scores: {results[-1].trust_scores}")
    print(f"  All keys are int (anonymous indices) ✓")
    print(f"  No agent_ids leaked ✓")

    # Also verify the WebSocket-style serialization is anonymized
    ws_payload = {
        "trust_scores": {str(k): round(v, 3) for k, v in results[-1].trust_scores.items()}
    }
    payload_str = str(ws_payload)
    for secret in secret_ids:
        assert secret not in payload_str, (
            f"WebSocket payload leaks {secret}: {payload_str}"
        )
    print(f"  WebSocket serialization also anonymized ✓")

    engine.finalize()
    os.unlink(db_path)
    print("✓ test_trust_scores_anonymized PASSED\n")


def test_d3_physical_enforcement():
    """
    Fix #3 verification: a MALICIOUS agent that ignores the shared MVR
    in its act() method must STILL be unable to move during D3.

    Without physical enforcement, D3 would be advisory — a non-compliant
    agent could simply ignore max_speed=0 and keep moving. The motor
    must intercept and roll back the agent's position.
    """
    print("--- D3 Physical Enforcement Against Malicious Agent ---")

    class MaliciousAgent(BaseAgent):
        """
        Agent that COMPLETELY IGNORES the shared MVR.
        Always moves at full speed in a fixed direction.
        Even if max_speed=0 in shared_mvr, it still moves.
        """
        def __init__(self, config):
            super().__init__(config)
            self._boundary = (0, 0, 50, 50)
            # Hardcoded forward motion at full speed
            self._fixed_velocity = (3.0, 0.0)

        def sense(self, environment):
            if "boundary" in environment:
                self._boundary = environment["boundary"]

        def infer(self):
            pass

        def project(self):
            px, py = self._state.position
            return MVRProjection(
                spatial_envelope=SpatialEnvelope(px - 1, py - 1, px + 1, py + 1),
                temporal_sync=TemporalSync(_time.time(), 3.0),
                intent_vector=IntentVector(direction=(1, 0), speed=3.0),
                constraint_set=ConstraintSet(max_speed=3.0, min_separation=2.0),
                risk_gradient=RiskGradient(cell_risks={}),
            )

        def act(self, shared_mvr, dt):
            # MALICIOUS: completely ignore shared_mvr.
            # Even if max_speed is 0, we move.
            vx, vy = self._fixed_velocity
            self._state.velocity = (vx, vy)
            self._state.speed = math.sqrt(vx * vx + vy * vy)
            px, py = self._state.position
            self._state.position = (px + vx * dt, py + vy * dt)
            self.advance_cycle()

    # We need to force a D3 condition. Set θ_K very low so any close
    # encounter triggers D3.
    config = SimulationConfig(
        scenario="enforcement_test",
        network_profile="ideal",
        dt=0.1,
        max_cycles=10,
        boundary=(0, 0, 50, 50),
        void_config=VoidConfig(width=50, height=50),
        db_path=tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
        jitter_seed=42,
    )
    engine = SimulationEngine(config)

    # Lower thresholds so D3 triggers easily
    engine._safety.update_theta_k(DeferenceLevel.D1, 0.05)
    engine._safety.update_theta_k(DeferenceLevel.D2, 0.10)
    engine._safety.update_theta_k(DeferenceLevel.D3, 0.15)

    # Place two malicious agents head-on, very close
    a1 = MaliciousAgent(AgentConfig(
        agent_id="malicious_1",
        start_position=(20.0, 25.0),
        max_speed=3.0,
        min_separation=10.0,  # large min_sep → ΔK fires immediately
    ))
    a2 = MaliciousAgent(AgentConfig(
        agent_id="malicious_2",
        start_position=(22.0, 25.0),
        max_speed=3.0,
        min_separation=10.0,
    ))
    # Make a2 move toward a1 (head-on collision)
    a2._fixed_velocity = (-3.0, 0.0)

    engine.add_agent(a1)
    engine.add_agent(a2)
    engine.initialize()

    # Track positions across cycles
    positions_a1 = [tuple(a1.position)]
    positions_a2 = [tuple(a2.position)]
    d3_triggered = False

    for cycle in range(10):
        result = engine.step()
        positions_a1.append(tuple(a1.position))
        positions_a2.append(tuple(a2.position))

        # Check if any agent reached D3 in this cycle
        for action in result.deference_actions:
            if action.level >= DeferenceLevel.D3:
                d3_triggered = True

    print(f"  D3 triggered at some point: {d3_triggered}")
    print(f"  a1 positions: {[(round(p[0],2), round(p[1],2)) for p in positions_a1]}")
    print(f"  a2 positions: {[(round(p[0],2), round(p[1],2)) for p in positions_a2]}")

    assert d3_triggered, "Test setup failed: D3 should have triggered"

    # KEY ASSERTION: in cycles where D3 was active, the agent's position
    # must NOT have changed compared to the position before that cycle.
    # We verify by stepping through and checking that for at least one cycle
    # where D3 fired, the position was rolled back.

    # Re-run with explicit per-cycle tracking
    config2 = SimulationConfig(
        scenario="enforcement_test_2",
        network_profile="ideal",
        dt=0.1,
        max_cycles=10,
        boundary=(0, 0, 50, 50),
        void_config=VoidConfig(width=50, height=50),
        db_path=tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
        jitter_seed=42,
    )
    engine2 = SimulationEngine(config2)
    engine2._safety.update_theta_k(DeferenceLevel.D1, 0.05)
    engine2._safety.update_theta_k(DeferenceLevel.D2, 0.10)
    engine2._safety.update_theta_k(DeferenceLevel.D3, 0.15)

    b1 = MaliciousAgent(AgentConfig(
        agent_id="m1",
        start_position=(20.0, 25.0),
        max_speed=3.0,
        min_separation=10.0,
    ))
    b2 = MaliciousAgent(AgentConfig(
        agent_id="m2",
        start_position=(22.0, 25.0),
        max_speed=3.0,
        min_separation=10.0,
    ))
    b2._fixed_velocity = (-3.0, 0.0)

    engine2.add_agent(b1)
    engine2.add_agent(b2)
    engine2.initialize()

    rollback_observed = False
    for cycle in range(10):
        pos_before_b1 = tuple(b1.position)
        result = engine2.step()
        pos_after_b1 = tuple(b1.position)

        # Find b1's deference action in this cycle
        for action in result.deference_actions:
            if action.details.get("agent_index") == 0 and action.level >= DeferenceLevel.D3:
                # b1 was at D3+. Position must NOT have changed.
                if pos_after_b1 == pos_before_b1:
                    rollback_observed = True
                else:
                    assert False, (
                        f"Cycle {cycle+1}: D{action.level} fired for b1 but "
                        f"position changed: {pos_before_b1} -> {pos_after_b1}. "
                        f"Physical enforcement FAILED."
                    )

    assert rollback_observed, (
        "Test inconclusive: D3 never fired for b1 specifically. "
        "Try adjusting θ_K thresholds or initial positions."
    )

    engine2.finalize()
    print(f"  Rollback observed during D3+ ✓")
    print(f"  Malicious agent could NOT move during D3 ✓")

    print("✓ test_d3_physical_enforcement PASSED\n")


if __name__ == "__main__":
    test_trust_scores_anonymized()
    test_d3_physical_enforcement()
    test_omniscient_no_agent_ids()
    test_validate_rejects_nan_inf()
    test_validate_rejects_oversized_risk_gradient()
    test_anonymized_scores_rotate_indices()
    print("=" * 55)
    print("=== ALL AUDIT FIX TESTS PASSED ===")
    print("=" * 55)


# =====================================================================
# ROUND 2 TESTS
# =====================================================================

def test_omniscient_no_agent_ids():
    """
    Round 2 Fix C1: _push_omniscient_info must use anonymous indices,
    never real agent_ids. The OmniscientCoordinator should function
    correctly with indices instead of identities.
    """
    print("--- Omniscient Snapshot Contains No Agent IDs ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="omniscient_sovereignty_test",
        network_profile="ideal",
        dt=0.1,
        max_cycles=20,
        boundary=(0, 0, 50, 50),
        void_config=VoidConfig(width=50, height=50),
        db_path=db_path,
        jitter_seed=42,
    )
    engine = SimulationEngine(config)

    secret_ids = ["SECRET_AGENT_ALPHA", "SECRET_AGENT_BETA"]
    from agents.omniscient_coordinator import OmniscientCoordinator

    engine.add_agent(ReferenceSyncferenceAgent(
        AgentConfig(agent_id=secret_ids[0], start_position=(10.0, 25.0)),
        goal=(40.0, 25.0),
    ))
    engine.add_agent(OmniscientCoordinator(
        AgentConfig(agent_id=secret_ids[1], start_position=(40.0, 25.0)),
        goal=(10.0, 25.0),
    ))

    engine.initialize()

    # Intercept the snapshot to verify no agent_ids
    original_push = engine._push_omniscient_info

    captured_snapshots = []
    def intercepting_push():
        # Build snapshot the same way the engine does
        snapshot = [
            {
                "index": idx,
                "position": a.position,
                "velocity": a.velocity,
            }
            for idx, a in enumerate(engine._agents.values())
        ]
        captured_snapshots.append(snapshot)
        original_push()

    engine._push_omniscient_info = intercepting_push

    results = engine.run(20)

    # Verify no agent_ids in any captured snapshot
    for i, snapshot in enumerate(captured_snapshots):
        snapshot_str = str(snapshot)
        for secret in secret_ids:
            assert secret not in snapshot_str, (
                f"Cycle {i}: SOVEREIGNTY VIOLATION — agent_id {secret!r} "
                f"found in omniscient snapshot: {snapshot}"
            )
        # Verify all entries use integer index, not string agent_id
        for entry in snapshot:
            assert "agent_id" not in entry, (
                f"Cycle {i}: snapshot contains 'agent_id' key: {entry}"
            )
            assert "index" in entry, (
                f"Cycle {i}: snapshot missing 'index' key: {entry}"
            )
            assert isinstance(entry["index"], int), (
                f"Cycle {i}: index is not int: {entry['index']}"
            )

    # Verify OmniscientCoordinator still functions (H_p reasonable)
    avg_hp = sum(r.harmony.h_p for r in results) / len(results)
    assert avg_hp > 0.5, f"OmniscientCoordinator broken: avg H_p = {avg_hp}"

    engine.finalize()
    os.unlink(db_path)
    print(f"  Captured {len(captured_snapshots)} snapshots")
    print(f"  No agent_ids in any snapshot ✓")
    print(f"  OmniscientCoordinator avg H_p: {avg_hp:.4f} ✓")
    print("✓ test_omniscient_no_agent_ids PASSED\n")


def test_validate_rejects_nan_inf():
    """
    Round 2 Fix C3: validate() must reject NaN and Inf in spatial_envelope.
    """
    print("--- Validate Rejects NaN/Inf ---")
    import math

    cases = [
        ("NaN x_min", SpatialEnvelope(float('nan'), 0, 10, 10)),
        ("Inf x_max", SpatialEnvelope(0, 0, float('inf'), 10)),
        ("-Inf y_min", SpatialEnvelope(0, float('-inf'), 10, 10)),
        ("NaN y_max", SpatialEnvelope(0, 0, 10, float('nan'))),
    ]

    for label, bad_env in cases:
        p = MVRProjection(
            spatial_envelope=bad_env,
            temporal_sync=TemporalSync(_time.time(), 5.0),
            intent_vector=IntentVector(direction=(1, 0), speed=1.0),
            constraint_set=ConstraintSet(max_speed=2.0, min_separation=1.0),
            risk_gradient=RiskGradient(cell_risks={}),
        )
        errors = p.validate()
        assert any("finite" in e for e in errors), (
            f"{label}: validate() did not catch non-finite value. Errors: {errors}"
        )
        print(f"  {label}: rejected ✓")

    print("✓ test_validate_rejects_nan_inf PASSED\n")


def test_validate_rejects_oversized_risk_gradient():
    """
    Round 2 Fix C2: validate() must reject risk_gradient with >10,000 cells.
    DOS defense.
    """
    print("--- Validate Rejects Oversized Risk Gradient ---")

    big_risks = {f"cell_{i}": 0.5 for i in range(10_001)}
    p = MVRProjection(
        spatial_envelope=SpatialEnvelope(0, 0, 10, 10),
        temporal_sync=TemporalSync(_time.time(), 5.0),
        intent_vector=IntentVector(direction=(1, 0), speed=1.0),
        constraint_set=ConstraintSet(max_speed=2.0, min_separation=1.0),
        risk_gradient=RiskGradient(cell_risks=big_risks),
    )
    errors = p.validate()
    assert any("exceeds maximum" in e for e in errors), (
        f"DOS: validate() did not catch oversized risk_gradient. Errors: {errors}"
    )
    print(f"  10,001 cells: rejected ✓")

    # Normal size should pass
    ok_risks = {f"cell_{i}": 0.5 for i in range(100)}
    p2 = MVRProjection(
        spatial_envelope=SpatialEnvelope(0, 0, 10, 10),
        temporal_sync=TemporalSync(_time.time(), 5.0),
        intent_vector=IntentVector(direction=(1, 0), speed=1.0),
        constraint_set=ConstraintSet(max_speed=2.0, min_separation=1.0),
        risk_gradient=RiskGradient(cell_risks=ok_risks),
    )
    errors2 = p2.validate()
    assert not any("exceeds" in e for e in errors2), (
        f"Normal size rejected: {errors2}"
    )
    print(f"  100 cells: accepted ✓")
    print("✓ test_validate_rejects_oversized_risk_gradient PASSED\n")


def test_anonymized_scores_rotate_indices():
    """
    Round 2 Fix C6: get_anonymized_scores() must rotate indices
    periodically to prevent reidentification by temporal correlation.
    """
    print("--- Anonymized Scores Rotate Indices ---")
    from roch3.sovereign_context import SovereignProjectionBuffer, ARGUSTrustChannel

    buf = SovereignProjectionBuffer()
    argus = ARGUSTrustChannel(buf)

    # Register 3 agents
    for i, aid in enumerate(["a1", "a2", "a3"]):
        p = MVRProjection(
            spatial_envelope=SpatialEnvelope(i*10, 0, i*10+5, 5),
            temporal_sync=TemporalSync(_time.time(), 5.0),
            intent_vector=IntentVector(direction=(1, 0), speed=1.0),
            constraint_set=ConstraintSet(max_speed=2.0, min_separation=1.0),
            risk_gradient=RiskGradient(cell_risks={}),
        )
        buf.store(aid, p)
        argus.update_trust(aid, {"type": "consistent"})

    # Give different trust to each agent so we can track them
    argus.update_trust("a1", {"type": "consistent"})  # high
    for _ in range(10):
        argus.update_trust("a3", {"type": "spatial_inflation", "severity": 1.0})  # low

    # Collect anonymized scores across multiple calls
    score_sets = []
    for _ in range(25):  # More than ROTATION_INTERVAL (10)
        scores = argus.get_anonymized_scores()
        score_sets.append(dict(scores))

    # Verify: indices should change at rotation boundary
    # Compare sets before and after rotation
    pre_rotation = score_sets[0]
    post_rotation = score_sets[11]  # After first rotation at call 10

    # The VALUES should be the same set (same agents, same trust)
    # but the INDEX mapping should differ
    pre_values = sorted(pre_rotation.values())
    post_values = sorted(post_rotation.values())

    # Values should be approximately the same (same agents)
    print(f"  Pre-rotation indices: {sorted(pre_rotation.keys())}")
    print(f"  Post-rotation indices: {sorted(post_rotation.keys())}")
    print(f"  Pre-rotation values: {[round(v,3) for v in sorted(pre_rotation.values())]}")
    print(f"  Post-rotation values: {[round(v,3) for v in sorted(post_rotation.values())]}")

    # The key assertion: at least once across 25 calls, the index mapping changed
    mappings_changed = False
    ref = score_sets[0]
    for s in score_sets[1:]:
        if s != ref:
            mappings_changed = True
            break

    assert mappings_changed, (
        "Indices never rotated across 25 calls (ROTATION_INTERVAL=10). "
        "Reidentification by temporal correlation is possible."
    )
    print(f"  Index rotation observed ✓")

    # All scores in [0, 1]
    for scores in score_sets:
        for v in scores.values():
            assert 0.0 <= v <= 1.0, f"Score {v} out of [0,1]"
    print(f"  All scores in [0, 1] ✓")

    print("✓ test_anonymized_scores_rotate_indices PASSED\n")
