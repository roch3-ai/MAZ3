"""
scripts/export_results.py

Paper 1 data export — runs a scenario, collects CycleResults, and generates:
  1. CSV  — cycle-by-cycle metrics for supplemental data
  2. LaTeX — formatted table for Paper 1 (Table 3x3 or summary table)
  3. PNG  — H_p over time + trust decay curves (matplotlib)

Usage:
  python scripts/export_results.py --scenario bottleneck --agents 5 --seed 42
  python scripts/export_results.py --scenario intersection --seed 42
  python scripts/export_results.py --scenario corridor --seed 42
  python scripts/export_results.py --scenario void_stress --seed 42

  # Table 3x3: all scenarios, single seed
  python scripts/export_results.py --table3x3 --seed 42 --out results/

Output files (in --out directory):
  maz3_<scenario>_<seed>.csv
  maz3_<scenario>_<seed>.tex
  maz3_<scenario>_<seed>.png
  maz3_table3x3_<seed>.tex   (only with --table3x3)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.simulation import SimulationEngine, SimulationConfig, CycleResult
from agents.base_agent import AgentConfig
from agents.reference_syncference import ReferenceSyncferenceAgent
from roch3.void_index import VoidConfig
from roch3.fairness import compute_fairness_result
from scenarios.bottleneck import create_bottleneck_simulation
from scenarios.intersection import create_intersection_simulation
from scenarios.corridor import create_corridor_simulation
from scenarios.void_stress import create_void_stress_simulation


# ─────────────────────────────────────────────────────────────────────────────
# Row type for export
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExportRow:
    cycle: int
    h_p: float
    d_spatial: float
    d_temporal: float
    d_risk: float
    deference_level: str    # highest D-level this cycle (D0..D4)
    convergence_ms: float
    void_fraction: float
    attacks_detected: int   # count of attacks this cycle


def _deference_label(actions: list) -> str:
    """Highest deference level fired this cycle."""
    if not actions:
        return "D0"
    max_lvl = max(a.level.value for a in actions)
    return f"D{max_lvl}"


def collect_cycle_rows(
    engine: SimulationEngine,
    max_cycles: int,
) -> list[ExportRow]:
    """Run engine and collect one ExportRow per cycle."""
    rows: list[ExportRow] = []
    for _ in range(max_cycles):
        result: CycleResult = engine.step()
        rows.append(ExportRow(
            cycle=result.cycle,
            h_p=result.harmony.h_p,
            d_spatial=result.harmony.components.d_spatial,
            d_temporal=result.harmony.components.d_temporal,
            d_risk=result.harmony.components.d_risk,
            deference_level=_deference_label(result.deference_actions),
            convergence_ms=result.convergence_time_ms,
            void_fraction=result.void_snapshot.get("void_fraction", 0.0),
            attacks_detected=len(result.attacks_detected),
        ))
    engine.finalize()
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# CSV export
# ─────────────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "cycle", "h_p", "d_spatial", "d_temporal", "d_risk",
    "deference_level", "convergence_ms", "void_fraction", "attacks_detected",
]


def write_csv(rows: list[ExportRow], path: str) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "cycle": r.cycle,
                "h_p": f"{r.h_p:.6f}",
                "d_spatial": f"{r.d_spatial:.6f}",
                "d_temporal": f"{r.d_temporal:.6f}",
                "d_risk": f"{r.d_risk:.6f}",
                "deference_level": r.deference_level,
                "convergence_ms": f"{r.convergence_ms:.3f}",
                "void_fraction": f"{r.void_fraction:.6f}",
                "attacks_detected": r.attacks_detected,
            })
    print(f"  CSV  → {path} ({len(rows)} rows)")


# ─────────────────────────────────────────────────────────────────────────────
# LaTeX summary table (single scenario)
# ─────────────────────────────────────────────────────────────────────────────

def _summary_stats(rows: list[ExportRow]) -> dict:
    if not rows:
        return {}
    hp = [r.h_p for r in rows]
    d_sp = [r.d_spatial for r in rows]
    d_tm = [r.d_temporal for r in rows]
    d_rk = [r.d_risk for r in rows]
    d1_plus = sum(1 for r in rows if r.deference_level not in ("D0",))
    return {
        "avg_hp": sum(hp) / len(hp),
        "min_hp": min(hp),
        "max_hp": max(hp),
        "avg_d_spatial": sum(d_sp) / len(d_sp),
        "avg_d_temporal": sum(d_tm) / len(d_tm),
        "avg_d_risk": sum(d_rk) / len(d_rk),
        "d1_plus_cycles": d1_plus,
        "d1_plus_pct": d1_plus / len(rows) * 100,
        "attacks_total": sum(r.attacks_detected for r in rows),
        "n_cycles": len(rows),
    }


def write_latex_summary(
    rows: list[ExportRow],
    scenario: str,
    seed: int,
    path: str,
) -> None:
    s = _summary_stats(rows)
    if not s:
        print(f"  LaTeX → skipped (no data)")
        return

    label = scenario.replace("_", r"\_")

    tex = r"""\begin{table}[h]
