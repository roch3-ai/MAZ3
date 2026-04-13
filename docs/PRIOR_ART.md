# Prior Art and Differentiation

This document articulates how MAZ3 / ROCH3 differs from existing multi-agent coordination systems. It exists to support patent prosecution by documenting prior art and the specific technical differences.

## ROS 2 / Nav2

**What it is:** Robot Operating System 2 with the Nav2 navigation stack — the dominant open-source middleware for robot coordination.

**Architecture:** Centralized topic-based pub/sub with named nodes. Coordination requires explicit topic subscriptions and shared world models.

**Differentiation:**
- ROS 2 requires agents to publish identifiable state on shared topics. Identity is exposed by design. ROCH3's SovereignProjectionBuffer removes identity at the architectural level.
- Nav2 collision avoidance assumes a unified planner with global knowledge. ROCH3 produces coordinated behavior without any agent having global knowledge.
- ROS 2 has no formal conservative composition operator — agents resolve conflicts through priority schemes or pre-arranged contracts. ROCH3's Γ operator guarantees monotonic safety regardless of agent compliance.
- ROS 2 has no graduated deference (D0–D4) with latency-bounded enforcement.

## ACAS-X / TCAS

**What it is:** Aircraft Collision Avoidance System (Next Generation) — the FAA-approved system for commercial aviation collision avoidance.

**Architecture:** Two-aircraft pairwise resolution using offline-computed lookup tables. Each aircraft transmits identity and intent via Mode S transponder.

**Differentiation:**
- ACAS-X is two-party. ROCH3 handles n-party coordination via the convergence operator.
- ACAS-X requires identity broadcast. ROCH3 maintains structural sovereignty.
- ACAS-X resolutions are precomputed for the entire state space. ROCH3 computes online via Γ in <1ms.
- ACAS-X is domain-specific (aviation). ROCH3 is domain-agnostic (P4 Claim 8).

## DARPA OFFSET (OFFensive Swarm-Enabled Tactics)

**What it is:** DARPA program for swarm coordination of small UAVs in urban environments.

**Architecture:** Heterogeneous swarms with mission-level commands distributed to autonomous teams.

**Differentiation:**
- OFFSET assumes friendly cooperation among all swarm members. ROCH3 provides adversarial detection (spatial inflation, risk underreporting) and graduated trust degradation.
- OFFSET has no formal sovereignty guarantee. ROCH3's double-buffer architecture makes cross-agent state access structurally impossible.
- OFFSET focuses on tactical mission execution. ROCH3 focuses on the substrate protocol that enables ANY mission.

## Decentralized POMDP (Dec-POMDP)

**What it is:** Theoretical framework for decentralized partially observable Markov decision processes.

**Differentiation:**
- Dec-POMDP is computationally intractable in general (NEXP-complete). ROCH3 is online and sub-millisecond for n<100.
- Dec-POMDP requires shared reward function. ROCH3 preserves agent sovereignty over rewards/objectives.
- Dec-POMDP has no operational legitimacy framework. ROCH3 has The Axiom (Supervisability, Integrity, Traceability).

## Velocity Obstacles / ORCA / RVO

**What it is:** Reciprocal Velocity Obstacles and Optimal Reciprocal Collision Avoidance — geometric methods for multi-agent local navigation.

**Differentiation:**
- ORCA assumes all agents observe each other directly. ROCH3 uses MVR projections that abstract away identity.
- ORCA is purely geometric (collision avoidance only). ROCH3's MVR includes risk gradient and constraint set, supporting richer coordination than collision-only.
- ORCA requires symmetric reciprocity. ROCH3 works with mixed honest/adversarial populations via ARGUS trust scoring.

## Byzantine Fault Tolerance / PBFT / Raft

**What it is:** Distributed consensus protocols for replicated state machines under faulty/adversarial nodes.

**Differentiation:**
- BFT protocols assume all nodes converge on identical state. ROCH3 explicitly preserves agent intent diversity (M*.intent preserves individual intents).
- BFT protocols require identifiable nodes for vote attribution. ROCH3 anonymizes during convergence.
- BFT protocols are not real-time. ROCH3 has hard latency bounds tied to deference levels.

## Summary Table

| System | Year | Sovereignty | Adversarial | Real-time | n-party | Domain |
|--------|------|-------------|-------------|-----------|---------|--------|
| ROS 2 / Nav2 | 2017 | No | No | Soft | Yes | Robotics |
| ACAS-X | 2014 | No | No | Hard | 2 only | Aviation |
| DARPA OFFSET | 2017 | No | Limited | Soft | Yes | UAV swarms |
| Dec-POMDP | 2002 | Partial | No | No | Yes | Theoretical |
| ORCA | 2011 | No | No | Hard | Yes | Geometric |
| PBFT/Raft | 1999 | No | Yes | No | Yes | Distributed systems |
| **ROCH3** | **2026** | **Yes (structural)** | **Yes** | **Hard (<1ms)** | **Yes** | **Domain-agnostic** |

## Patent References

- P3: Application 64/029,056 (Kinetic Deference, 55 claims)
- P4: Application 64/030,395 (REPUBLIK OS, 75 claims)
- Inventor: Gustavo Emmanuel Briones Jara
- Filed under USPTO Micro Entity status (Customer Number 226699)
