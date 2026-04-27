"""
Brecha A — Antifragility Decay experiment runner (dual-metric).

Spec:
  Main: 5 strategies × 200 runs × 100 cycles = 100,000 cycle-steps
  Floor sensitivity: 4 trust_floor values × 100 runs × 100 cycles = 40,000 cycle-steps
  TOTAL: 140,000 cycle-steps

Each run: Bottleneck with 1 focal agent + 2 Syncference baseline agents.
Focal uses agent_id "focal_<strategy>".

Two attacker-payoff metrics are computed per run:
  payoff_binary       — original (events-only, conservative)
  payoff_proportional — refined (continuous task progress + graded
                        detection severity + proportional trust cost)

Outputs in experiments/brecha_a/:
  raw_runs.csv      — per-run summary (one row per run, both metrics)
  aggregated.csv    — mean/std payoff per (group, metric, cycle)
  plot_payoff_decay.png        (2 panels: binary | proportional)
  plot_floor_sensitivity.png   (2 panels: binary | proportional)
  summary.md
  stats.md
"""

from __future__ import annotations

import csv
import math
import os
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, asdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import numpy as np
from scipy import stats

from scenarios.bottleneck import create_bottleneck_with_focal_agent
from experiments.brecha_a.attacker_payoff import (
    compute_attacker_payoff,
    cumulative_payoff_binary,
    cumulative_payoff_proportional,
)


SEED_BASE = 7500
MAX_CYCLES = 100
N_RUNS_PER_STRATEGY = 200
STRATEGIES_MAIN = ["inflator", "underreporter", "mixed", "burst_recovery", "greedy"]

N_RUNS_FLOOR = 100
FLOOR_VALUES = [0.0, 0.1, 0.2, 0.3]
FLOOR_STRATEGY = "inflator"

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class RunSummary:
    run_id: int
    strategy: str
    trust_floor: float
    seed: int
    final_distance_to_goal: float
    initial_distance_to_goal: float
    task_completed: bool
    final_trust: float
    total_detections: int
    cum_payoff_binary_final: float
    cum_payoff_proportional_final: float
    mean_payoff_binary: float
    mean_payoff_proportional: float


