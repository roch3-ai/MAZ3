"""
MAZ3 CLI — python -m maz3

Usage:
  python -m maz3 run --scenario bottleneck --agents 5 --network wifi --seed 42
  python -m maz3 run --scenario intersection --seed 42
  python -m maz3 run --scenario corridor --seed 42
  python -m maz3 run --scenario void_stress --seed 42
  python -m maz3 export --scenario bottleneck --seed 42 --out results/
  python -m maz3 export --table3x3 --seed 42 --out results/
  python -m maz3 version

Commands:
  run     — Run a scenario and print summary to stdout
  export  — Run and write CSV + LaTeX + PNG to --out directory
  version — Print MAZ3 version and exit
"""

from __future__ import annotations

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _cmd_version(args: argparse.Namespace) -> int:
    from roch3.__version__ import __version__
    print(f"MAZ3 v{__version__}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    scenario = args.scenario
    seed = args.seed
    network = args.network
    max_cycles = args.cycles

    print(f"MAZ3 run: scenario={scenario} network={network} seed={seed} cycles={max_cycles}")

    if scenario == "bottleneck":
        from scenarios.bottleneck import create_bottleneck_simulation
        engine, _ = create_bottleneck_simulation(
            agent_types=args.agent_types,
            network_profile=network,
            max_cycles=max_cycles,
            db_path=":memory:",
            jitter_seed=seed,
        )
        engine.initialize()
        hp_vals, d_counts = [], {"D0": 0, "D1": 0, "D2+": 0}
        for _ in range(max_cycles):
            r = engine.step()
            hp_vals.append(r.harmony.h_p)
            for a in r.deference_actions:
                lvl = a.level.value
                key = "D0" if lvl == 0 else ("D1" if lvl == 1 else "D2+")
                d_counts[key] += 1
        engine.finalize()
        avg_hp = sum(hp_vals) / len(hp_vals) if hp_vals else 0.0
        print(f"  avg_H_p:           {avg_hp:.4f}")
        print(f"  min_H_p:           {min(hp_vals):.4f}")
        d = d_counts
        print(f"  deference:         D0={d['D0']} D1={d['D1']} D2+={d['D2+']}")

    elif scenario == "intersection":
        from scenarios.intersection import run_intersection_scenario
        result = run_intersection_scenario(
            agent_types=args.agent_types,
            network_profile=network,
            max_cycles=max_cycles,
            db_path=":memory:",
            jitter_seed=seed,
        )
        print(f"  avg_H_p:           {result.avg_h_p:.4f}")
        print(f"  min_H_p:           {result.min_h_p:.4f}")
        print(f"  collisions:        {result.collisions}")
        print(f"  fairness_index:    {result.fairness_index:.4f}")
        print(f"  resolution_cycles: {result.resolution_cycles}")
        d = result.deference_counts
        print(f"  deference:         D0={d['D0']} D1={d['D1']} D2+={d['D2+']}")

    elif scenario == "corridor":
        from scenarios.corridor import run_corridor_scenario
        result = run_corridor_scenario(
            agent_types=args.agent_types,
            network_profile=network,
            max_cycles=max_cycles,
            db_path=":memory:",
            jitter_seed=seed,
        )
        print(f"  avg_H_p:           {result.avg_h_p:.4f}")
        print(f"  min_H_p:           {result.min_h_p:.4f}")
        print(f"  agents_completed:  {result.agents_completed}/{result.total_agents}")
        print(f"  fairness_index:    {result.fairness_index:.4f}")
        print(f"  D1+/agent:         {result.deference_per_agent:.1f}")
        d = result.deference_counts
        print(f"  deference:         D0={d['D0']} D1={d['D1']} D2+={d['D2+']}")

    elif scenario == "void_stress":
        from scenarios.void_stress import run_void_stress_test
        # void_stress always runs with its fixed agent configuration
        # (5 honest syncference + 1 adversarial inflator). --agent-types is ignored.
        if args.agent_types != "syncference":
            print(f"  Note: --agent-types={args.agent_types!r} ignored for void_stress "
                  f"(always 5 honest + 1 adversarial inflator)")
        result = run_void_stress_test(
            network_profile=network,
            max_cycles=max_cycles,
            db_path=":memory:",
            jitter_seed=seed,
        )
        print(f"  avg_H_p:           {result.avg_h_p:.4f}")
        print(f"  void_pre:          {result.void_fraction_pre_attack:.3f}")
        print(f"  void_post:         {result.void_fraction_post_attack:.3f}")
        print(f"  collapse_detected: {result.collapse_detected}")
        print(f"  detection_latency: {result.detection_latency} cycles")
        print(f"  attacker_trust:    {result.attacker_final_trust}")

    else:
        print(f"Unknown scenario: {scenario!r}", file=sys.stderr)
        return 1

    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from scripts.export_results import export_scenario, export_table3x3

    if args.table3x3:
        export_table3x3(
            seed=args.seed,
            max_cycles=args.cycles,
            out_dir=args.out,
        )
    else:
        export_scenario(
            scenario=args.scenario,
            agent_types=args.agent_types,
            seed=args.seed,
            max_cycles=args.cycles,
            out_dir=args.out,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m maz3",
        description="MAZ3 — Multi-Agent coordination benchmark for sovereign physical systems",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── version ───────────────────────────────────────────────────────────────
    sub.add_parser("version", help="Print MAZ3 version")

    # ── run ───────────────────────────────────────────────────────────────────
    run_p = sub.add_parser("run", help="Run a scenario and print summary")
    run_p.add_argument(
        "--scenario", default="bottleneck",
        choices=["bottleneck", "intersection", "corridor", "void_stress"],
    )
    run_p.add_argument(
        "--agent-types", dest="agent_types", default="syncference",
        choices=["syncference", "mixed", "adversarial", "greedy_all"],
    )
    run_p.add_argument(
        "--network", default="ideal",
        choices=["ideal", "industrial_ethernet", "wifi_warehouse", "lora_mesh"],
    )
    run_p.add_argument("--seed", type=int, default=42)
    run_p.add_argument("--cycles", type=int, default=300)

    # ── export ────────────────────────────────────────────────────────────────
    exp_p = sub.add_parser("export", help="Export CSV + LaTeX + PNG for Paper 1")
    exp_p.add_argument(
        "--scenario", default="bottleneck",
        choices=["bottleneck", "intersection", "corridor", "void_stress"],
    )
    exp_p.add_argument(
        "--agent-types", dest="agent_types", default="syncference",
        choices=["syncference", "mixed", "adversarial", "greedy_all"],
    )
    exp_p.add_argument("--seed", type=int, default=42)
    exp_p.add_argument("--cycles", type=int, default=300)
    exp_p.add_argument("--out", default="results", help="Output directory")
    exp_p.add_argument(
        "--table3x3", action="store_true",
        help="Generate full 3×3 benchmark table",
    )

    args = parser.parse_args()

    # FIX-5: Global seed at CLI entrypoint for full process-level reproducibility.
    # This is the correct place — one process, no concurrent sessions.
    # The engine uses local Random() instances; this covers any other stdlib calls.
    if hasattr(args, "seed") and args.seed is not None:
        import random as _random
        _random.seed(args.seed)
        try:
            import numpy as _np_cli
            _np_cli.random.seed(args.seed)
        except ImportError:
            pass

    if args.command == "version":
        return _cmd_version(args)
    elif args.command == "run":
        return _cmd_run(args)
    elif args.command == "export":
        return _cmd_export(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
