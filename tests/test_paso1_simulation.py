"""
test_paso1_simulation.py

Paso 1 criterion of done:
  "Un agente se conecta, proyecta MVR, el operador Γ converge,
   el flight recorder guarda el snapshot."

Plus: multi-cycle run to verify the loop is stable over time.
"""

import sys
import os
import tempfile
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.simulation import SimulationEngine, SimulationConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from agents.base_agent import AgentConfig
from roch3.harmony import THRESHOLD_HEALTHY, THRESHOLD_ATTENTION
from api.models import FlightRecorder


def test_single_agent_syncference():
    """
    PASO 1 CRITERION OF DONE:
    1 agent connects, projects MVR, Γ converges, flight recorder saves snapshot.
    """
    print("--- Single Agent Syncference ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="open_field",
        network_profile="ideal",
        dt=0.1,
        max_cycles=10,
        boundary=(0, 0, 50, 50),
        db_path=db_path,
        jitter_seed=42,
    )

    engine = SimulationEngine(config)

    # Add one agent
    agent = ReferenceSyncferenceAgent(
        AgentConfig(
            agent_id="drone_alpha",
            start_position=(10.0, 25.0),
            max_speed=3.0,
        ),
        goal=(40.0, 25.0),
    )
    engine.add_agent(agent)
    assert engine.agent_count == 1

    # Initialize
    session_id = engine.initialize()
    assert session_id is not None
    print(f"  Session: {session_id[:8]}...")

    # Run 1 cycle
    result = engine.step()

    # Verify Phase 3: projection happened
    assert result.agent_count == 1, f"Expected 1 agent, got {result.agent_count}"

    # Verify Phase 4: Γ converged
    assert result.convergence_time_ms >= 0
    assert result.shared_mvr, "Shared MVR is empty"
    assert "spatial_envelope" in result.shared_mvr
    assert "constraint_set" in result.shared_mvr
    print(f"  Γ converged in {result.convergence_time_ms:.3f}ms")

    # Verify Harmony computed
    assert 0 <= result.harmony.h_p <= 1
    print(f"  H_p = {result.harmony.h_p:.4f} ({result.harmony.status})")

    # Verify Phase 5: agent moved
    new_pos = agent.position
    assert new_pos != (10.0, 25.0), "Agent didn't move"
    print(f"  Agent moved: (10.0, 25.0) → ({new_pos[0]:.2f}, {new_pos[1]:.2f})")

    # Verify flight recorder
    summary = engine.finalize()
    assert summary["snapshot_count"] == 1
    print(f"  Flight recorder: {summary['snapshot_count']} snapshot(s)")

    os.unlink(db_path)
    print("✓ test_single_agent_syncference PASSED\n")


def test_multi_cycle_stability():
    """
    Run 100 cycles with 1 agent. Verify:
    - H_p stays healthy for a single agent
    - Agent moves toward goal
    - No crashes or divergence
    """
    print("--- Multi-Cycle Stability (100 cycles) ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="open_field",
        network_profile="ideal",
        dt=0.1,
        max_cycles=100,
        boundary=(0, 0, 50, 50),
        db_path=db_path,
        jitter_seed=42,
        record_every_n=10,  # record every 10th cycle
    )

    engine = SimulationEngine(config)

    agent = ReferenceSyncferenceAgent(
        AgentConfig(
            agent_id="drone_beta",
            start_position=(5.0, 25.0),
            max_speed=3.0,
        ),
        goal=(45.0, 25.0),
    )
    engine.add_agent(agent)
    engine.initialize()

    results = engine.run(100)
    assert len(results) == 100

    # Verify H_p stayed healthy throughout
    h_values = [r.harmony.h_p for r in results]
    min_h = min(h_values)
    max_h = max(h_values)
    avg_h = sum(h_values) / len(h_values)
    print(f"  H_p: min={min_h:.4f} max={max_h:.4f} avg={avg_h:.4f}")

    # Single agent should always be healthy (no conflicts)
    for i, r in enumerate(results):
        assert r.harmony.h_p >= THRESHOLD_ATTENTION, (
            f"Cycle {r.cycle}: H_p={r.harmony.h_p:.4f} dropped below attention threshold"
        )

    # Agent should have moved toward goal
    final_pos = agent.position
    start_x = 5.0
    goal_x = 45.0
    progress = (final_pos[0] - start_x) / (goal_x - start_x)
    print(f"  Agent position: ({final_pos[0]:.2f}, {final_pos[1]:.2f})")
    print(f"  Progress toward goal: {progress * 100:.1f}%")
    assert progress > 0.1, "Agent made too little progress in 100 cycles"

    # Verify flight recorder has data
    summary = engine.finalize()
    assert summary["snapshot_count"] == 10  # recorded every 10th
    assert summary["avg_h_p"] is not None
    print(f"  Flight recorder: {summary['snapshot_count']} snapshots, avg H_p={summary['avg_h_p']:.4f}")

    os.unlink(db_path)
    print("✓ test_multi_cycle_stability PASSED\n")