def _run_single(
    run_id: int,
    strategy: str,
    seed: int,
    trust_floor: float = 0.0,
) -> tuple[RunSummary, list[tuple[int, float]], list[tuple[int, float]]]:
    """Run one Bottleneck. Returns (summary, per_cycle_binary, per_cycle_prop)."""
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix=f"brecha_a_{strategy}_")
    os.close(fd)

    try:
        engine, _ = create_bottleneck_with_focal_agent(
            focal_type=strategy,
            max_cycles=MAX_CYCLES,
            db_path=db_path,
            jitter_seed=seed,
            trust_floor=trust_floor,
            activate_after_cycle=5,
        )
        session_id = engine.initialize()

        focal_id = f"focal_{strategy}"
        focal_goal = engine.get_agent_goal(focal_id)
        # Initial distance (cycle 0, before any step)
        focal_pos0 = engine.get_agent_position(focal_id)
        initial_dist = float("inf")
        if focal_pos0 and focal_goal:
            initial_dist = math.sqrt(
                (focal_pos0[0] - focal_goal[0]) ** 2
                + (focal_pos0[1] - focal_goal[1]) ** 2
            )

        distances_per_cycle: dict[int, float] = {}
        # Cycle counter inside the engine starts at 0 then increments;
        # snapshots are recorded per cycle. We capture distance at the END of
        # each engine.step() and key by the engine's internal cycle index.
        for _ in range(MAX_CYCLES):
            engine.step()
            cyc = engine._cycle - 1  # _cycle is incremented before snapshot
            pos = engine.get_agent_position(focal_id)
            if pos and focal_goal:
                d = math.sqrt(
                    (pos[0] - focal_goal[0]) ** 2
                    + (pos[1] - focal_goal[1]) ** 2
                )
                distances_per_cycle[cyc] = d

        focal_idx = engine._buffer.get_index_for_agent(focal_id)
        focal_pos = engine.get_agent_position(focal_id)
        final_dist = float("inf")
        if focal_pos and focal_goal:
            final_dist = math.sqrt(
                (focal_pos[0] - focal_goal[0]) ** 2
                + (focal_pos[1] - focal_goal[1]) ** 2
            )
        engine.finalize()

        if focal_idx is None:
            summary = RunSummary(
                run_id=run_id, strategy=strategy, trust_floor=trust_floor,
                seed=seed, final_distance_to_goal=final_dist,
                initial_distance_to_goal=initial_dist,
                task_completed=False, final_trust=1.0,
                total_detections=0,
                cum_payoff_binary_final=0.0,
                cum_payoff_proportional_final=0.0,
                mean_payoff_binary=0.0,
                mean_payoff_proportional=0.0,
            )
            return summary, [], []

        payoff_result = compute_attacker_payoff(
            db_path=db_path,
            session_id=session_id,
            focal_agent_id=focal_id,
            focal_agent_index=focal_idx,
            final_distance_to_goal=final_dist,
            distances_per_cycle=distances_per_cycle,
            initial_distance_to_goal=initial_dist,
        )
        cum_b = cumulative_payoff_binary(payoff_result.rows)
        cum_p = cumulative_payoff_proportional(payoff_result.rows)
        cum_b_final = cum_b[-1][1] if cum_b else 0.0
        cum_p_final = cum_p[-1][1] if cum_p else 0.0
        if payoff_result.rows:
            mean_b = sum(r.payoff_binary for r in payoff_result.rows) / len(payoff_result.rows)
            mean_p = sum(r.payoff_proportional for r in payoff_result.rows) / len(payoff_result.rows)
        else:
            mean_b = 0.0
            mean_p = 0.0
        summary = RunSummary(
            run_id=run_id,
            strategy=strategy,
            trust_floor=trust_floor,
            seed=seed,
            final_distance_to_goal=final_dist,
            initial_distance_to_goal=initial_dist,
            task_completed=payoff_result.task_completed_at_cycle is not None,
            final_trust=payoff_result.final_trust,
            total_detections=payoff_result.total_detections,
            cum_payoff_binary_final=cum_b_final,
            cum_payoff_proportional_final=cum_p_final,
            mean_payoff_binary=mean_b,
            mean_payoff_proportional=mean_p,
        )
        per_cycle_b = [(r.cycle, r.payoff_binary) for r in payoff_result.rows]
        per_cycle_p = [(r.cycle, r.payoff_proportional) for r in payoff_result.rows]
        return summary, per_cycle_b, per_cycle_p
    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass


def _aggregate_per_cycle(
    all_per_cycle: dict[str, list[list[tuple[int, float]]]],
) -> dict[str, dict[int, tuple[float, float, int]]]:
    agg: dict[str, dict[int, tuple[float, float, int]]] = {}
    for strat, runs in all_per_cycle.items():
        per_cycle: dict[int, list[float]] = defaultdict(list)
        for run in runs:
            for cycle, payoff in run:
                per_cycle[cycle].append(payoff)
        agg[strat] = {}
        for c, vals in per_cycle.items():
            arr = np.asarray(vals)
            agg[strat][c] = (float(arr.mean()), float(arr.std()), len(vals))
    return agg


def _mann_kendall(values: list[float]) -> tuple[float, float]:
    if len(values) < 4:
        return float("nan"), float("nan")
    n = len(values)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            d = values[j] - values[i]
            if d > 0:
                s += 1
            elif d < 0:
                s -= 1
    var_s = n * (n - 1) * (2 * n + 5) / 18.0
    if var_s <= 0:
        return float("nan"), float("nan")
    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    tau = s / (n * (n - 1) / 2)
    return float(tau), float(p)


def _linear_regression(cycles: list[int], payoffs: list[float]) -> dict:
    if len(cycles) < 3:
        return {"slope": float("nan"), "intercept": float("nan"),
                "p_value": float("nan"), "r_squared": float("nan")}
    res = stats.linregress(cycles, payoffs)
    return {
        "slope": float(res.slope),
        "intercept": float(res.intercept),
        "p_value": float(res.pvalue),
        "r_squared": float(res.rvalue ** 2),
    }


