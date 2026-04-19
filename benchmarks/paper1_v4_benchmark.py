"""
Benchmark runner for Paper 1 v4.

Scope (confirmed 2026-04-17):
- 1 scenario: Bottleneck  (Intersection is future work, see §5.4)
- 3 network profiles: ideal, wifi_warehouse, lora_mesh
- 5 agent types: syncference, greedy, mixed, orca, omniscient_v2
    → 15 cells total, minus (orca + lora_mesh) skip = 14 effective.

For each cell we compute:
- H_p mean and std (secondary under v4; kept for backward compat)
- Collisions/cycle mean and std (primary)
- Task completion fraction mean and std (primary)
- Deadlock frequency (primary)
- Algorithmic convergence time mean (ms, excludes network δ)

Output:
- results/paper1_v4_benchmark_N{N}.json   (machine-readable)
- results/paper1_v4_benchmark_N{N}.md     (ready-to-paste tables)

Seeds are (seed_base + run_index) so any single cell is reproducible in
isolation.

Usage:
    python -m benchmarks.paper1_v4_benchmark --n 50 --seed-base 42
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from typing import List

# Allow "python benchmarks/paper1_v4_benchmark.py" from repo root as well as
# "python -m benchmarks.paper1_v4_benchmark". Both need the repo root on
# sys.path so that sibling packages (engine, agents, roch3, scenarios) import.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from engine.session import run_session  # noqa: E402


NETWORK_PROFILES = ["ideal", "wifi_warehouse", "lora_mesh"]

# Scenario catalogue. Each entry maps scenario → (agent_types, cycles).
# - bottleneck: 5 agent types × 3 networks × 1 scenario = 15 (−1 skip = 14).
# - asymmetric_risk: 4 agent types × 3 networks = 12 (−1 skip = 11).
#   "mixed" is excluded because it uses ReferenceRandomAgent (no goal),
#   which would bias task_completion in an open-field risk study.
AGENT_TYPES_BY_SCENARIO: dict[str, list[str]] = {
    "bottleneck": ["syncference", "greedy", "mixed", "orca", "omniscient_v2"],
    "asymmetric_risk": ["syncference", "greedy", "orca", "omniscient_v2"],
}
CYCLES_BY_SCENARIO: dict[str, int] = {
    "bottleneck": 200,        # long enough for deadlock detection
    "asymmetric_risk": 300,   # longer to allow detours around the zone
}
SCENARIOS = list(AGENT_TYPES_BY_SCENARIO.keys())


@dataclass
class CellResult:
    scenario: str
    network: str
    agent_type: str
    n_runs: int
    hp_mean: float
    hp_std: float
    collision_rate_mean: float
    collision_rate_std: float
    task_completion_mean: float
    task_completion_std: float
    deadlock_frequency: float      # fraction of runs that deadlocked
    convergence_ms_mean: float
    convergence_ms_std: float


def run_cell(
    scenario: str, network: str, agent_type: str,
    n_runs: int, seed_base: int, cycles_per_run: int,
) -> CellResult:
    hp_vals: List[float] = []
    collision_rates: List[float] = []
    completions: List[float] = []
    deadlocks = 0
    convergence_times: List[float] = []

    for run_idx in range(n_runs):
        seed = seed_base + run_idx
        result = run_session(
            agent_types=agent_type,
            network_profile=network,
            scenario=scenario,
            max_cycles=cycles_per_run,
            jitter_seed=seed,
        )
        hp_vals.append(result.hp_mean)
        collision_rates.append(result.collisions_per_cycle)
        completions.append(result.task_completion_fraction)
        if result.deadlocked:
            deadlocks += 1
        convergence_times.append(result.mean_algorithmic_convergence_ms)

    def _std(xs: List[float]) -> float:
        return statistics.stdev(xs) if len(xs) > 1 else 0.0

    return CellResult(
        scenario=scenario,
        network=network,
        agent_type=agent_type,
        n_runs=n_runs,
        hp_mean=statistics.mean(hp_vals),
        hp_std=_std(hp_vals),
        collision_rate_mean=statistics.mean(collision_rates),
        collision_rate_std=_std(collision_rates),
        task_completion_mean=statistics.mean(completions),
        task_completion_std=_std(completions),
        deadlock_frequency=deadlocks / n_runs,
        convergence_ms_mean=statistics.mean(convergence_times),
        convergence_ms_std=_std(convergence_times),
    )


def run_full_benchmark(
    n_runs: int, seed_base: int,
    scenarios: List[str] | None = None,
) -> List[CellResult]:
    selected = scenarios if scenarios else SCENARIOS
    results: List[CellResult] = []
    total_cells = sum(
        len(NETWORK_PROFILES) * len(AGENT_TYPES_BY_SCENARIO[s])
        for s in selected
    )
    cell_idx = 0
    for scenario in selected:
        agent_types = AGENT_TYPES_BY_SCENARIO[scenario]
        cycles = CYCLES_BY_SCENARIO[scenario]
        for network in NETWORK_PROFILES:
            for agent_type in agent_types:
                cell_idx += 1
                # ORCA assumes reliable communications as part of its homogeneous
                # baseline contract. Running it on lora_mesh is not a meaningful
                # comparison — we document the skip in the paper.
                if agent_type == "orca" and network == "lora_mesh":
                    print(
                        f"[{cell_idx}/{total_cells}] SKIP: {scenario} | "
                        "orca + lora_mesh (ORCA assumes reliable comms)"
                    )
                    continue
                print(
                    f"[{cell_idx}/{total_cells}] {scenario} | "
                    f"{network} | {agent_type}"
                )
                cell = run_cell(
                    scenario, network, agent_type,
                    n_runs, seed_base, cycles,
                )
                results.append(cell)
    return results


def format_results_markdown(results: List[CellResult]) -> str:
    lines = []
    lines.append("# Paper 1 v4 — Benchmark Results\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Runs per cell: {results[0].n_runs if results else 'N/A'}\n")
    lines.append(
        "\n## Primary metrics (collision rate, task completion, deadlock frequency)\n"
    )

    scenarios_present = sorted({r.scenario for r in results})
    for scenario in scenarios_present:
        lines.append(f"\n### Scenario: {scenario.capitalize()}\n")
        for network in NETWORK_PROFILES:
            lines.append(f"\n#### Network: {network}\n")
            lines.append(
                "| Agent Type | Collisions/cycle | Task Completion | "
                "Deadlock Freq | H_p (secondary) |"
            )
            lines.append("|---|---|---|---|---|")
            for r in results:
                if r.scenario == scenario and r.network == network:
                    lines.append(
                        f"| {r.agent_type} | "
                        f"{r.collision_rate_mean:.4f} ± {r.collision_rate_std:.4f} | "
                        f"{r.task_completion_mean:.3f} ± {r.task_completion_std:.3f} | "
                        f"{r.deadlock_frequency:.2f} | "
                        f"{r.hp_mean:.3f} ± {r.hp_std:.3f} |"
                    )

    lines.append("\n## Algorithmic convergence time (excludes network δ)\n")
    lines.append("| Scenario | Network | Agent Type | Convergence (ms) |")
    lines.append("|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.scenario} | {r.network} | {r.agent_type} | "
            f"{r.convergence_ms_mean:.4f} ± {r.convergence_ms_std:.4f} |"
        )

    # One SBE table per scenario that contains both syncference and omniscient_v2.
    for scenario in scenarios_present:
        sync = [r for r in results
                if r.agent_type == "syncference" and r.scenario == scenario]
        omni = [r for r in results
                if r.agent_type == "omniscient_v2" and r.scenario == scenario]
        if not (sync and omni):
            continue
        lines.append(
            f"\n## Sovereign Behavioral Equivalence "
            f"(Syncference vs OmniscientV2, {scenario.capitalize()})\n"
        )
        lines.append(
            "| Network | Syncference H_p | OmniscientV2 H_p | Δ | "
            "Coll (Sync) | Coll (Omni) | Task (Sync) | Task (Omni) | "
            "Deadlock (Sync) | Deadlock (Omni) |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|---|---|"
        )
        for s in sync:
            o = next((x for x in omni if x.network == s.network), None)
            if o is None:
                continue
            delta = s.hp_mean - o.hp_mean
            lines.append(
                f"| {s.network} | {s.hp_mean:.4f} ± {s.hp_std:.4f} | "
                f"{o.hp_mean:.4f} ± {o.hp_std:.4f} | "
                f"{delta:+.4f} | "
                f"{s.collision_rate_mean:.4f} | {o.collision_rate_mean:.4f} | "
                f"{s.task_completion_mean:.3f} | {o.task_completion_mean:.3f} | "
                f"{s.deadlock_frequency:.2f} | {o.deadlock_frequency:.2f} |"
            )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="runs per cell")
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="results")
    parser.add_argument(
        "--scenarios", nargs="+", default=["all"],
        help=(
            "Scenario names, space- or comma-separated, or 'all'. "
            f"Known: {','.join(SCENARIOS)}"
        ),
    )
    parser.add_argument(
        "--suffix", type=str, default="",
        help="Optional suffix appended to output filenames."
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    raw_scenarios = args.scenarios
    if len(raw_scenarios) == 1 and raw_scenarios[0] == "all":
        selected = SCENARIOS
    else:
        selected = []
        for item in raw_scenarios:
            selected.extend(s.strip() for s in item.split(",") if s.strip())
        for s in selected:
            if s not in AGENT_TYPES_BY_SCENARIO:
                raise SystemExit(f"Unknown scenario: {s!r}")

    total_cells = sum(
        len(NETWORK_PROFILES) * len(AGENT_TYPES_BY_SCENARIO[s])
        for s in selected
    )
    skip_cells = sum(1 for s in selected if "orca" in AGENT_TYPES_BY_SCENARIO[s])
    print(f"Running benchmark: N={args.n}, seed_base={args.seed_base}")
    print(f"Scenarios: {selected}")
    print(
        f"Total cells: {total_cells} "
        f"(minus {skip_cells} documented orca+lora_mesh skip"
        f"{'s' if skip_cells != 1 else ''} = "
        f"{total_cells - skip_cells} effective)"
    )

    t0 = time.perf_counter()
    results = run_full_benchmark(args.n, args.seed_base, selected)
    elapsed_min = (time.perf_counter() - t0) / 60.0
    print(f"\nCompleted in {elapsed_min:.1f} min.")

    suffix = f"_{args.suffix}" if args.suffix else ""
    json_path = os.path.join(
        args.output_dir, f"paper1_v4_benchmark_N{args.n}{suffix}.json"
    )
    with open(json_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    print(f"Wrote {json_path}")

    md_path = os.path.join(
        args.output_dir, f"paper1_v4_benchmark_N{args.n}{suffix}.md"
    )
    with open(md_path, "w") as f:
        f.write(format_results_markdown(results))
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
