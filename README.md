# MAZ3 — Empirical Benchmark for Sovereign Multi-Agent Coordination

**Status:** Research benchmark, Apache 2.0
**Tests:** 55 passing across 9 suites
**Version:** 1.0.0 (Paper 1 v4.2)

## What is MAZ3?

Public benchmark for sovereign multi-agent coordination under adversarial and
degraded-network conditions. MAZ3 is the first public benchmark to combine:

- Sub-millisecond algorithmic convergence for n<50 agents
- Adversarial detection latency under 0.01ms
- Architectural sovereignty (no identity leaks across the coordination substrate)
- Physical enforcement of D3/D4 deference levels against malicious agents

Includes pending US provisional patent applications (P3, P4); see the
[Patent Disclosure](#patent-disclosure) section below.

## Reproducing Paper 1 v4.2 Results

Paper 1 v4.2 is pre-registered on OSF:
[**osf.io/kjcwg**](https://osf.io/kjcwg) — DOI:
[10.17605/OSF.IO/KJCWG](https://doi.org/10.17605/OSF.IO/KJCWG).

All aggregated tables and per-cell data from the N=500 benchmark are in
[`results/paper1_v4_benchmark_N500.md`](results/paper1_v4_benchmark_N500.md)
and [`results/paper1_v4_benchmark_N500.json`](results/paper1_v4_benchmark_N500.json).

**Local reproduction (single machine):**

```bash
pip install -r requirements.txt
python -m benchmarks.paper1_v4_benchmark --n 500 --seed-base 42
```

Results land in `results/paper1_v4_benchmark_N500.{json,md}`.

**Azure reproduction (25 parallel container instances, ~40 min wall clock):**

```bash
# Requires: az CLI logged in, a resource group, an ACR, and a storage account.
# Defaults assume the ROCH3 infrastructure (see scripts/run_azure_n500.py).
python scripts/run_azure_n500.py --n 500 --seed-base 42
```

Output is byte-identical to the local run (deterministic seeds +
`numpy==2.4.4` pinned in the Dockerfile).

For the cost-of-sovereignty analysis (Asymmetric_risk scenario) and the
network-dependent behavior in Bottleneck, see Paper 1 v4.2.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run all 9 test suites
for t in test_sovereignty test_paso0_integration test_paso1_simulation \
         test_paso2_multiagent test_paso3_adversarial test_convergence \
         test_safety test_paso5_omniscient test_audit_fixes; do
  python tests/${t}.py
done

# 3×3 benchmark table
python -c "from engine.session import run_benchmark_matrix, print_table; print_table(run_benchmark_matrix())"

# Start API server
python api/server.py
# Then: curl http://localhost:8000/health
#       POST http://localhost:8000/benchmark/run
#       WS   ws://localhost:8000/ws/live
```

## Documentation

- [`docs/SOVEREIGNTY.md`](docs/SOVEREIGNTY.md) — The architectural sovereignty guarantee. Why "sovereignty is architecture, not policy."
- [`docs/AXIOM.md`](docs/AXIOM.md) — The 3 axioms (Supervisability, Integrity, Traceability) and Axiom Seal Lite criteria.
- [`docs/SDK.md`](docs/SDK.md) — Agent SDK contract, wire format, ROS 2 integration patterns.
- [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md) — Differentiation from ROS 2/Nav2, ACAS-X, DARPA OFFSET, Dec-POMDP, ORCA, BFT.

## Requirements

- Python 3.10+
- numpy == 2.4.4 (pinned for reproducibility)
- fastapi ≥ 0.100, uvicorn ≥ 0.23 (for API server only)

## Formal properties (validated empirically)

| Property | Result |
|----------|--------|
| Bounded convergence (n=50) | <0.1ms |
| Graceful degradation (ideal→wifi) | 1.0% relative |
| Monotonic safety | Verified |
| Determinism | 500/500 identical runs (pinned seeds) |
| Adversarial detection latency | <0.01ms |
| Trust degradation (1.0→0.0) | ~10 cycles |
| D3/D4 physical enforcement | Verified vs malicious |
| Sovereignty (no agent_id leaks) | Verified architecturally |

**Axiom Seal Lite:** PASS (5/5 criteria met)

Per-scenario H_p and collision tables are in
[`results/paper1_v4_benchmark_N500.md`](results/paper1_v4_benchmark_N500.md).
See Paper 1 v4.2 for the cost-of-sovereignty analysis.

## Citing MAZ3

```bibtex
@misc{maz3_2026,
  author = {Briones Jara, Gustavo Emmanuel},
  title  = {MAZ3: Empirical Benchmark for Sovereign Multi-Agent Coordination},
  year   = {2026},
  version = {1.0.0},
  organization = {ROCH3},
  url    = {https://github.com/roch3-ai/MAZ3}
}
```

When citing, please include the version number. Benchmark numbers are not
comparable across major versions.

## Patent Disclosure

Includes pending US provisional patent applications:

- P3: Application 64/029,056 (Kinetic Deference, 55 claims)
- P4: Application 64/030,395 (REPUBLIK OS, 75 claims)

Total ROCH3 portfolio: ~194 pending claims across 4 provisional applications.

## License

Apache License 2.0 — see [LICENSE](LICENSE). The patent grant in Section 3
protects implementers; the patent retaliation clause protects ROCH3's pending
claims.

---

*ROCH3 — The TCP/IP of the Physical World*
