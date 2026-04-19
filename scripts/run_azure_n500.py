"""Orchestrate the Paper 1 v4 N=500 benchmark across Azure Container Instances.

Fan-out:
  25 cells = (2 scenarios × 3 networks × {5,4} agent_types) − 2 orca+lora_mesh skips
  Each cell runs inside its own ACI container group with N seeds (default 500).
  Per-cell CellResult JSONs land on a shared Azure Files share.

Fan-in:
  Once every container group reaches a terminal state, we download the JSONs
  and aggregate them into the standard ``results/paper1_v4_benchmark_N{N}.json``
  and ``.md`` artefacts using the same formatter the local benchmark uses.

Assumed infra (created in PASO A/B of the sprint):
  - Resource group ``maz3-paper1-rg`` in ``mexicocentral``
  - ACR ``roch3maz3paper1`` with image ``paper1v4:latest``
  - Current subscription set to the sprint subscription

The script creates on demand:
  - Storage account + file share for /results mount
  - ACR admin credentials (enables admin user if needed)
  - 25 container groups named ``c-{scenario}-{network}-{agent}``

Usage:
  python -m scripts.run_azure_n500 --dry-run
  python -m scripts.run_azure_n500 --n 500
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from benchmarks.paper1_v4_benchmark import (  # noqa: E402
    AGENT_TYPES_BY_SCENARIO,
    NETWORK_PROFILES,
    CellResult,
    format_results_markdown,
)


# --- Defaults --------------------------------------------------------------
# All match the infra created in PASO A/B. Override via CLI flags if needed.
DEFAULT_SUBSCRIPTION = "310f8566-79b6-46b8-bd4c-98cc2358b5b8"
DEFAULT_RG = "maz3-paper1-rg"
DEFAULT_LOCATION = "mexicocentral"
DEFAULT_REGISTRY = "roch3maz3paper1"
DEFAULT_IMAGE = "roch3maz3paper1.azurecr.io/paper1v4:latest"
DEFAULT_STORAGE_ACCOUNT = "roch3maz3paper1store"
DEFAULT_SHARE = "results"
DEFAULT_CPU = 1
DEFAULT_MEMORY_GB = 1.5

# (agent_type, network) pairs skipped by the benchmark (matches the local runner).
SKIP_CELLS = {("orca", "lora_mesh")}


@dataclass(frozen=True)
class Cell:
    scenario: str
    network: str
    agent_type: str

    @property
    def container_name(self) -> str:
        return (
            f"c-{self.scenario.replace('_', '-')}-"
            f"{self.network.replace('_', '-')}-"
            f"{self.agent_type.replace('_', '-')}"
        )

    @property
    def output_filename(self) -> str:
        return f"{self.scenario}_{self.network}_{self.agent_type}.json"


def build_cells() -> List[Cell]:
    cells: List[Cell] = []
    for scenario, agents in AGENT_TYPES_BY_SCENARIO.items():
        for network in NETWORK_PROFILES:
            for agent in agents:
                if (agent, network) in SKIP_CELLS:
                    continue
                cells.append(Cell(scenario, network, agent))
    return cells


# --- az helpers ------------------------------------------------------------

def _az(*args: str, capture: bool = False, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["az", *args]
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def ensure_acr_admin(registry: str) -> Tuple[str, str]:
    _az("acr", "update", "-n", registry, "--admin-enabled", "true", "-o", "none")
    cp = _az("acr", "credential", "show", "-n", registry, "-o", "json", capture=True)
    creds = json.loads(cp.stdout)
    return creds["username"], creds["passwords"][0]["value"]


def ensure_storage(resource_group: str, location: str,
                   account: str, share: str) -> str:
    exists = subprocess.run(
        ["az", "storage", "account", "show",
         "--name", account, "--resource-group", resource_group, "-o", "none"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists:
        print(f"  creating storage account {account} in {location}...")
        _az("storage", "account", "create",
            "--name", account, "--resource-group", resource_group,
            "--location", location, "--sku", "Standard_LRS",
            "--kind", "StorageV2", "-o", "none")

    key_cp = _az("storage", "account", "keys", "list",
                 "--resource-group", resource_group,
                 "--account-name", account, "-o", "json", capture=True)
    key = json.loads(key_cp.stdout)[0]["value"]

    _az("storage", "share", "create",
        "--name", share, "--account-name", account,
        "--account-key", key, "-o", "none")
    return key


def launch_cell(cell: Cell, *, n_runs: int, seed_base: int,
                resource_group: str, location: str, image: str,
                registry: str, registry_user: str, registry_pass: str,
                storage_account: str, storage_key: str, share: str) -> None:
    env_vars = [
        f"SCENARIO={cell.scenario}",
        f"NETWORK_PROFILE={cell.network}",
        f"AGENT_TYPE={cell.agent_type}",
        f"N_RUNS={n_runs}",
        f"SEED_BASE={seed_base}",
        f"OUTPUT_FILE=/results/{cell.output_filename}",
    ]
    cmd = [
        "az", "container", "create",
        "--resource-group", resource_group,
        "--name", cell.container_name,
        "--image", image,
        "--location", location,
        "--os-type", "Linux",
        "--cpu", str(DEFAULT_CPU),
        "--memory", str(DEFAULT_MEMORY_GB),
        "--restart-policy", "Never",
        "--registry-login-server", f"{registry}.azurecr.io",
        "--registry-username", registry_user,
        "--registry-password", registry_pass,
        "--azure-file-volume-account-name", storage_account,
        "--azure-file-volume-account-key", storage_key,
        "--azure-file-volume-share-name", share,
        "--azure-file-volume-mount-path", "/results",
        "--environment-variables", *env_vars,
        "--no-wait",
        "-o", "none",
    ]
    subprocess.run(cmd, check=True)


def wait_for_all(cells: List[Cell], resource_group: str, *,
                 poll_interval: float = 15.0,
                 timeout_s: float = 3600.0) -> Dict[Cell, str]:
    pending = set(cells)
    terminal: Dict[Cell, str] = {}
    start = time.time()
    last_log = 0.0
    while pending:
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Timed out waiting for {len(pending)} container(s): "
                f"{[c.container_name for c in pending]}"
            )
        for cell in list(pending):
            cp = subprocess.run(
                ["az", "container", "show",
                 "--resource-group", resource_group,
                 "--name", cell.container_name,
                 "--query", "instanceView.state", "-o", "tsv"],
                capture_output=True, text=True,
            )
            state = (cp.stdout or "").strip()
            if state in ("Succeeded", "Failed"):
                terminal[cell] = state
                pending.discard(cell)
                elapsed = (time.time() - start) / 60.0
                print(f"  [{elapsed:5.1f} min] {state:9s}  {cell.container_name}")
        if pending:
            now = time.time()
            if now - last_log > 60.0:
                elapsed = (now - start) / 60.0
                print(f"  [{elapsed:5.1f} min] {len(pending)} still pending...")
                last_log = now
            time.sleep(poll_interval)
    return terminal


def download_results(cells: List[Cell], *, storage_account: str,
                     storage_key: str, share: str, dest_dir: str) -> List[str]:
    os.makedirs(dest_dir, exist_ok=True)
    paths: List[str] = []
    for cell in cells:
        local = os.path.join(dest_dir, cell.output_filename)
        subprocess.run(
            ["az", "storage", "file", "download",
             "--account-name", storage_account,
             "--account-key", storage_key,
             "--share-name", share,
             "--path", cell.output_filename,
             "--dest", local, "-o", "none"],
            check=True,
        )
        paths.append(local)
    return paths


def aggregate_results(cells: List[Cell], json_paths: List[str], *,
                      n_runs: int, output_dir: str) -> Tuple[str, str]:
    # Keep the same scenario / network / agent_type order the local benchmark
    # produces so the N500 artefact is diffable against the N50 one.
    path_by_cell = {c: p for c, p in zip(cells, json_paths)}
    results: List[CellResult] = []
    for cell in cells:
        with open(path_by_cell[cell]) as f:
            d = json.load(f)
        results.append(CellResult(**d))

    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"paper1_v4_benchmark_N{n_runs}.json")
    with open(json_path, "w") as f:
        json.dump([asdict(r) for r in results], f, indent=2)
    md_path = os.path.join(output_dir, f"paper1_v4_benchmark_N{n_runs}.md")
    with open(md_path, "w") as f:
        f.write(format_results_markdown(results))
    return json_path, md_path


def cleanup_containers(cells: List[Cell], resource_group: str) -> None:
    for cell in cells:
        subprocess.run(
            ["az", "container", "delete",
             "--resource-group", resource_group,
             "--name", cell.container_name,
             "--yes", "-o", "none"],
            check=False,
        )


# --- smoke test ------------------------------------------------------------

def run_smoke_test(args: argparse.Namespace) -> int:
    """End-to-end validation with one cell at N=2.

    Runs bottleneck/ideal/syncference on a dedicated container name
    ("smoke-*") so it never collides with production cell names or files.
    Fetches the container logs, downloads the JSON, runs schema checks, and
    cleans up both the container and the remote file.

    Returns an exit code: 0 on pass, non-zero on any failure.
    """
    _az("account", "set", "--subscription", args.subscription)

    print("[smoke] Ensuring ACR admin user...")
    reg_user, reg_pass = ensure_acr_admin(args.registry)

    print(f"[smoke] Ensuring storage account {args.storage_account} "
          f"+ share {args.share}...")
    storage_key = ensure_storage(args.resource_group, args.location,
                                 args.storage_account, args.share)

    cell = Cell("bottleneck", "ideal", "syncference")
    container_name = f"smoke-{cell.container_name}"
    output_filename = f"smoke_{cell.output_filename}"
    n_runs = 2
    seed_base = 42

    # Best-effort cleanup of any leftover smoke container from a previous run.
    subprocess.run(
        ["az", "container", "delete",
         "--resource-group", args.resource_group,
         "--name", container_name, "--yes", "-o", "none"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )

    t0 = time.perf_counter()
    env_vars = [
        f"SCENARIO={cell.scenario}",
        f"NETWORK_PROFILE={cell.network}",
        f"AGENT_TYPE={cell.agent_type}",
        f"N_RUNS={n_runs}",
        f"SEED_BASE={seed_base}",
        f"OUTPUT_FILE=/results/{output_filename}",
    ]
    print(f"[smoke] Creating container {container_name} (N={n_runs})...")
    subprocess.run([
        "az", "container", "create",
        "--resource-group", args.resource_group,
        "--name", container_name,
        "--image", args.image,
        "--location", args.location,
        "--os-type", "Linux",
        "--cpu", str(DEFAULT_CPU),
        "--memory", str(DEFAULT_MEMORY_GB),
        "--restart-policy", "Never",
        "--registry-login-server", f"{args.registry}.azurecr.io",
        "--registry-username", reg_user,
        "--registry-password", reg_pass,
        "--azure-file-volume-account-name", args.storage_account,
        "--azure-file-volume-account-key", storage_key,
        "--azure-file-volume-share-name", args.share,
        "--azure-file-volume-mount-path", "/results",
        "--environment-variables", *env_vars,
        "--no-wait",
        "-o", "none",
    ], check=True)

    deadline = t0 + 300.0
    state = "Unknown"
    while time.perf_counter() < deadline:
        cp = subprocess.run(
            ["az", "container", "show",
             "--resource-group", args.resource_group,
             "--name", container_name,
             "--query", "instanceView.state", "-o", "tsv"],
            capture_output=True, text=True,
        )
        state = (cp.stdout or "").strip() or "Unknown"
        print(f"  [{time.perf_counter()-t0:5.1f}s] state={state}")
        if state in ("Succeeded", "Failed"):
            break
        time.sleep(10)
    elapsed = time.perf_counter() - t0

    print("\n[smoke] Container logs:")
    print("=" * 70)
    logs_cp = subprocess.run(
        ["az", "container", "logs",
         "--resource-group", args.resource_group,
         "--name", container_name],
        capture_output=True, text=True,
    )
    print(logs_cp.stdout, end="" if logs_cp.stdout.endswith("\n") else "\n")
    if logs_cp.stderr.strip():
        print("[logs-stderr]", logs_cp.stderr.strip())
    print("=" * 70)

    if state != "Succeeded":
        print(f"\n[smoke] FAIL: container terminal state = {state!r}")
        print("[smoke] Keeping container in place for post-mortem. Delete "
              "manually when done:")
        print(f"  az container delete -g {args.resource_group} "
              f"-n {container_name} --yes")
        return 3

    local_dir = os.path.join(args.output_dir, "_smoke_test")
    os.makedirs(local_dir, exist_ok=True)
    local = os.path.join(local_dir, output_filename)
    if os.path.exists(local):
        os.unlink(local)
    print(f"\n[smoke] Downloading {output_filename} → {local}")
    subprocess.run([
        "az", "storage", "file", "download",
        "--account-name", args.storage_account,
        "--account-key", storage_key,
        "--share-name", args.share,
        "--path", output_filename,
        "--dest", local, "-o", "none",
    ], check=True)

    with open(local) as f:
        content = f.read()
    print("\n[smoke] Downloaded JSON:")
    print("-" * 70)
    print(content)
    print("-" * 70)

    data = json.loads(content)
    checks = [
        ("scenario == 'bottleneck'", data.get("scenario") == "bottleneck"),
        ("network  == 'ideal'",      data.get("network") == "ideal"),
        ("agent_type == 'syncference'", data.get("agent_type") == "syncference"),
        ("n_runs == 2",              data.get("n_runs") == 2),
        ("hp_mean is number",        isinstance(data.get("hp_mean"), (int, float))),
        ("0 <= hp_mean <= 1",        0.0 <= float(data.get("hp_mean", -1)) <= 1.0),
        ("convergence_ms_mean > 0",  float(data.get("convergence_ms_mean", 0)) > 0.0),
        ("task_completion_mean in [0,1]",
         0.0 <= float(data.get("task_completion_mean", -1)) <= 1.0),
    ]
    print("\n[smoke] Schema checks:")
    all_ok = True
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            all_ok = False

    print("\n[smoke] Cleanup: deleting container + remote file...")
    subprocess.run([
        "az", "container", "delete",
        "--resource-group", args.resource_group,
        "--name", container_name, "--yes", "-o", "none",
    ], check=False)
    subprocess.run([
        "az", "storage", "file", "delete",
        "--account-name", args.storage_account,
        "--account-key", storage_key,
        "--share-name", args.share,
        "--path", output_filename, "-o", "none",
    ], check=False)

    # ACI pricing (West/Central US ballpark, ~same for mexicocentral):
    # $0.0000012/vCPU-s + $0.0000013/GiB-s. Storage/ACR ~cents, omit.
    cost = (DEFAULT_CPU * elapsed * 0.0000012
            + DEFAULT_MEMORY_GB * elapsed * 0.0000013)
    print(f"\n[smoke] Wall clock: {elapsed:.1f}s. "
          f"Estimated ACI cost: ${cost:.4f}")

    if all_ok:
        print("[smoke] PASS")
        return 0
    print("[smoke] FAIL: one or more schema checks failed")
    return 3


# --- main ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=500, help="seeds per cell")
    parser.add_argument("--seed-base", type=int, default=42)
    parser.add_argument("--subscription", default=DEFAULT_SUBSCRIPTION)
    parser.add_argument("--resource-group", default=DEFAULT_RG)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--image", default=DEFAULT_IMAGE)
    parser.add_argument("--storage-account", default=DEFAULT_STORAGE_ACCOUNT)
    parser.add_argument("--share", default=DEFAULT_SHARE)
    parser.add_argument("--output-dir", default="results")
    parser.add_argument("--dry-run", action="store_true",
                        help="enumerate cells and print plan; no Azure calls")
    parser.add_argument("--smoke-test", action="store_true",
                        help="run a single cell (bottleneck/ideal/syncference) "
                             "at N=2 end-to-end to validate the pipeline")
    parser.add_argument("--keep-containers", action="store_true",
                        help="skip container group deletion at the end")
    parser.add_argument("--timeout-min", type=float, default=60.0,
                        help="hard cap waiting for all containers to terminate")
    args = parser.parse_args()

    if args.smoke_test:
        sys.exit(run_smoke_test(args))

    cells = build_cells()
    print(f"[orchestrator] N={args.n}, seed_base={args.seed_base}, cells={len(cells)}")
    for i, c in enumerate(cells, 1):
        print(f"  [{i:2d}/{len(cells)}] {c.scenario:<17s} | "
              f"{c.network:<15s} | {c.agent_type:<14s} → {c.container_name}")

    if args.dry_run:
        print()
        print("[dry-run] Plan:")
        print(f"  - subscription:    {args.subscription}")
        print(f"  - resource group:  {args.resource_group} ({args.location})")
        print(f"  - ACR image:       {args.image}")
        print(f"  - storage account: {args.storage_account}")
        print(f"  - file share:      {args.share}")
        print(f"  - per-container:   {DEFAULT_CPU} vCPU, {DEFAULT_MEMORY_GB} GiB")
        print(f"  - output dir:      {args.output_dir}")
        print(f"  - timeout:         {args.timeout_min:.0f} min")

        print("\n[dry-run] Per-cell environment variables:")
        for i, c in enumerate(cells, 1):
            print(f"  [{i:2d}/{len(cells)}] {c.container_name}")
            print(f"        SCENARIO={c.scenario} "
                  f"NETWORK_PROFILE={c.network} AGENT_TYPE={c.agent_type}")
            print(f"        N_RUNS={args.n} SEED_BASE={args.seed_base} "
                  f"OUTPUT_FILE=/results/{c.output_filename}")

        print("\n[dry-run] Azure resources:")
        print(f"  - Reused (already exist from PASO A/B):")
        print(f"      · resource group        {args.resource_group}")
        print(f"      · ACR                   {args.registry}")
        print(f"      · image                 {args.image}")
        print(f"  - Ensured (created if missing):")
        print(f"      · storage account       {args.storage_account} "
              "(Standard_LRS, StorageV2)")
        print(f"      · file share            {args.share}")
        print(f"  - Created per run (deleted after aggregation):")
        print(f"      · {len(cells)} container groups (c-*)")
        print(f"      · {len(cells)} per-cell JSONs on the share "
              "(left in place for re-aggregation)")

        # Timing model ----------------------------------------------------
        # Reference points we trust:
        #   · Local N=50 sequential wall clock: 450s over 25 cells → 18s/cell
        #     average → ~0.36 s/run.
        #   · Azure smoke N=2 (bottleneck/ideal/syncference) total: 35.3s.
        #     Breakdown: ~13s image pull + container start, ~1s compute (2
        #     runs × 0.36s = 0.72s), ~21s mount/stop/dispose overhead.
        # Project per-cell wall clock at N=500:
        #     compute = 500 × 0.36s = 180s
        #     azure overhead ≈ 35s (smoke minus the 0.7s of compute it did)
        #     per-cell wall = ~215s  (~3.6 min)
        runs_per_cell = args.n
        per_run_s = 0.36
        compute_s = runs_per_cell * per_run_s
        aci_overhead_s = 35.0
        per_cell_wall_s = compute_s + aci_overhead_s
        # All 25 launched with --no-wait concurrently. The bottleneck is the
        # slowest cell; staggered launches add maybe 15-25s but dwarfed by
        # the per-cell duration. We assume wall clock ≈ per-cell wall.
        parallel_wall_s = per_cell_wall_s
        print("\n[dry-run] Wall-clock estimate (based on local N=50 + smoke):")
        print(f"  - per-run compute:         {per_run_s:.2f}s")
        print(f"  - per-cell compute (N={runs_per_cell}):     "
              f"{compute_s:.0f}s  (= N × per-run)")
        print(f"  - per-cell Azure overhead: {aci_overhead_s:.0f}s  "
              "(image pull + start + mount + stop, from smoke)")
        print(f"  - per-cell total:          {per_cell_wall_s:.0f}s  "
              f"(~{per_cell_wall_s/60.0:.1f} min)")
        print(f"  - {len(cells)} cells in parallel:    ~{parallel_wall_s:.0f}s "
              f"(~{parallel_wall_s/60.0:.1f} min) wall clock")

        # Cost model ------------------------------------------------------
        # ACI Linux pricing (Azure public, same ballpark for mexicocentral):
        #   vCPU-second:   $0.0000012
        #   GiB-second:    $0.0000013
        # Storage (Standard_LRS file share): per-GB-month + per-txn, both
        #   negligible for <1 MB and <100 transactions in a single run.
        vcpu_rate = 0.0000012
        gib_rate = 0.0000013
        per_s = DEFAULT_CPU * vcpu_rate + DEFAULT_MEMORY_GB * gib_rate
        per_container_cost = per_s * per_cell_wall_s
        total_cost = per_container_cost * len(cells)
        print("\n[dry-run] Cost estimate (ACI Linux, public pricing):")
        print(f"  - vCPU-second:             ${vcpu_rate:.7f}")
        print(f"  - GiB-second:              ${gib_rate:.7f}")
        print(f"  - per-container-second:    ${per_s:.8f} "
              f"(= {DEFAULT_CPU} × vCPU + {DEFAULT_MEMORY_GB} × GiB)")
        print(f"  - per-container at {per_cell_wall_s:.0f}s:   "
              f"${per_container_cost:.4f}")
        print(f"  - {len(cells)} containers total:     "
              f"${total_cost:.4f}")
        print(f"  - storage + ACR egress:    < $0.001 (negligible)")
        print(f"  - TOTAL estimated:         ~${total_cost + 0.001:.3f}")
        print(f"  - Budget cap:              $30.00 "
              f"(this run = {(total_cost + 0.001) / 30.0 * 100:.3f}% of cap)")

        print("\n[dry-run] No Azure resources will be created.")
        return

    _az("account", "set", "--subscription", args.subscription)

    print("[orchestrator] Ensuring ACR admin user...")
    reg_user, reg_pass = ensure_acr_admin(args.registry)

    print(f"[orchestrator] Ensuring storage account {args.storage_account} "
          f"+ share {args.share}...")
    storage_key = ensure_storage(args.resource_group, args.location,
                                 args.storage_account, args.share)

    print(f"[orchestrator] Launching {len(cells)} ACI container groups...")
    t0 = time.perf_counter()
    for i, cell in enumerate(cells, 1):
        print(f"  launch [{i:2d}/{len(cells)}] {cell.container_name}")
        launch_cell(cell, n_runs=args.n, seed_base=args.seed_base,
                    resource_group=args.resource_group, location=args.location,
                    image=args.image, registry=args.registry,
                    registry_user=reg_user, registry_pass=reg_pass,
                    storage_account=args.storage_account,
                    storage_key=storage_key, share=args.share)

    print("[orchestrator] Waiting for all containers to reach terminal state...")
    terminal = wait_for_all(cells, args.resource_group,
                            timeout_s=args.timeout_min * 60.0)
    succeeded = [c for c in cells if terminal.get(c) == "Succeeded"]
    failed = [c for c in cells if terminal.get(c) != "Succeeded"]
    wall_min = (time.perf_counter() - t0) / 60.0
    print(f"[orchestrator] Terminal after {wall_min:.1f} min: "
          f"{len(succeeded)} succeeded, {len(failed)} failed.")
    for c in failed:
        print(f"  FAILED: {c.container_name} (state={terminal.get(c)!r})")

    if not succeeded:
        print("[orchestrator] No succeeded cells — aborting before aggregation.")
        sys.exit(2)

    print("[orchestrator] Downloading per-cell JSONs...")
    cells_dir = os.path.join(args.output_dir, f"_azure_N{args.n}_cells")
    paths = download_results(succeeded,
                             storage_account=args.storage_account,
                             storage_key=storage_key, share=args.share,
                             dest_dir=cells_dir)

    print(f"[orchestrator] Aggregating {len(paths)} cell results...")
    json_path, md_path = aggregate_results(succeeded, paths,
                                           n_runs=args.n,
                                           output_dir=args.output_dir)
    print(f"  Wrote {json_path}")
    print(f"  Wrote {md_path}")

    if not args.keep_containers:
        print("[orchestrator] Deleting container groups...")
        cleanup_containers(cells, args.resource_group)

    if failed:
        print(f"[orchestrator] Completed with {len(failed)} failed cell(s).")
        sys.exit(1)
    print("[orchestrator] Done.")


if __name__ == "__main__":
    main()