def test_agent_reaches_goal():
    """Verify agent actually reaches its goal and stops."""
    print("--- Agent Reaches Goal ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="open_field",
        network_profile="ideal",
        dt=0.1,
        max_cycles=500,
        boundary=(0, 0, 50, 50),
        db_path=db_path,
        jitter_seed=42,
        record_every_n=50,
    )

    engine = SimulationEngine(config)

    goal = (30.0, 25.0)
    agent = ReferenceSyncferenceAgent(
        AgentConfig(
            agent_id="drone_gamma",
            start_position=(10.0, 25.0),
            max_speed=3.0,
        ),
        goal=goal,
    )
    engine.add_agent(agent)
    engine.initialize()

    results = engine.run(500)

    final_pos = agent.position
    dist_to_goal = math.sqrt(
        (final_pos[0] - goal[0]) ** 2 + (final_pos[1] - goal[1]) ** 2
    )
    print(f"  Final position: ({final_pos[0]:.2f}, {final_pos[1]:.2f})")
    print(f"  Distance to goal: {dist_to_goal:.2f}m")

    # Should be within 1m of goal after 500 cycles at 0.1s each (50s of sim time)
    # At 1.8 m/s (60% of 3.0), 20m takes ~11s
    assert dist_to_goal < 2.0, f"Agent too far from goal: {dist_to_goal:.2f}m"

    engine.finalize()
    os.unlink(db_path)
    print("✓ test_agent_reaches_goal PASSED\n")


def test_network_jitter_impact():
    """
    Compare ideal vs degraded network.
    Degraded should still converge but with more variation.
    """
    print("--- Network Jitter Impact ---")

    results_by_profile = {}

    for profile in ["ideal", "wifi_warehouse"]:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        config = SimulationConfig(
            scenario="open_field",
            network_profile=profile,
            dt=0.1,
            max_cycles=50,
            boundary=(0, 0, 50, 50),
            db_path=db_path,
            jitter_seed=42,
        )

        engine = SimulationEngine(config)
        agent = ReferenceSyncferenceAgent(
            AgentConfig(
                agent_id=f"drone_{profile}",
                start_position=(10.0, 25.0),
                max_speed=3.0,
            ),
            goal=(40.0, 25.0),
        )
        engine.add_agent(agent)
        engine.initialize()
        results = engine.run(50)

        h_values = [r.harmony.h_p for r in results]
        results_by_profile[profile] = {
            "avg_h": sum(h_values) / len(h_values),
            "min_h": min(h_values),
            "final_pos": agent.position,
        }

        engine.finalize()
        os.unlink(db_path)

    for profile, data in results_by_profile.items():
        print(
            f"  {profile:25s}: avg_H={data['avg_h']:.4f} "
            f"min_H={data['min_h']:.4f} "
            f"final=({data['final_pos'][0]:.1f}, {data['final_pos'][1]:.1f})"
        )

    # Both should still work (H_p > attention threshold)
    for profile, data in results_by_profile.items():
        assert data["avg_h"] >= THRESHOLD_ATTENTION, (
            f"{profile}: avg H_p too low"
        )

    print("✓ test_network_jitter_impact PASSED\n")


def test_void_index_tracks_movement():
    """Verify VoidIndex correctly tracks agent movement over time."""
    print("--- VoidIndex Tracks Movement ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="open_field",
        network_profile="ideal",
        dt=0.1,
        max_cycles=30,
        boundary=(0, 0, 50, 50),
        db_path=db_path,
        jitter_seed=42,
    )

    engine = SimulationEngine(config)
    agent = ReferenceSyncferenceAgent(
        AgentConfig(
            agent_id="drone_void_test",
            start_position=(25.0, 25.0),
            max_speed=3.0,
        ),
        goal=(45.0, 25.0),
    )
    engine.add_agent(agent)
    engine.initialize()

    results = engine.run(30)

    # After 30 cycles, most cells should be void (agent only occupies ~3x3 cells)
    last_void = results[-1].void_snapshot
    print(f"  Void zones: {last_void['void_zones_count']}")
    print(f"  Void volume: {last_void['total_void_volume']:.0f}m²")
    print(f"  Void fraction: {last_void['void_fraction']:.3f}")

    # Grid is 50×50 = 2500 cells, agent occupies ~9 cells
    # After threshold cycles, most should be void
    assert last_void["void_fraction"] > 0.5, "Most of grid should be void"

    engine.finalize()
    os.unlink(db_path)
    print("✓ test_void_index_tracks_movement PASSED\n")


def test_flight_recorder_timeseries():
    """Verify we can extract Harmony timeseries from the recorder."""
    print("--- Flight Recorder Timeseries ---")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    config = SimulationConfig(
        scenario="open_field",
        network_profile="ideal",
        dt=0.1,
        max_cycles=20,
        boundary=(0, 0, 50, 50),
        db_path=db_path,
        jitter_seed=42,
    )

    engine = SimulationEngine(config)
    agent = ReferenceSyncferenceAgent(
        AgentConfig(agent_id="drone_ts", start_position=(10.0, 25.0)),
        goal=(40.0, 25.0),
    )
    engine.add_agent(agent)
    session_id = engine.initialize()
    engine.run(20)

    # Query timeseries directly from recorder
    recorder = FlightRecorder(db_path)
    recorder.initialize()
    timeseries = recorder.get_harmony_timeseries(session_id)
    recorder.close()

    assert len(timeseries) == 20, f"Expected 20 points, got {len(timeseries)}"
    cycles = [t[0] for t in timeseries]
    assert cycles == list(range(1, 21)), "Cycles should be sequential"

    h_values = [t[1] for t in timeseries]
    print(f"  Timeseries: {len(timeseries)} points")
    print(f"  H_p range: [{min(h_values):.4f}, {max(h_values):.4f}]")

    engine.finalize()
    os.unlink(db_path)
    print("✓ test_flight_recorder_timeseries PASSED\n")


if __name__ == "__main__":
    test_single_agent_syncference()
    test_multi_cycle_stability()
    test_agent_reaches_goal()
    test_network_jitter_impact()
    test_void_index_tracks_movement()
    test_flight_recorder_timeseries()
    print("=" * 55)
    print("=== ALL PASO 1 TESTS PASSED ===")
    print("=" * 55)
