"""
Brecha B — Architectural Convergence to Axiom (ACS by agent type).

Spec:
  6 agent types × 100 runs × 100 cycles = 60,000 cycle-steps

Each run: Bottleneck with 1 focal agent (the type under test) + 2 Syncference
baselines. Compute ACS for the focal agent post-run.

Hypotheses (reformulated):
  H_B1: Syncference focal mantains ACS > 0.95 sostenido.
  H_B2: Greedy and Adversarial types have ACS significantly lower than Syncference.
  H_B3: Discrimination comes principally from Integrity_extended (not S or T).
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
from experiments.brecha_b.acs_metric import compute_acs


SEED_BASE = 8000
MAX_CYCLES = 100
N_RUNS_PER_TYPE = 100
AGENT_TYPES = [
    "syncference", "greedy", "inflator", "underreporter",
    "mixed", "burst_recovery",
]

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class ACSRunRow:
    run_id: int
    agent_type: str
    seed: int
    supervisability: float
    integrity_extended: float
    traceability: float
    acs: float
    cycles_with_projection: int
    cycles_compliant: int
    cycles_with_detection: int


def _run_single(run_id: int, agent_type: str, seed: int) -> ACSRunRow:
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix=f"brecha_b_{agent_type}_")
    os.close(fd)
    try:
        engine, _ = create_bottleneck_with_focal_agent(
            focal_type=agent_type,
            max_cycles=MAX_CYCLES,
            db_path=db_path,
            jitter_seed=seed,
            activate_after_cycle=5,
        )
        session_id = engine.initialize()
        for _ in range(MAX_CYCLES):
            engine.step()
        focal_id = f"focal_{agent_type}"
        focal_idx = engine._buffer.get_index_for_agent(focal_id)
        engine.finalize()
        if focal_idx is None:
            return ACSRunRow(
                run_id=run_id, agent_type=agent_type, seed=seed,
                supervisability=0.0, integrity_extended=0.0, traceability=0.0,
                acs=0.0, cycles_with_projection=0, cycles_compliant=0,
                cycles_with_detection=0,
            )
        result = compute_acs(
            db_path=db_path,
            session_id=session_id,
            agent_id=focal_id,
            agent_index=focal_idx,
            total_cycles=MAX_CYCLES,
        )
        return ACSRunRow(
            run_id=run_id,
            agent_type=agent_type,
            seed=seed,
            supervisability=result.supervisability,
            integrity_extended=result.integrity_extended,
            traceability=result.traceability,
            acs=result.acs,
            cycles_with_projection=result.cycles_with_projection,
            cycles_compliant=result.cycles_compliant,
            cycles_with_detection=result.cycles_with_detection,
        )
    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass


def _cliffs_delta(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return float("nan")
    a_arr = np.asarray(a)
    b_arr = np.asarray(b)
    greater = (a_arr[:, None] > b_arr[None, :]).sum()
    less = (a_arr[:, None] < b_arr[None, :]).sum()
    return float((greater - less) / (len(a_arr) * len(b_arr)))


def main() -> None:
    t_start = time.time()
    print(f"[Brecha B] Starting at {time.strftime('%H:%M:%S')}")
    print(f"[Brecha B] {len(AGENT_TYPES)} types × {N_RUNS_PER_TYPE} runs × {MAX_CYCLES} cycles")

    all_rows: list[ACSRunRow] = []
    run_id = 0
    for agent_type in AGENT_TYPES:
        t0 = time.time()
        for r in range(N_RUNS_PER_TYPE):
            run_id += 1
            seed = SEED_BASE + run_id
            try:
                row = _run_single(run_id, agent_type, seed)
                all_rows.append(row)
            except Exception as e:
                print(f"  ! run {run_id} {agent_type} failed: {e}")
                continue
        print(f"  {agent_type}: {N_RUNS_PER_TYPE} runs in {time.time() - t0:.1f}s")

    elapsed = time.time() - t_start
    print(f"\n[Brecha B] All runs done in {elapsed:.1f}s")

    # === CSVs ===
    raw_path = os.path.join(OUT_DIR, "raw_runs.csv")
    with open(raw_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(asdict(all_rows[0]).keys()))
        w.writeheader()
        for r in all_rows:
            w.writerow(asdict(r))
    print(f"  wrote {raw_path} ({len(all_rows)} rows)")

    by_type: dict[str, list[ACSRunRow]] = defaultdict(list)
    for r in all_rows:
        by_type[r.agent_type].append(r)

    # Aggregated summary CSV
    agg_path = os.path.join(OUT_DIR, "aggregated.csv")
    with open(agg_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["agent_type", "n", "mean_acs", "ci95_acs",
                    "mean_supervisability", "mean_integrity_ext",
                    "mean_traceability"])
        for at in AGENT_TYPES:
            rs = by_type[at]
            if not rs:
                continue
            acs_arr = np.asarray([r.acs for r in rs])
            sup_arr = np.asarray([r.supervisability for r in rs])
            int_arr = np.asarray([r.integrity_extended for r in rs])
            trc_arr = np.asarray([r.traceability for r in rs])
            ci = 1.96 * acs_arr.std(ddof=1) / math.sqrt(len(acs_arr))
            w.writerow([
                at, len(acs_arr),
                f"{acs_arr.mean():.4f}",
                f"{ci:.4f}",
                f"{sup_arr.mean():.4f}",
                f"{int_arr.mean():.4f}",
                f"{trc_arr.mean():.4f}",
            ])
    print(f"  wrote {agg_path}")

    # === Statistics ===
    print("\n[Brecha B] Statistics...")
    acs_by_type = {at: [r.acs for r in by_type[at]] for at in AGENT_TYPES}
    int_by_type = {at: [r.integrity_extended for r in by_type[at]] for at in AGENT_TYPES}
    sup_by_type = {at: [r.supervisability for r in by_type[at]] for at in AGENT_TYPES}

    # Kruskal-Wallis on ACS across types
    groups = [acs_by_type[at] for at in AGENT_TYPES if acs_by_type[at]]
    if len(groups) >= 2 and all(len(g) > 0 for g in groups):
        kw_h, kw_p = stats.kruskal(*groups)
    else:
        kw_h, kw_p = float("nan"), float("nan")
    print(f"  Kruskal-Wallis (ACS across 6 types): H={kw_h:.3f} p={kw_p:.3e}")

    # Pairwise Mann-Whitney U: Sync vs each other type (Bonferroni-corrected)
    pairwise = {}
    sync_acs = acs_by_type["syncference"]
    n_pairs = len(AGENT_TYPES) - 1
    bonferroni_alpha = 0.05 / n_pairs
    for at in AGENT_TYPES:
        if at == "syncference":
            continue
        other = acs_by_type[at]
        if not sync_acs or not other:
            pairwise[at] = (float("nan"), float("nan"), float("nan"),
                            False)
            continue
        u, p = stats.mannwhitneyu(sync_acs, other, alternative="greater")
        delta = _cliffs_delta(sync_acs, other)
        sig = p < bonferroni_alpha
        pairwise[at] = (float(u), float(p), delta, sig)
        print(f"  Sync > {at}: U={u:.0f} p={p:.3e} delta={delta:.3f} "
              f"sig@bonferroni={sig}")

    # Plots
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Boxplot ACS by type
    fig, ax = plt.subplots(figsize=(10, 6))
    data = [acs_by_type[at] for at in AGENT_TYPES]
    ax.boxplot(data, tick_labels=AGENT_TYPES, showmeans=True)
    ax.set_ylabel("ACS")
    ax.set_title("Brecha B — ACS distribution by agent type (N=100 each)")
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=20)
    fig.tight_layout()
    p1 = os.path.join(OUT_DIR, "plot_acs_by_type.png")
    fig.savefig(p1, dpi=120, metadata={"Software": ""})
    plt.close(fig)
    print(f"  wrote {p1}")

    # Stacked bar of sub-scores: Sup, Int_ext, Trc per type
    fig, ax = plt.subplots(figsize=(10, 6))
    sup_means = [np.mean(sup_by_type[at]) if sup_by_type[at] else 0 for at in AGENT_TYPES]
    int_means = [np.mean(int_by_type[at]) if int_by_type[at] else 0 for at in AGENT_TYPES]
    trc_means = [np.mean([r.traceability for r in by_type[at]])
                 if by_type[at] else 0 for at in AGENT_TYPES]
    x = np.arange(len(AGENT_TYPES))
    width = 0.27
    ax.bar(x - width, sup_means, width, label="Supervisability")
    ax.bar(x, int_means, width, label="Integrity_extended")
    ax.bar(x + width, trc_means, width, label="Traceability")
    ax.set_xticks(x)
    ax.set_xticklabels(AGENT_TYPES, rotation=20)
    ax.set_ylabel("Sub-score (mean)")
    ax.set_title("Brecha B — ACS sub-score discrimination across agent types")
    ax.legend(loc="lower left")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    p2 = os.path.join(OUT_DIR, "plot_integrity_discrimination.png")
    fig.savefig(p2, dpi=120, metadata={"Software": ""})
    plt.close(fig)
    print(f"  wrote {p2}")

    # === summary.md ===
    summary_path = os.path.join(OUT_DIR, "summary.md")
    with open(summary_path, "w") as f:
        f.write("# Brecha B — Architectural Convergence (ACS by agent type)\n\n")
        f.write(f"Total runs: {len(all_rows)}, wall time: {elapsed:.1f}s\n\n")
        f.write("## ACS sub-scores by agent type\n\n")
        f.write("| Agent type | n | mean ACS | 95% CI | mean S | mean I_ext | mean T |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for at in AGENT_TYPES:
            rs = by_type[at]
            if not rs:
                continue
            acs_arr = np.asarray([r.acs for r in rs])
            sup_arr = np.asarray([r.supervisability for r in rs])
            int_arr = np.asarray([r.integrity_extended for r in rs])
            trc_arr = np.asarray([r.traceability for r in rs])
            ci = 1.96 * acs_arr.std(ddof=1) / math.sqrt(len(acs_arr))
            f.write(f"| {at} | {len(acs_arr)} | {acs_arr.mean():.4f} | "
                    f"±{ci:.4f} | {sup_arr.mean():.4f} | "
                    f"{int_arr.mean():.4f} | {trc_arr.mean():.4f} |\n")

    print(f"  wrote {summary_path}")

    # === stats.md ===
    stats_path = os.path.join(OUT_DIR, "stats.md")
    with open(stats_path, "w") as f:
        f.write("# Brecha B — Statistical analysis\n\n")
        f.write("## Kruskal-Wallis: ACS across 6 agent types\n\n")
        f.write(f"H = {kw_h:.3f}, p = {kw_p:.3e}\n\n")
        f.write("## Pairwise Mann-Whitney U: Syncference > each other type\n")
        f.write(f"Bonferroni α = 0.05/{n_pairs} = {bonferroni_alpha:.4f}\n\n")
        f.write("| Comparison | U | p-value | Cliff's δ | Significant @ Bonf |\n")
        f.write("|---|---|---|---|---|\n")
        for at, (u, p, d, sig) in pairwise.items():
            f.write(f"| Sync vs {at} | {u:.0f} | {p:.3e} | {d:.3f} | "
                    f"{'✓' if sig else '✗'} |\n")

        f.write("\n## Hypothesis verdicts\n\n")
        # H_B1: Sync ACS > 0.95
        sync_arr = np.asarray(acs_by_type["syncference"])
        h_b1_conf = sync_arr.mean() > 0.95
        f.write(f"**H_B1 (Sync ACS > 0.95 sustained):** "
                f"{'✓ confirmed' if h_b1_conf else '✗ rejected'} "
                f"(mean = {sync_arr.mean():.4f})\n\n")
        # H_B2: Greedy and adversarials < Sync significantly
        n_lower_sig = sum(1 for at, (_, _, _, sig) in pairwise.items() if sig)
        h_b2_conf = n_lower_sig == n_pairs
        f.write(f"**H_B2 (all non-Sync types ACS significantly lower):** "
                f"{'✓ confirmed' if h_b2_conf else '✗ partial'} "
                f"({n_lower_sig}/{n_pairs} significant @ Bonf)\n\n")
        # H_B3: discrimination via Integrity_extended
        sup_means_arr = np.asarray(sup_means)
        int_means_arr = np.asarray(int_means)
        sup_range = float(sup_means_arr.max() - sup_means_arr.min())
        int_range = float(int_means_arr.max() - int_means_arr.min())
        h_b3_conf = int_range > sup_range
        f.write(f"**H_B3 (Integrity_ext drives discrimination):** "
                f"{'✓ confirmed' if h_b3_conf else '✗ rejected'} "
                f"(I_ext range = {int_range:.3f}, S range = {sup_range:.3f})\n")

    print(f"  wrote {stats_path}")
    print(f"\n[Brecha B] DONE. {elapsed:.1f}s total.")


if __name__ == "__main__":
    main()