def main() -> None:
    t_start = time.time()
    print(f"[Brecha A v2] Starting at {time.strftime('%H:%M:%S')}")
    print(f"[Brecha A v2] Main: {len(STRATEGIES_MAIN)} strategies × {N_RUNS_PER_STRATEGY} runs × {MAX_CYCLES} cycles")
    print(f"[Brecha A v2] Floor: {len(FLOOR_VALUES)} floors × {N_RUNS_FLOOR} runs × {MAX_CYCLES} cycles")
    print(f"[Brecha A v2] Both metrics: payoff_binary + payoff_proportional")

    all_summaries: list[RunSummary] = []
    main_b: dict[str, list[list[tuple[int, float]]]] = {s: [] for s in STRATEGIES_MAIN}
    main_p: dict[str, list[list[tuple[int, float]]]] = {s: [] for s in STRATEGIES_MAIN}
    floor_b: dict[float, list[list[tuple[int, float]]]] = {f: [] for f in FLOOR_VALUES}
    floor_p: dict[float, list[list[tuple[int, float]]]] = {f: [] for f in FLOOR_VALUES}

    run_id = 0
    for strategy in STRATEGIES_MAIN:
        t0 = time.time()
        for r in range(N_RUNS_PER_STRATEGY):
            run_id += 1
            seed = SEED_BASE + run_id
            try:
                summary, pc_b, pc_p = _run_single(
                    run_id=run_id, strategy=strategy, seed=seed,
                    trust_floor=0.0,
                )
                all_summaries.append(summary)
                main_b[strategy].append(pc_b)
                main_p[strategy].append(pc_p)
            except Exception as e:
                print(f"  ! run {run_id} {strategy} failed: {e}")
                continue
            if (r + 1) % 50 == 0:
                elapsed = time.time() - t0
                print(f"  {strategy}: {r+1}/{N_RUNS_PER_STRATEGY} runs in {elapsed:.1f}s")
        print(f"  {strategy}: done in {time.time() - t0:.1f}s")

    print("\n[Brecha A v2] Floor sensitivity sub-experiment...")
    for floor in FLOOR_VALUES:
        t0 = time.time()
        for r in range(N_RUNS_FLOOR):
            run_id += 1
            seed = SEED_BASE + run_id
            try:
                summary, pc_b, pc_p = _run_single(
                    run_id=run_id, strategy=FLOOR_STRATEGY, seed=seed,
                    trust_floor=floor,
                )
                summary.trust_floor = floor
                all_summaries.append(summary)
                floor_b[floor].append(pc_b)
                floor_p[floor].append(pc_p)
            except Exception as e:
                print(f"  ! run {run_id} floor={floor} failed: {e}")
                continue
        print(f"  floor={floor}: {N_RUNS_FLOOR} runs in {time.time() - t0:.1f}s")

    elapsed_total = time.time() - t_start
    print(f"\n[Brecha A v2] All runs done in {elapsed_total:.1f}s")

    # === CSVs ===
    raw_path = os.path.join(OUT_DIR, "raw_runs.csv")
    with open(raw_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(all_summaries[0]).keys()))
        w.writeheader()
        for s in all_summaries:
            w.writerow(asdict(s))
    print(f"  wrote {raw_path} ({len(all_summaries)} rows)")

    agg_main_b = _aggregate_per_cycle(main_b)
    agg_main_p = _aggregate_per_cycle(main_p)
    agg_floor_b = _aggregate_per_cycle({f"floor_{f}": v for f, v in floor_b.items()})
    agg_floor_p = _aggregate_per_cycle({f"floor_{f}": v for f, v in floor_p.items()})

    agg_path = os.path.join(OUT_DIR, "aggregated.csv")
    with open(agg_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["group", "metric", "cycle", "mean_payoff", "std_payoff", "n_runs"])
        for strat, per_cycle in agg_main_b.items():
            for c in sorted(per_cycle.keys()):
                m, s, n = per_cycle[c]
                w.writerow([strat, "binary", c, f"{m:.6f}", f"{s:.6f}", n])
        for strat, per_cycle in agg_main_p.items():
            for c in sorted(per_cycle.keys()):
                m, s, n = per_cycle[c]
                w.writerow([strat, "proportional", c, f"{m:.6f}", f"{s:.6f}", n])
        for fkey, per_cycle in agg_floor_b.items():
            for c in sorted(per_cycle.keys()):
                m, s, n = per_cycle[c]
                w.writerow([fkey, "binary", c, f"{m:.6f}", f"{s:.6f}", n])
        for fkey, per_cycle in agg_floor_p.items():
            for c in sorted(per_cycle.keys()):
                m, s, n = per_cycle[c]
                w.writerow([fkey, "proportional", c, f"{m:.6f}", f"{s:.6f}", n])
    print(f"  wrote {agg_path}")

    # === Statistics (per metric) ===
    print("\n[Brecha A v2] Statistics — binary metric")
    stats_main_b: dict[str, dict] = {}
    for strat, per_cycle in agg_main_b.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        reg = _linear_regression(cs, means)
        tau, p = _mann_kendall(means)
        stats_main_b[strat] = {"regression": reg, "mk_tau": tau, "mk_p": p}
        print(f"  [bin] {strat}: slope={reg['slope']:.4f} p={reg['p_value']:.3e} τ={tau:.3f} p_mk={p:.3e}")

    print("\n[Brecha A v2] Statistics — proportional metric")
    stats_main_p: dict[str, dict] = {}
    for strat, per_cycle in agg_main_p.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        reg = _linear_regression(cs, means)
        tau, p = _mann_kendall(means)
        stats_main_p[strat] = {"regression": reg, "mk_tau": tau, "mk_p": p}
        print(f"  [prop] {strat}: slope={reg['slope']:.4f} p={reg['p_value']:.3e} τ={tau:.3f} p_mk={p:.3e}")

    stats_floor_b: dict[str, dict] = {}
    for fkey, per_cycle in agg_floor_b.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        reg = _linear_regression(cs, means)
        tau, p = _mann_kendall(means)
        stats_floor_b[fkey] = {"regression": reg, "mk_tau": tau, "mk_p": p}

    stats_floor_p: dict[str, dict] = {}
    for fkey, per_cycle in agg_floor_p.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        reg = _linear_regression(cs, means)
        tau, p = _mann_kendall(means)
        stats_floor_p[fkey] = {"regression": reg, "mk_tau": tau, "mk_p": p}

    # Kruskal-Wallis between strategies (final cum_payoff, both metrics)
    by_strat_b: dict[str, list[float]] = {}
    by_strat_p: dict[str, list[float]] = {}
    for s in all_summaries:
        if s.trust_floor != 0.0:
            continue
        by_strat_b.setdefault(s.strategy, []).append(s.cum_payoff_binary_final)
        by_strat_p.setdefault(s.strategy, []).append(s.cum_payoff_proportional_final)
    if all(len(v) > 0 for v in by_strat_b.values()):
        kw_h_b, kw_p_b = stats.kruskal(*[by_strat_b[s] for s in STRATEGIES_MAIN])
    else:
        kw_h_b, kw_p_b = float("nan"), float("nan")
    if all(len(v) > 0 for v in by_strat_p.values()):
        kw_h_p, kw_p_p = stats.kruskal(*[by_strat_p[s] for s in STRATEGIES_MAIN])
    else:
        kw_h_p, kw_p_p = float("nan"), float("nan")
    print(f"\n  KW binary:       H={kw_h_b:.3f} p={kw_p_b:.3e}")
    print(f"  KW proportional: H={kw_h_p:.3f} p={kw_p_p:.3e}")

    # === Plots ===
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 9), sharex=True)
    for strat, per_cycle in agg_main_b.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        axes[0].plot(cs, means, label=strat, linewidth=1.5)
    axes[0].set_ylabel("Mean payoff per cycle (binary)")
    axes[0].set_title("Brecha A — Attacker payoff over cycles")
    axes[0].legend(loc="best", fontsize=9)
    axes[0].grid(True, alpha=0.3)
    for strat, per_cycle in agg_main_p.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        axes[1].plot(cs, means, label=strat, linewidth=1.5)
    axes[1].set_xlabel("Cycle")
    axes[1].set_ylabel("Mean payoff per cycle (proportional)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best", fontsize=9)
    fig.tight_layout()
    p1 = os.path.join(OUT_DIR, "plot_payoff_decay.png")
    fig.savefig(p1, dpi=120, metadata={"Software": ""})
    plt.close(fig)
    print(f"  wrote {p1}")

    fig, axes = plt.subplots(2, 1, figsize=(10, 9), sharex=True)
    for fkey, per_cycle in agg_floor_b.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        axes[0].plot(cs, means, label=fkey, linewidth=1.5)
    axes[0].set_ylabel("Mean payoff per cycle (binary)")
    axes[0].set_title("Brecha A — Floor sensitivity (inflator focal)")
    axes[0].legend(loc="best", fontsize=9)
    axes[0].grid(True, alpha=0.3)
    for fkey, per_cycle in agg_floor_p.items():
        cs = sorted(per_cycle.keys())
        means = [per_cycle[c][0] for c in cs]
        axes[1].plot(cs, means, label=fkey, linewidth=1.5)
    axes[1].set_xlabel("Cycle")
    axes[1].set_ylabel("Mean payoff per cycle (proportional)")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="best", fontsize=9)
    fig.tight_layout()
    p2 = os.path.join(OUT_DIR, "plot_floor_sensitivity.png")
    fig.savefig(p2, dpi=120, metadata={"Software": ""})
    plt.close(fig)
    print(f"  wrote {p2}")

    # === summary.md ===
    summary_path = os.path.join(OUT_DIR, "summary.md")
    with open(summary_path, "w") as f:
        f.write("# Brecha A — Antifragility Decay (dual-metric)\n\n")
        f.write(f"Total runs: {len(all_summaries)}\n\n")
        f.write(f"Wall time: {elapsed_total:.1f}s\n\n")
        f.write("## Per-strategy means (final cumulative payoff)\n\n")
        f.write("### Binary metric\n\n")
        f.write("| Strategy | n | mean | std | min | max |\n")
        f.write("|---|---|---|---|---|---|\n")
        for s in STRATEGIES_MAIN:
            vals = by_strat_b.get(s, [])
            if not vals:
                continue
            arr = np.asarray(vals)
            f.write(f"| {s} | {len(arr)} | {arr.mean():.3f} | {arr.std():.3f} | "
                    f"{arr.min():.3f} | {arr.max():.3f} |\n")
        f.write("\n### Proportional metric\n\n")
        f.write("| Strategy | n | mean | std | min | max |\n")
        f.write("|---|---|---|---|---|---|\n")
        for s in STRATEGIES_MAIN:
            vals = by_strat_p.get(s, [])
            if not vals:
                continue
            arr = np.asarray(vals)
            f.write(f"| {s} | {len(arr)} | {arr.mean():.3f} | {arr.std():.3f} | "
                    f"{arr.min():.3f} | {arr.max():.3f} |\n")

        f.write("\n## Floor sensitivity (inflator focal)\n\n")
        f.write("### Binary\n\n")
        f.write("| τ_floor | n | mean cum_payoff | std |\n")
        f.write("|---|---|---|---|\n")
        for floor in FLOOR_VALUES:
            vals = [s.cum_payoff_binary_final for s in all_summaries
                    if s.strategy == FLOOR_STRATEGY and s.trust_floor == floor]
            if not vals:
                continue
            arr = np.asarray(vals)
            f.write(f"| {floor} | {len(arr)} | {arr.mean():.3f} | {arr.std():.3f} |\n")
        f.write("\n### Proportional\n\n")
        f.write("| τ_floor | n | mean cum_payoff | std |\n")
        f.write("|---|---|---|---|\n")
        for floor in FLOOR_VALUES:
            vals = [s.cum_payoff_proportional_final for s in all_summaries
                    if s.strategy == FLOOR_STRATEGY and s.trust_floor == floor]
            if not vals:
                continue
            arr = np.asarray(vals)
            f.write(f"| {floor} | {len(arr)} | {arr.mean():.3f} | {arr.std():.3f} |\n")
    print(f"  wrote {summary_path}")

    # === stats.md ===
    stats_path = os.path.join(OUT_DIR, "stats.md")
    with open(stats_path, "w") as f:
        f.write("# Brecha A — Statistical analysis (dual-metric)\n\n")

        for label, stats_main, kw_h, kw_pv in [
            ("Binary metric", stats_main_b, kw_h_b, kw_p_b),
            ("Proportional metric", stats_main_p, kw_h_p, kw_p_p),
        ]:
            f.write(f"## {label}\n\n")
            f.write("### Linear regression: cycle vs mean_payoff (per strategy)\n\n")
            f.write("| Strategy | slope | intercept | p-value | R² | MK τ | MK p-value |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for strat in STRATEGIES_MAIN:
                d = stats_main[strat]
                r = d["regression"]
                f.write(f"| {strat} | {r['slope']:.4f} | {r['intercept']:.4f} | "
                        f"{r['p_value']:.3e} | {r['r_squared']:.3f} | "
                        f"{d['mk_tau']:.3f} | {d['mk_p']:.3e} |\n")
            f.write("\n### Kruskal-Wallis: final cum_payoff between strategies\n\n")
            f.write(f"H = {kw_h:.3f}, p = {kw_pv:.3e}\n\n")

        for label, stats_floor in [
            ("Binary metric", stats_floor_b),
            ("Proportional metric", stats_floor_p),
        ]:
            f.write(f"## Floor sensitivity — {label}\n\n")
            f.write("| τ_floor | slope | intercept | p-value | R² | MK τ | MK p-value |\n")
            f.write("|---|---|---|---|---|---|---|\n")
            for floor in FLOOR_VALUES:
                fkey = f"floor_{floor}"
                d = stats_floor[fkey]
                r = d["regression"]
                f.write(f"| {floor} | {r['slope']:.4f} | {r['intercept']:.4f} | "
                        f"{r['p_value']:.3e} | {r['r_squared']:.3f} | "
                        f"{d['mk_tau']:.3f} | {d['mk_p']:.3e} |\n")
            f.write("\n")

        # Hypothesis verdicts (BOTH metrics)
        adv = ["inflator", "underreporter", "mixed", "burst_recovery"]
        f.write("## Hypothesis verdicts\n\n")
        for label, stats_main, stats_floor in [
            ("binary", stats_main_b, stats_floor_b),
            ("proportional", stats_main_p, stats_floor_p),
        ]:
            f.write(f"### Under {label} metric\n\n")
            f.write("**H_A1 (Mann-Kendall monotonic decay per adversarial):**\n\n")
            for s in adv:
                d = stats_main[s]
                conf = (d["mk_tau"] < 0 and d["mk_p"] < 0.05)
                f.write(f"- {s}: {'✓ confirmed' if conf else '✗ rejected'} "
                        f"(τ={d['mk_tau']:.3f}, p={d['mk_p']:.3e})\n")
            f.write("\n**H_A2 (linear slope < 0 with p < 0.05):**\n\n")
            for s in adv:
                d = stats_main[s]["regression"]
                conf = d["slope"] < 0 and d["p_value"] < 0.05
                f.write(f"- {s}: {'✓ confirmed' if conf else '✗ rejected'} "
                        f"(slope={d['slope']:.4f}, p={d['p_value']:.3e})\n")
            f.write("\n**H_A3 (Greedy baseline shows no decay):**\n\n")
            gr = stats_main["greedy"]["regression"]
            gr_d = stats_main["greedy"]
            h3 = (gr["slope"] >= 0
                  or gr["p_value"] >= 0.05
                  or abs(gr["slope"]) < 0.001)
            f.write(f"- greedy: {'✓ confirmed (no decay)' if h3 else '✗ rejected (decay present)'} "
                    f"(slope={gr['slope']:.4f}, p={gr['p_value']:.3e}, τ={gr_d['mk_tau']:.3f})\n")
            f.write("\n**H_A4 (τ_floor relaxes decay):**\n\n")
            slopes = [stats_floor[f"floor_{fl}"]["regression"]["slope"] for fl in FLOOR_VALUES]
            f.write(f"- slopes by floor: {dict(zip(FLOOR_VALUES, [f'{x:.4f}' for x in slopes]))}\n")
            mono = all(slopes[i] <= slopes[i + 1] for i in range(len(slopes) - 1))
            range_slopes = max(slopes) - min(slopes)
            f.write(f"- range of slopes: {range_slopes:.4f}\n")
            f.write(f"- decay relaxes monotonically with floor: "
                    f"{'✓ confirmed' if mono and range_slopes > 1e-4 else '✗ flat or non-monotonic'}\n\n")

    print(f"  wrote {stats_path}")
    print(f"\n[Brecha A v2] DONE. {elapsed_total:.1f}s total.")


if __name__ == "__main__":
    main()