\centering
\caption{MAZ3 """ + label + r""" Scenario — Cycle-Level Metrics (seed """ + str(seed) + r""")}
\label{tab:maz3_""" + scenario + r"""}
\begin{tabular}{lrr}
\toprule
\textbf{Metric} & \textbf{Value} & \textbf{Unit} \\
\midrule
Cycles run           & """ + str(s["n_cycles"]) + r""" & cycles \\
Avg $H_p$            & """ + f"{s['avg_hp']:.4f}" + r""" & [0,1] \\
Min $H_p$            & """ + f"{s['min_hp']:.4f}" + r""" & [0,1] \\
Avg $D_\text{spatial}$ & """ + f"{s['avg_d_spatial']:.4f}" + r""" & [0,1] \\
Avg $D_\text{temporal}$ & """ + f"{s['avg_d_temporal']:.4f}" + r""" & [0,1] \\
Avg $D_\text{risk}$  & """ + f"{s['avg_d_risk']:.4f}" + r""" & [0,1] \\
D1+ cycles           & """ + f"{s['d1_plus_cycles']}" + r""" & (""" + f"{s['d1_plus_pct']:.1f}" + r"""\%) \\
Attacks detected     & """ + f"{s['attacks_total']}" + r""" & events \\
\bottomrule
\end{tabular}
\end{table}
"""
    with open(path, "w") as f:
        f.write(tex)
    print(f"  LaTeX → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Table 3×3 (3 scenarios × 3 agent_type/fidelity levels)
# ─────────────────────────────────────────────────────────────────────────────

def write_latex_table3x3(
    data: dict[str, dict[str, dict]],
    seed: int,
    path: str,
) -> None:
    """
    data: {scenario: {agent_type: summary_stats_dict}}
    Produces a LaTeX table: rows = scenarios, cols = agent_type variants.
    """
    scenarios = list(data.keys())
    variants = []
    for s in scenarios:
        for v in data[s].keys():
            if v not in variants:
                variants.append(v)

    # Header
    col_spec = "l" + "r" * len(variants)
    variant_headers = " & ".join(
        r"\textbf{" + v.replace("_", r"\_") + "}" for v in variants
    )

    rows_tex = []
    for sc in scenarios:
        sc_label = sc.replace("_", r"\_")
        cells = []
        for v in variants:
            if v in data[sc]:
                s = data[sc][v]
                cells.append(f"{s['avg_hp']:.3f} / {s['min_hp']:.3f}")
            else:
                cells.append("--")
        rows_tex.append(sc_label + " & " + " & ".join(cells) + r" \\")

    tex = r"""\begin{table}[h]
