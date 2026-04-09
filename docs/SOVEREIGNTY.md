# Sovereignty Guarantee

**"Sovereignty is architecture, not policy."**

## The Problem

In multi-agent coordination, agents must share enough information to avoid collisions and conflicts. But sharing information creates a vulnerability: if Agent A can see Agent B's plans, A can exploit that knowledge.

Most coordination systems solve this with trust policies, access control lists, or encryption. These are all *policy* solutions — they work until someone finds a way around the policy.

## The ROCH3 Solution: Structural Sovereignty

MAZ3 makes sovereignty **structural** — it is physically impossible in the code architecture for one agent's projection to leak to another.

### Double-Buffer Architecture

Two channels that **NEVER** cross:

**Channel 1 — SovereignProjectionBuffer (for Γ):**
- Stores agent projections indexed by anonymous integer (not agent_id)
- The convergence operator Γ receives fields + trust weights, never identities
- Γ cannot retransmit Agent A's projection to Agent B because it doesn't know who A or B are

**Channel 2 — ARGUSTrustChannel (for trust scoring):**
- Receives behavioral observations keyed by agent_id
- Produces trust scores
- Translates {agent_id → anonymous_index} before pushing to buffer
- Never exposes raw projections

### The Mapping

The ONLY place where agent_id and MVR fields coexist is inside `SovereignProjectionBuffer._projections`. But they never *leave* together:

```
ARGUS: {agent_id: trust_score}
         ↓
Mapping: {agent_id → anonymous_index}  (inside buffer only)
         ↓
Γ sees:  [{mvr_fields, trust_weight: 0.95, _index: 0},
          {mvr_fields, trust_weight: 0.72, _index: 1}]
```

### Verification

`test_sovereignty.py` contains 5 tests that verify this guarantee:

1. **test_sovereignty_guarantee**: No agent_id appears anywhere in convergence output
2. **test_no_cross_agent_access**: No API path exists to get Agent A's projection from Agent B's perspective
3. **test_gamma_receives_no_identity**: Γ operates entirely without agent identifiers
4. **test_argus_channel_separation**: ARGUS and Γ channels are fully separated
5. **test_agent_removal**: Removing an agent cleans its projection but keeps index stable

A security auditor inspecting this code must find it **structurally impossible** to access one agent's raw projection from another agent's perspective. This is the sovereignty guarantee.

## Patent Reference

- P3 Claims 1-6 (sovereignty guarantee)
- P4 Claims 6-10 (ARGUS identity and security)
- P4 Axiom: state(aᵢ) ∩ MVR = ∅ — agent internal state never enters the shared MVR
