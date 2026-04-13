# The Axiom

**Three non-negotiable axioms for operational legitimacy of autonomous physical systems.**

## The Three Axioms

### 1. Supervisability

Every autonomous action must be observable and interruptible by a qualified human or oversight system. An autonomous agent that cannot be supervised is not legitimate, regardless of its performance.

In MAZ3: every cycle is logged to the flight recorder. Every deference action is recorded. The D3 (commanded stop) and D4 (emergency veto) levels are physically enforced — no agent can override them.

### 2. Integrity

The system must not produce outputs that are less safe than its inputs. The convergence operator Γ must satisfy monotonic safety: the shared MVR is always at least as conservative as the most cautious individual assessment.

In MAZ3: `test_convergence.py::test_monotonic_safety` verifies this formally. Constraints are intersected (strictest wins). Risk is maximized per cell (pessimistic). Spatial envelopes are unioned (conservative).

### 3. Traceability

Every coordination decision must be traceable to specific inputs. If the system commands an agent to stop, the chain of reasoning must be reconstructable: which projections, which ΔK value, which threshold triggered it.

In MAZ3: the flight recorder stores snapshots with agent projections, shared MVR, harmony index, detection events, void index, and deference actions. Every D1+ event includes the ΔK value and threshold that triggered it.

## Axiom Seal Lite

Certification criteria for the MAZ3 benchmark. An agent implementation passes Axiom Seal Lite if:

| Criterion | Requirement | Test |
|-----------|-------------|------|
| C1 | avg H_p ≥ 0.85 across 3 network profiles | test_paso5 |
| C2 | min H_p ≥ 0.55 in ideal conditions | test_paso5 |
| C3 | No sovereignty violations | test_sovereignty |
| C4 | Detection latency < 1ms for known attacks | test_paso5 |
| C5 | Convergence time < 8ms for n ≤ 50 | test_paso5 |

The reference Syncference agent passes all 5 criteria.

### Seal Levels (Roadmap)

- **Axiom Seal Lite** (current): Benchmark-only certification. Free. Verifies basic protocol compliance.
- **Axiom Seal Pro** (60 days post-launch): Production certification. $99/year. Requires real-world deployment data + audit.

## Machine-Executable Axioms

The Axiom is designed to be expressed in policy languages (Rego/Cedar) for machine enforcement. In MAZ3, enforcement is through code:

- Supervisability → flight recorder + D3/D4 physical enforcement
- Integrity → Γ conservative composition (proven in tests)
- Traceability → PostgreSQL-compatible schema with full event logging

## Patent Reference

- P4 Claims: The Axiom (3 axioms of operational legitimacy)
- P4 Claims: Axiom Seal certification mechanism