\centering
\caption{MAZ3 Benchmark — $H_p$ (avg / min) across scenarios and agent populations (seed """ + str(seed) + r""")}
\label{tab:maz3_3x3}
\begin{tabular}{""" + col_spec + r"""}
\toprule
\textbf{Scenario} & """ + variant_headers + r""" \\
\midrule
""" + "\n".join(rows_tex) + r"""
\bottomrule
\end{tabular}
\end{table}
% Rows: scenario. Columns: agent population variant. Cell: avg\_Hp / min\_Hp.
"""
    with open(path, "w") as f:
        f.write(tex)
    print(f"  LaTeX 3×3 → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# PNG export (H_p over time + trust decay curve via D-level proxy)
# ─────────────────────────────────────────────────────────────────────────────

def write_png(
    rows: list[ExportRow],
    scenario: str,
    seed: int,
    path: str,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"  PNG  → skipped (matplotlib not available)")
        return

    cycles = [r.cycle for r in rows]
    hp = [r.h_p for r in rows]
    d_sp = [r.d_spatial for r in rows]
    d_tm = [r.d_temporal for r in rows]
    d_rk = [r.d_risk for r in rows]

    # D-level as numeric for secondary axis
    d_lvl_num = []
    for r in rows:
        lvl = r.deference_level
        d_lvl_num.append(int(lvl[1]) if lvl.startswith("D") and lvl[1:].isdigit() else 0)

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    fig.suptitle(
        f"MAZ3 — {scenario.replace('_', ' ').title()} (seed={seed})",
        fontsize=13, fontweight="bold"
    )

    # Top: H_p and divergence components
    ax1 = axes[0]
    ax1.plot(cycles, hp, color="#2563EB", linewidth=1.8, label=r"$H_p$")
    ax1.fill_between(cycles, hp, alpha=0.12, color="#2563EB")
    ax1.plot(cycles, d_sp, color="#DC2626", linewidth=0.9, linestyle="--",
             alpha=0.8, label=r"$D_\mathrm{spatial}$")
    ax1.plot(cycles, d_tm, color="#16A34A", linewidth=0.9, linestyle=":",
             alpha=0.8, label=r"$D_\mathrm{temporal}$")
    ax1.plot(cycles, d_rk, color="#D97706", linewidth=0.9, linestyle="-.",
             alpha=0.8, label=r"$D_\mathrm{risk}$")
    ax1.axhline(0.85, color="#9CA3AF", linewidth=0.8, linestyle="--",
                label="Healthy (0.85)")
    ax1.axhline(0.55, color="#EF4444", linewidth=0.8, linestyle="--",
                label="Intervene (0.55)")
    ax1.set_ylabel("Index value [0, 1]")
    ax1.set_ylim(-0.05, 1.05)
    ax1.legend(loc="lower left", fontsize=8, ncol=3)
    ax1.grid(True, alpha=0.3)

    # Bottom: Deference level per cycle
    ax2 = axes[1]
    ax2.bar(cycles, d_lvl_num, color="#7C3AED", alpha=0.6, width=1.0,
            label="Deference level")
    ax2.set_ylabel("Deference level (0–4)")
    ax2.set_xlabel("Cycle")
    ax2.set_yticks([0, 1, 2, 3, 4])
    ax2.set_yticklabels(["D0", "D1", "D2", "D3", "D4"])
    ax2.legend(loc="upper right", fontsize=8)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  PNG  → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Scenario runners (unified interface)
# ─────────────────────────────────────────────────────────────────────────────

def _run_bottleneck(agent_types: str, seed: int, max_cycles: int) -> list[ExportRow]:
    engine, _ = create_bottleneck_simulation(
        agent_types=agent_types,
        network_profile="ideal",
        max_cycles=max_cycles,
        db_path=":memory:",
        jitter_seed=seed,
    )
    engine._config.seed = seed
    engine.initialize()
    return collect_cycle_rows(engine, max_cycles)


def _run_intersection(agent_types: str, seed: int, max_cycles: int) -> list[ExportRow]:
    engine, _ = create_intersection_simulation(
        agent_types=agent_types,
        network_profile="ideal",
        max_cycles=max_cycles,
        db_path=":memory:",
        jitter_seed=seed,
    )
    engine._config.seed = seed
    engine.initialize()
    return collect_cycle_rows(engine, max_cycles)


def _run_corridor(agent_types: str, seed: int, max_cycles: int) -> list[ExportRow]:
    engine, _ = create_corridor_simulation(
        agent_types=agent_types,
        network_profile="ideal",
        max_cycles=max_cycles,
        db_path=":memory:",
        jitter_seed=seed,
    )
    engine._config.seed = seed
    engine.initialize()
    return collect_cycle_rows(engine, max_cycles)


def _run_void_stress(seed: int, max_cycles: int) -> list[ExportRow]:
    engine, _ = create_void_stress_simulation(
        inflation_factor=8.0,
        activate_cycle=10,
        network_profile="ideal",
        max_cycles=max_cycles,
        db_path=":memory:",
        jitter_seed=seed,
    )
    engine._config.seed = seed
    engine.initialize()
    return collect_cycle_rows(engine, max_cycles)


SCENARIO_RUNNERS = {
    "bottleneck": {
        "syncference": lambda s, n: _run_bottleneck("syncference", s, n),
        "mixed":       lambda s, n: _run_bottleneck("mixed", s, n),
        "greedy":      lambda s, n: _run_bottleneck("greedy", s, n),
    },
    "intersection": {
        "syncference": lambda s, n: _run_intersection("syncference", s, n),
        "mixed":       lambda s, n: _run_intersection("mixed", s, n),
        "adversarial": lambda s, n: _run_intersection("adversarial", s, n),
    },
    "corridor": {
        "syncference": lambda s, n: _run_corridor("syncference", s, n),
        "mixed":       lambda s, n: _run_corridor("mixed", s, n),
        "greedy_all":  lambda s, n: _run_corridor("greedy_all", s, n),
    },
    "void_stress": {
        "adversarial": lambda s, n: _run_void_stress(s, n),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Main export function
# ─────────────────────────────────────────────────────────────────────────────

def export_scenario(
    scenario: str,
    agent_types: str = "syncference",
    seed: int = 42,
    max_cycles: int = 300,
    out_dir: str = ".",
) -> list[ExportRow]:
    os.makedirs(out_dir, exist_ok=True)
    stem = f"maz3_{scenario}_{agent_types}_{seed}"

    print(f"\n[export] {scenario} / {agent_types} / seed={seed}")

    runners = SCENARIO_RUNNERS.get(scenario)
    if runners is None:
        raise ValueError(f"Unknown scenario: {scenario!r}")
    runner = runners.get(agent_types)
    if runner is None:
        raise ValueError(f"Unknown agent_types {agent_types!r} for scenario {scenario!r}")

    rows = runner(seed, max_cycles)

    write_csv(rows, os.path.join(out_dir, f"{stem}.csv"))
    write_latex_summary(rows, scenario, seed, os.path.join(out_dir, f"{stem}.tex"))
    write_png(rows, scenario, seed, os.path.join(out_dir, f"{stem}.png"))

    return rows


def export_table3x3(
    seed: int = 42,
    max_cycles: int = 200,
    out_dir: str = ".",
) -> None:
    """
    Run 3 scenarios × 3 agent variants, build LaTeX 3×3 table.
    Scenarios: bottleneck, intersection, corridor
    Variants: syncference, mixed, adversarial/greedy_all
    """
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n[export] Table 3×3 / seed={seed}")

    config = {
        "bottleneck":   ["syncference", "mixed", "greedy"],
        "intersection": ["syncference", "mixed", "adversarial"],
        "corridor":     ["syncference", "mixed", "greedy_all"],
    }

    table_data: dict[str, dict[str, dict]] = {}
    for scenario, variants in config.items():
        table_data[scenario] = {}
        runners = SCENARIO_RUNNERS[scenario]
        for agent_types in variants:
            runner = runners.get(agent_types)
            if runner is None:
                continue
            print(f"  Running {scenario}/{agent_types}...")
            rows = runner(seed, max_cycles)
            table_data[scenario][agent_types] = _summary_stats(rows)
            # Also write individual CSV
            stem = f"maz3_{scenario}_{agent_types}_{seed}"
            write_csv(rows, os.path.join(out_dir, f"{stem}.csv"))

    write_latex_table3x3(
        table_data, seed,
        os.path.join(out_dir, f"maz3_table3x3_{seed}.tex")
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MAZ3 Paper 1 data exporter — CSV, LaTeX, PNG"
    )
    parser.add_argument(
        "--scenario", default="bottleneck",
        choices=list(SCENARIO_RUNNERS.keys()),
        help="Scenario to run",
    )
    parser.add_argument(
        "--agent-types", default="syncference",
        help="Agent population variant (syncference | mixed | adversarial | greedy_all)",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    parser.add_argument("--cycles", type=int, default=300, help="Max cycles")
    parser.add_argument("--out", default="results", help="Output directory")
    parser.add_argument(
        "--table3x3", action="store_true",
        help="Generate full 3×3 scenario table for Paper 1",
    )
    args = parser.parse_args()

    if args.table3x3:
        export_table3x3(seed=args.seed, max_cycles=args.cycles, out_dir=args.out)
    else:
        export_scenario(
            scenario=args.scenario,
            agent_types=args.agent_types,
            seed=args.seed,
            max_cycles=args.cycles,
            out_dir=args.out,
        )


if __name__ == "__main__":
    main()
