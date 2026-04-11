# MAZ3 — Empirical Benchmark for ROCH3 Patent Validation

**Status:** Complete (Pasos 0–5, post-audit fixes Round 1)
**Tests:** 51 passing across 9 suites
**Version:** 1.0.0
**Deadline:** May 15, 2026

## What is MAZ3?

Public benchmark that empirically validates P3 (Kinetic Deference, 55 claims) and P4 (REPUBLIK OS, 75 claims) — 130 patent claims filed with the USPTO by ROCH3.

MAZ3 is the first benchmark to provide:
- Sub-millisecond convergence for n<50 agents
- Adversarial detection latency under 0.01ms
- Structural sovereignty guarantee (verified by 5 tests)
- Physical enforcement of D3/D4 deference levels (verified against malicious agents)

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
- numpy ≥ 1.24
- fastapi ≥ 0.100, uvicorn ≥ 0.23 (for API server only)

## Key Results

**Coordination quality (3×3 benchmark, Bottleneck scenario):**

| Agents | Network | avg H_p | min H_p |
|--------|---------|---------|---------|
| Syncference | ideal | 0.975 | 0.944 |
| Mixed | ideal | 0.964 | 0.329 |
| Greedy | ideal | 0.929 | 0.343 |

**Formal properties (validated empirically):**

| Property | Result | Patent Claim |
|----------|--------|--------------|
| Bounded convergence (n=50) | <0.1ms | P4 Theorem 1 |
| Graceful degradation (ideal→wifi) | 1.0% relative | P4 Theorem 3 |
| Monotonic safety | Verified | P4 Theorem 2 |
| Determinism | 50/50 identical runs | Safety-critical req |
| Adversarial detection latency | <0.01ms | P3 detection claims |
| Trust degradation (1.0→0.0) | ~10 cycles | P3 ARGUS |
| D3/D4 physical enforcement | Verified vs malicious | P3 enforcement claim |
| Sovereignty (no agent_id leaks) | Verified architecturally | P3/P4 sovereignty |

**Axiom Seal Lite:** PASS (5/5 criteria met)

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

When citing, please include the version number. Benchmark numbers are not comparable across major versions.

## Patent References

- P3: Application 64/029,056 (Kinetic Deference, 55 claims)
- P4: Application 64/030,395 (REPUBLIK OS, 75 claims)
- Inventor: Gustavo Emmanuel Briones Jara
- Filed under USPTO Micro Entity status

Total ROCH3 portfolio: ~194 claims across 4 provisional applications.

## License

Apache License 2.0 — see [LICENSE](LICENSE). The patent grant in Section 3 protects implementers; the patent retaliation clause protects ROCH3's claims.

---

*ROCH3 — The TCP/IP of the Physical World*
*Tepic, Nayarit, México*
