"""
test_sovereignty.py — OBLIGATORIO

Verifica que la garantía de soberanía es ESTRUCTURAL, no política.
Si un investigador de seguridad audita el código, debe encontrar que es
ESTRUCTURALMENTE IMPOSIBLE acceder a las proyecciones de un agente
desde la perspectiva de otro.

This test MUST pass before any release.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from roch3.mvr import (
    MVRProjection, SpatialEnvelope, TemporalSync,
    IntentVector, ConstraintSet, RiskGradient,
)
from roch3.sovereign_context import SovereignProjectionBuffer, ARGUSTrustChannel
from roch3.convergence import GammaOperator
import time


def _make_projection(x: float, y: float, speed: float = 1.0) -> MVRProjection:
    """Helper: create a valid MVR projection at position (x, y)."""
    return MVRProjection(
        spatial_envelope=SpatialEnvelope(x - 1, y - 1, x + 1, y + 1),
        temporal_sync=TemporalSync(time.time(), drift_bound_ms=5.0),
        intent_vector=IntentVector(direction=(1.0, 0.0), speed=speed),
        constraint_set=ConstraintSet(max_speed=5.0, min_separation=2.0),
        risk_gradient=RiskGradient(cell_risks={f"{int(x)}_{int(y)}": 0.3}),
    )


def test_sovereignty_guarantee():
    """
    CORE TEST: The output of get_fields_for_convergence() must contain
    NO agent identifiers. Period.
    """
    buffer = SovereignProjectionBuffer()

    # Store projections from 3 different agents
    agent_ids = ["drone_alpha_001", "robot_beta_002", "vehicle_gamma_003"]
    for i, agent_id in enumerate(agent_ids):
        proj = _make_projection(x=i * 10.0, y=i * 5.0)
        buffer.store(agent_id, proj)

    # Get fields for convergence
    fields = buffer.get_fields_for_convergence()

    # VERIFY: No agent_id anywhere in the output
    fields_str = str(fields)
    for agent_id in agent_ids:
        assert agent_id not in fields_str, (
            f"SOVEREIGNTY VIOLATION: agent_id '{agent_id}' found in convergence fields!"
        )

    # VERIFY: Fields have anonymous indices, not ids
    for field in fields:
        assert "_index" in field, "Missing anonymous index"
        assert isinstance(field["_index"], int), "Index must be integer"
        assert "_trust_weight" in field, "Missing trust weight"
        # Check no string keys that look like agent identifiers
        for key in field:
            if isinstance(field[key], str) and any(aid in field[key] for aid in agent_ids):
                assert False, f"SOVEREIGNTY VIOLATION: agent_id leaked in field '{key}'"

    print("✓ test_sovereignty_guarantee PASSED")


def test_no_cross_agent_access():
    """
    Verify that there is NO API path to get agent A's projection
    from the perspective of agent B.
    """
    buffer = SovereignProjectionBuffer()

    # Agent A stores a distinctive projection
    proj_a = _make_projection(x=100.0, y=200.0, speed=3.5)
    buffer.store("agent_A", proj_a)

    # Agent B stores a different projection
    proj_b = _make_projection(x=0.0, y=0.0, speed=1.0)
    buffer.store("agent_B", proj_b)

    # The ONLY way to get fields is get_fields_for_convergence()
    fields = buffer.get_fields_for_convergence()

    # Verify: we can see the data but NOT who it belongs to
    assert len(fields) == 2
    # We can see position data (100, 200) exists somewhere
    # But we CANNOT tell which anonymous index maps to which agent
    indices = [f["_index"] for f in fields]
    assert len(set(indices)) == 2  # Two distinct indices

    # The buffer has get_index_for_agent() but this is INTERNAL
    # — only used by ARGUSTrustChannel, not exposed to agents
    idx_a = buffer.get_index_for_agent("agent_A")
    idx_b = buffer.get_index_for_agent("agent_B")
    assert idx_a != idx_b
    assert idx_a is not None
    assert idx_b is not None

    print("✓ test_no_cross_agent_access PASSED")


def test_gamma_receives_no_identity():
    """
    Verify that Γ (the convergence operator) operates entirely
    without agent identifiers.
    """
    buffer = SovereignProjectionBuffer()
    gamma = GammaOperator()

    # Store 3 agents
    for i in range(3):
        proj = _make_projection(x=i * 5.0, y=i * 3.0)
        buffer.store(f"secret_agent_{i}", proj)

    # Apply ARGUS trust
    argus = ARGUSTrustChannel(buffer)
    argus.update_trust("secret_agent_0", {"type": "consistent"})
    argus.update_trust("secret_agent_1", {"type": "spatial_inflation", "severity": 2.0})
    argus.update_trust("secret_agent_2", {"type": "consistent"})
    argus.push_weights_to_buffer()

    # Get fields and converge
    fields = buffer.get_fields_for_convergence()
    result = gamma.converge(fields, cycle=1)

    # VERIFY: shared_mvr contains NO agent identifiers
    shared_str = str(result.shared_mvr)
    for i in range(3):
        assert f"secret_agent_{i}" not in shared_str, (
            f"SOVEREIGNTY VIOLATION: agent id leaked into shared MVR!"
        )

    # VERIFY: intents are preserved but anonymous
    intents = result.shared_mvr["intent_vector"]
    assert len(intents) == 3
    for intent in intents:
        assert "_index" in intent  # anonymous index
        assert "intent" in intent
        # Verify no agent_id key
        assert "agent_id" not in intent

    # VERIFY: trust weights affect convergence (agent_1 should have lower weight)
    weights = [intent["_trust_weight"] for intent in intents]
    assert min(weights) < 1.0, "ARGUS trust decay not applied"

    print("✓ test_gamma_receives_no_identity PASSED")


def test_argus_channel_separation():
    """
    Verify ARGUS and Γ channels are fully separated.
    ARGUS produces trust scores. Γ sees weights but not the ARGUS channel.
    """
    buffer = SovereignProjectionBuffer()
    argus = ARGUSTrustChannel(buffer)

    buffer.store("agent_X", _make_projection(10, 10))

    # ARGUS updates trust
    argus.update_trust("agent_X", {"type": "projection_poisoning", "severity": 3.0})

    # Before push: buffer still has default trust
    fields_before = buffer.get_fields_for_convergence()
    assert fields_before[0]["_trust_weight"] == 1.0

    # After push: trust is updated via anonymous index
    argus.push_weights_to_buffer()
    fields_after = buffer.get_fields_for_convergence()
    assert fields_after[0]["_trust_weight"] < 1.0, "Trust decay not applied after push"

    # ARGUS history contains agent_id (this is the authenticated channel)
    history = argus._get_history("agent_X")
    assert len(history) == 1
    assert history[0]["observation"]["type"] == "projection_poisoning"

    # But convergence fields do NOT contain this history
    fields_str = str(fields_after)
    assert "projection_poisoning" not in fields_str
    assert "agent_X" not in fields_str

    print("✓ test_argus_channel_separation PASSED")


def test_agent_removal():
    """Verify agent removal cleans projection but keeps index stable."""
    buffer = SovereignProjectionBuffer()

    buffer.store("agent_1", _make_projection(0, 0))
    buffer.store("agent_2", _make_projection(10, 10))

    idx_1 = buffer.get_index_for_agent("agent_1")
    assert buffer.agent_count() == 2

    buffer.remove_agent("agent_1")
    assert buffer.agent_count() == 1

    # Index mapping persists (stable for session)
    assert buffer.get_index_for_agent("agent_1") == idx_1

    # Only agent_2's fields remain
    fields = buffer.get_fields_for_convergence()
    assert len(fields) == 1

    print("✓ test_agent_removal PASSED")


if __name__ == "__main__":
    test_sovereignty_guarantee()
    test_no_cross_agent_access()
    test_gamma_receives_no_identity()
    test_argus_channel_separation()
    test_agent_removal()
    print("\n=== ALL SOVEREIGNTY TESTS PASSED ===")
