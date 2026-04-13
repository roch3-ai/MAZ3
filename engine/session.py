"""
Session Runner — Execute benchmark sessions and collect data.

Runs the 3×3 matrix:
  3 agent types × 3+ network profiles

Produces the data table for Paper 1.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from scenarios.bottleneck import create_bottleneck_simulation
from roch3.kinetic_safety import DeferenceLevel


@dataclass
class SessionResult:
    """Aggregated results from a benchmark session."""
    scenario: str
    agent_types: str
    network_profile: str
    cycles_run: int
    avg_h_p: float
    min_h_p: float
    max_h_p: float
    avg_convergence_ms: float
    max_convergence_ms: float
    deference_d0: int
    deference_d1: int
    deference_d2: int
    deference_d3_plus: int
    total_detections: int
    void_fraction_final: float

    def to_row(self) -> dict:
        return {
            "agents": self.agent_types,
            "network": self.network_profile,
            "avg_H_p": f"{self.avg_h_p:.4f}",
            "min_H_p": f"{self.min_h_p:.4f}",
            "D0": self.deference_d0,
            "D1": self.deference_d1,
            "D2+": self.deference_d2 + self.deference_d3_plus,
            "conv_ms": f"{self.avg_convergence_ms:.3f}",
            "void%": f"{self.void_fraction_final:.1%}",
        }


def run_session(
    agent_types: str,
    network_profile: str,
    max_cycles: int = 200,
    jitter_seed: int = 42,
) -> SessionResult:
    """Run a single benchmark session and return aggregated results."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        engine, bcfg = create_bottleneck_simulation(
            agent_types=agent_types,
            network_profile=network_profile,
            max_cycles=max_cycles,
            db_path=db_path,
            jitter_seed=jitter_seed,
        )

        engine.initialize()
        results = engine.run(max_cycles)
        summary = engine.finalize()

        # Aggregate harmony
        h_values = [r.harmony.h_p for r in results]
        conv_times = [r.convergence_time_ms for r in results]

        # Count deference levels
        d_counts = {0: 0, 1: 0, 2: 0, 3: 0}
        for r in results:
            for action in r.deference_actions:
                level = min(action.level, 3)
                d_counts[level] = d_counts.get(level, 0) + 1

        # Detections (events ≥ D1)
        total_detections = sum(
            1 for r in results for a in r.deference_actions
            if a.level >= DeferenceLevel.D1
        )

        # Final void fraction
        void_frac = results[-1].void_snapshot["void_fraction"] if results else 0.0

        # Guard against empty results
        # (max_cycles=0, early abort, or adversarial-induced crash)
        return SessionResult(
            scenario="bottleneck",
            agent_types=agent_types,
            network_profile=network_profile,
            cycles_run=len(results),
            avg_h_p=sum(h_values) / len(h_values) if h_values else 0.0,
            min_h_p=min(h_values) if h_values else 0.0,
            max_h_p=max(h_values) if h_values else 0.0,
            avg_convergence_ms=sum(conv_times) / len(conv_times) if conv_times else 0.0,
            max_convergence_ms=max(conv_times) if conv_times else 0.0,
            deference_d0=d_counts[0],
            deference_d1=d_counts[1],
            deference_d2=d_counts[2],
            deference_d3_plus=d_counts[3],
            total_detections=total_detections,
            void_fraction_final=void_frac,
        )
    finally:
        os.unlink(db_path)


def run_benchmark_matrix(
    agent_types_list: list[str] = None,
    network_profiles: list[str] = None,
    max_cycles: int = 200,
) -> list[SessionResult]:
    """
    Run the full benchmark matrix.
    Returns list of SessionResults for tabulation.
    """
    if agent_types_list is None:
        agent_types_list = ["syncference", "mixed", "greedy"]
    if network_profiles is None:
        network_profiles = ["ideal", "industrial_ethernet", "wifi_warehouse"]

    results = []
    for agents in agent_types_list:
        for profile in network_profiles:
            result = run_session(agents, profile, max_cycles)
            results.append(result)

    return results


def print_table(results: list[SessionResult]) -> None:
    """Print results as a formatted table."""
    header = f"{'Agents':<15} {'Network':<22} {'avg_H_p':>8} {'min_H_p':>8} {'D0':>5} {'D1':>5} {'D2+':>5} {'conv_ms':>8} {'void%':>7}"
    print(header)
    print("-" * len(header))
    for r in results:
        row = r.to_row()
        print(
            f"{row['agents']:<15} {row['network']:<22} "
            f"{row['avg_H_p']:>8} {row['min_H_p']:>8} "
            f"{row['D0']:>5} {row['D1']:>5} {row['D2+']:>5} "
            f"{row['conv_ms']:>8} {row['void%']:>7}"
        )
