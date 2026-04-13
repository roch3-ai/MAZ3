# MAZ3 — Empirical Benchmark for Sovereign Multi-Agent Coordination

**Version:** 1.1.0
**Tests:** 82 passing across 13 suites
**Status:** Production-ready

## What is MAZ3?

MAZ3 is the first public benchmark for **sovereign multi-agent coordination** — measuring how well heterogeneous autonomous agents coordinate in shared physical space without central authority.

It empirically validates P3 (Kinetic Deference, 55 claims) and P4 (REPUBLIK OS, 75 claims) — 130 patent claims filed with the USPTO by ROCH3.

MAZ3 is to physical coordination what Elo is to chess: a metric that didn't exist before, open, reproducible, and the first of its kind.

## Scenarios

| Scenario | Agents | Validates | Key Metric |
|----------|--------|-----------|------------|
| **Bottleneck** | 3, bidirectional narrow corridor | Syncference baseline, Claim 74 | avg H_p vs greedy |
| **Intersection** | 4, uncontrolled 4-way | Claims 43 (constraint relaxation), 73 (quorum-free) | Fairness Index, zero collisions |
| **Corridor** | 6, bidirectional 3m passage | Kinetic Deference D0→D4, Claim 55 (strategy-proof) | D2+ distribution under pressure |
| **Void Stress** | 5 honest + 1 inflator, 30×30 field | VoidIndex, Void Collapse Attack detection | Detection latency, trust penalty |

**Known limitation (documented):** Syncference without Claim 43 (constraint relaxation) active enters symmetric deadlock in 4-way head-on scenarios. This is expected protocol behavior, not a bug — it demonstrates *why* Claim 43 exists.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Run all 13 test suites
python -m pytest tests/ -q   # or use the runner below

# Manual runner (no pytest needed)
python -c "
import sys, os, importlib
sys.path.insert(0, '.')
r = {'pass': 0, 'fail': 0}
for f in sorted(os.listdir('tests')):
    if not f.startswith('test_') or not f.endswith('.py'): continue
    m = importlib.import_module(f'tests.{f[:-3]}')
    for n in sorted(dir(m)):
        fn = getattr(m, n)
        if n.startswith('test_') and callable(fn):
            try: fn(); r['pass'] += 1
            except Exception as e: print(f'FAIL {f}::{n}: {e}'); r['fail'] += 1
