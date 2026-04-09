# MAZ3 — Empirical Benchmark for ROCH3 Patent Validation

**Status:** Complete (Pasos 0-5)  
**Tests:** 49 passing  
**Deadline:** May 15, 2026  

## What is MAZ3?

Public benchmark that empirically validates P3 (Kinetic Deference, 55 claims) and P4 (REPUBLIK OS, 75 claims) — 130 patent claims filed with the USPTO by ROCH3.

## Quick Start

```bash
python tests/test_sovereignty.py
python tests/test_paso0_integration.py
python tests/test_paso1_simulation.py
python tests/test_paso2_multiagent.py
python tests/test_paso3_adversarial.py
python tests/test_convergence.py
python tests/test_safety.py
python tests/test_paso5_omniscient.py

# 3x3 benchmark table
python -c "from engine.session import run_benchmark_matrix, print_table; print_table(run_benchmark_matrix())"

# API server
pip install fastapi uvicorn
python api/server.py
```

## Requirements

Python 3.10+, numpy. FastAPI + uvicorn for API server.

## Key Results

**Coordination:** Syncference (avg H_p 0.975) > Mixed (0.964) > Greedy (0.929)

**Safety:** Syncference min H_p 0.944 (healthy) vs Greedy 0.343 (critical)

**Adversarial:** Detection in <0.01ms, trust 1.0→0.0 in ~10 cycles post-detection

**Formal:** Bounded convergence 0.07ms (n=50), graceful degradation 1% relative, deterministic

**Axiom Seal Lite:** PASS (all 5 criteria met)

## Patent References

P3: Application 64/029,056 (55 claims) | P4: Application 64/030,395 (75 claims) | Total: ~194 claims

---

*ROCH3 — The TCP/IP of the Physical World*
