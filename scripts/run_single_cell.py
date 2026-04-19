"""Run a single benchmark cell and write the CellResult as JSON.

Used by the Docker entrypoint for Azure Container Instances: each ACI
task runs exactly one (scenario, network, agent_type) cell with N_RUNS
seeds, then writes its result to a shared Azure Files volume. The
orchestrator aggregates the per-cell JSONs into the N=500 artefact.

The per-cell schema matches one entry of
results/paper1_v4_benchmark_N{N}.json so the orchestrator can
just concatenate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.paper1_v4_benchmark import (  # noqa: E402
    AGENT_TYPES_BY_SCENARIO,
    CYCLES_BY_SCENARIO,
    NETWORK_PROFILES,
    run_cell,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--network", required=True)
    parser.add_argument("--agent-type", required=True)
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.scenario not in AGENT_TYPES_BY_SCENARIO:
        raise SystemExit(f"Unknown scenario: {args.scenario!r}")
    if args.agent_type not in AGENT_TYPES_BY_SCENARIO[args.scenario]:
        raise SystemExit(
            f"Unknown agent_type {args.agent_type!r} for scenario "
            f"{args.scenario!r}. Known: "
            f"{AGENT_TYPES_BY_SCENARIO[args.scenario]}"
        )
    if args.network not in NETWORK_PROFILES:
        raise SystemExit(
            f"Unknown network {args.network!r}. Known: {NETWORK_PROFILES}"
        )

    cycles = CYCLES_BY_SCENARIO[args.scenario]
    print(
        f"[single-cell] {args.scenario} | {args.network} | "
        f"{args.agent_type} | N={args.n} | cycles={cycles}",
        flush=True,
    )

    cell = run_cell(
        args.scenario,
        args.network,
        args.agent_type,
        args.n,
        args.seed_base,
        cycles,
    )

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(asdict(cell), f, indent=2)
    print(f"[single-cell] Wrote {args.output}", flush=True)


if __name__ == "__main__":
    main()