print(f\"{r['pass']} passed, {r['fail']} failed\")
"

# CLI
python -m maz3 version
python -m maz3 run --scenario bottleneck --agent-types syncference --seed 42
python -m maz3 run --scenario intersection --seed 42
python -m maz3 run --scenario corridor --seed 42
python -m maz3 run --scenario void_stress --seed 42

# Export data for Paper 1 (CSV + LaTeX + PNG)
python -m maz3 export --scenario bottleneck --seed 42 --out results/
python -m maz3 export --table3x3 --seed 42 --out results/

# 3×3 benchmark table (legacy)
python -c "from engine.session import run_benchmark_matrix, print_table; print_table(run_benchmark_matrix())"

# API server
python api/server.py
```

## Key Results

**Coordination quality (Bottleneck, 200 cycles, seed=42):**

| Agents | Network | avg H_p | min H_p |
|--------|---------|---------|---------|
| Syncference | ideal | 0.975 | 0.944 |
| Mixed | ideal | 0.964 | 0.329 |
| Greedy | ideal | 0.929 | 0.343 |

**Formal properties (empirically validated):**

| Property | Result | Claim |
|----------|--------|-------|
| Bounded convergence (n=50) | <0.1ms | P4 Theorem 1 |
| Graceful degradation (ideal→wifi_warehouse) | ~2% relative | P4 Theorem 3 |
| Monotonic safety | Verified | P4 Theorem 2 |
| Adversarial detection latency | <0.01ms | P3 detection |
| Trust degradation (1.0→0.0) | ~10 cycles | P3 ARGUS |
| D3/D4 physical enforcement | Verified | P3 enforcement |
| Sovereignty (no agent_id leaks) | Verified architecturally | P3/P4 sovereignty |
| Syncference vs Omniscient (Claim 74) | Sync 0.978 > Omni 0.926 | P4 Claim 74 |
| Void Collapse Attack detection | 1 cycle latency | P3 VoidIndex |
| Fairness Index (Syncference, Intersection) | F ≥ 0.96 | P4 Claim 55 |

**Axiom Seal Lite:** PASS (5/5 criteria met)

## Metrics

**Harmony Index H_p:**
H_p(t) = 1 − ((D_spatial^p + D_temporal^p + D_risk^p) / 3)^(1/p), p=3.
- H_p > 0.85: healthy coordination
- H_p ≥ 0.55: attention required
- H_p < 0.55: intervene

**Fairness Index F:**
F = max(0, 1 − std(wait_times) / mean(wait_times)).
F = 1.0: all agents wait equally. F → 0: one agent always waits.
Scale-invariant (uses coefficient of variation).

**Kinetic Deference levels:**
D0 passive monitoring → D1 advisory → D2 speed correction → D3 physical stop → D4 emergency.

## Architecture

```
/roch3          # Core protocol
  mvr.py        # MVR schema (5 fields)
  sovereign_context.py  # SovereignProjectionBuffer + ARGUSTrustChannel
  convergence.py        # Operator Γ (conservative composition)
  harmony.py            # Harmony Index H_p (p=3)
  kinetic_safety.py     # ΔK + D0-D4
  void_index.py         # VoidIndex + Void Collapse Attack
  fairness.py           # Fairness Index F (canonical)
  network_jitter.py     # 4 network profiles
  adversarial_detection.py  # 4 adversarial detectors

/agents         # Reference agents
  reference_syncference.py  # Canonical honest agent
  reference_random.py       # Baseline random
  reference_greedy.py       # Baseline greedy
  adversarial_inflator.py   # Attack: spatial inflation
  adversarial_underreporter.py  # Attack: risk underreporting
  omniscient_coordinator.py # Internal reference (never on leaderboard)

/engine         # Simulation engine
/scenarios      # Bottleneck, Intersection, Corridor, VoidStress
/tests          # 13 suites, 82 tests
/scripts        # export_results.py — CSV + LaTeX + PNG for Paper 1
```

## Documentation

- [`docs/SOVEREIGNTY.md`](docs/SOVEREIGNTY.md) — Sovereignty architecture
- [`docs/AXIOM.md`](docs/AXIOM.md) — 3 axioms + Axiom Seal Lite criteria
- [`docs/SDK.md`](docs/SDK.md) — Agent SDK, wire format, ROS 2 integration
- [`docs/PRIOR_ART.md`](docs/PRIOR_ART.md) — Differentiation from ROS 2/Nav2, ACAS-X, DARPA OFFSET, Dec-POMDP, ORCA, BFT

## Requirements

- Python 3.10+
- numpy ≥ 1.24
- matplotlib ≥ 3.7 (for export PNG only)
- fastapi ≥ 0.100, uvicorn ≥ 0.23 (for API server only)

## Citing MAZ3

```bibtex
@misc{maz3_2026,
  author       = {Adon Roche},
  title        = {MAZ3: Empirical Benchmark for Sovereign Multi-Agent Coordination},
  year         = {2026},
  version      = {1.1.0},
  organization = {ROCH3.com},
  url          = {https://github.com/roch3-ai/MAZ3}
}
```

When citing, include the version number. Benchmark numbers are not comparable across major versions.

## Patent References

- P3: Application 64/029,056 (Kinetic Deference, 55 claims)
- P4: Application 64/030,395 (REPUBLIK OS, 75 claims)


Total ROCH3 portfolio: ~194 claims across 4 provisional applications.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

*ROCH3 — The TCP/IP of the Physical World*
