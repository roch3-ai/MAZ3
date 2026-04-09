"""
Sovereign Context — Double Buffer Architecture

Two channels that NEVER cross:
  1. SovereignProjectionBuffer → feeds Γ with anonymous MVR fields
  2. ARGUSTrustChannel → produces trust weights via authenticated channel

The mapping between agent_id and anonymous index lives ONLY inside
SovereignProjectionBuffer. Γ sees fields + weights, never identities.

"Sovereignty is not political — it is architecture."

Patent ref: P3 Claims 1-6 (sovereignty guarantee), P4 Claims 6-10 (ARGUS)
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Optional

from roch3.mvr import MVRProjection


@dataclass
class _IndexedProjection:
    """Internal: MVR fields + anonymous index. Never exposed outside this module."""
    index: int
    mvr_dict: dict  # Serialized MVR fields — no agent_id
    stored_at: float
    trust_weight: float = 1.0  # Default: full trust until ARGUS says otherwise


class SovereignProjectionBuffer:
    """
    The sovereignty guarantee is architectural, not policy.

    - Γ receives ONLY anonymous MVR fields + trust weights.
    - Γ cannot retransmit agent A's projection to agent B.
    - The mapping {agent_id → index} lives here and ONLY here.
    - Fields and identity coexist inside this buffer but NEVER leave together.

    A security auditor inspecting the code must find it STRUCTURALLY IMPOSSIBLE
    to access one agent's raw projection from another agent's perspective.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {agent_id: _IndexedProjection} — the ONLY place ids and fields coexist
        self._projections: dict[str, _IndexedProjection] = {}
        self._next_index: int = 0
        # {agent_id: index} — stable mapping for the lifetime of a session
        self._id_to_index: dict[str, int] = {}

    def store(self, agent_id: str, projection: MVRProjection) -> int:
        """
        Store a projection. Returns the anonymous index assigned.
        The caller (agent connection handler) knows agent_id.
        After this call, the projection is accessible ONLY as anonymous fields.
        """
        errors = projection.validate()
        if errors:
            raise ValueError(f"Invalid MVR projection: {errors}")

        mvr_dict = projection.to_dict()

        with self._lock:
            # Assign stable index (first time) or reuse existing
            if agent_id not in self._id_to_index:
                self._id_to_index[agent_id] = self._next_index
                self._next_index += 1

            idx = self._id_to_index[agent_id]

            self._projections[agent_id] = _IndexedProjection(
                index=idx,
                mvr_dict=mvr_dict,
                stored_at=time.time(),
            )
        return idx

    def apply_trust_weights(self, trust_scores: dict[int, float]) -> None:
        """
        Apply trust weights from ARGUS.

        CRITICAL: trust_scores is keyed by ANONYMOUS INDEX, not agent_id.
        The translation from agent_id to index happens in ARGUSTrustChannel,
        which calls this method with already-anonymized keys.
        """
        with self._lock:
            for agent_id, proj in self._projections.items():
                if proj.index in trust_scores:
                    proj.trust_weight = trust_scores[proj.index]

    def get_fields_for_convergence(self) -> list[dict]:
        """
        Returns anonymous MVR fields + trust weights for Γ.

        SOVEREIGNTY GUARANTEE: No agent_id in the output. Ever.
        Sorted by index for deterministic ordering.
        """
        with self._lock:
            entries = []
            for proj in self._projections.values():
                entry = dict(proj.mvr_dict)  # copy
                entry["_trust_weight"] = proj.trust_weight
                entry["_index"] = proj.index
                entries.append(entry)
            entries.sort(key=lambda e: e["_index"])
            return entries

    def get_index_for_agent(self, agent_id: str) -> Optional[int]:
        """
        Used internally by ARGUSTrustChannel to translate agent_id → index.
        This is the ONLY bridge between the two channels.
        """
        with self._lock:
            return self._id_to_index.get(agent_id)

    def remove_agent(self, agent_id: str) -> None:
        """Remove an agent's projection (disconnect / session end)."""
        with self._lock:
            self._projections.pop(agent_id, None)
            # Keep the index mapping — indices are stable for the session

    def agent_count(self) -> int:
        with self._lock:
            return len(self._projections)

    def clear(self) -> None:
        """Full reset — new session."""
        with self._lock:
            self._projections.clear()
            self._id_to_index.clear()
            self._next_index = 0


class ARGUSTrustChannel:
    """
    Authenticated channel for trust scoring.

    - Produces {agent_id: trust_score} based on behavioral observations.
    - Translates to {anonymous_index: trust_score} before passing to buffer.
    - NEVER exposes raw projections.
    - Γ has NO access to this channel.

    Trust scoring is based on:
    - Consistency of projections over time
    - Deviation from declared constraints
    - Detection of adversarial patterns (spatial inflation, under-reporting)

    Patent ref: P4 Claims 6-10 (ARGUS identity and security)
    """

    def __init__(self, buffer: SovereignProjectionBuffer) -> None:
        self._lock = threading.Lock()
        self._buffer = buffer
        # {agent_id: trust_score} — raw scores
        self._trust_scores: dict[str, float] = {}
        # {agent_id: [observation_history]} — for trend analysis
        self._history: dict[str, list[dict]] = {}
        # Configuration
        self._initial_trust: float = 1.0
        self._decay_rate: float = 0.05  # per suspicious observation
        self._recovery_rate: float = 0.01  # per clean observation

    def update_trust(self, agent_id: str, observation: dict) -> float:
        """
        Update trust score based on a behavioral observation.

        Observations include:
        - {"type": "consistent", ...} → trust recovery
        - {"type": "spatial_inflation", ...} → trust decay
        - {"type": "under_reporting_risk", ...} → trust decay
        - {"type": "clock_drift_excessive", ...} → trust decay

        Returns the updated trust score.
        """
        with self._lock:
            if agent_id not in self._trust_scores:
                self._trust_scores[agent_id] = self._initial_trust
                self._history[agent_id] = []

            current = self._trust_scores[agent_id]
            obs_type = observation.get("type", "unknown")

            if obs_type == "consistent":
                # Slow recovery — trust is hard to rebuild
                current = min(1.0, current + self._recovery_rate)
            elif obs_type in ("spatial_inflation", "under_reporting_risk",
                              "clock_drift_excessive", "projection_poisoning"):
                severity = observation.get("severity", 1.0)
                current = max(0.0, current - self._decay_rate * severity)
            # Unknown types don't change trust — fail safe

            self._trust_scores[agent_id] = current
            self._history[agent_id].append({
                "observation": observation,
                "trust_after": current,
                "timestamp": time.time(),
            })
            return current

    def push_weights_to_buffer(self) -> None:
        """
        Translate {agent_id: score} → {anonymous_index: score}
        and push to SovereignProjectionBuffer.

        This is the ONLY point where ARGUS touches the buffer,
        and it does so through anonymized indices only.
        """
        with self._lock:
            anonymized: dict[int, float] = {}
            for agent_id, score in self._trust_scores.items():
                idx = self._buffer.get_index_for_agent(agent_id)
                if idx is not None:
                    anonymized[idx] = score

        # Push outside lock to avoid deadlock with buffer's lock
        self._buffer.apply_trust_weights(anonymized)

    def get_trust_score(self, agent_id: str) -> float:
        """Get current trust score for an agent."""
        with self._lock:
            return self._trust_scores.get(agent_id, self._initial_trust)

    def get_all_scores(self) -> dict[str, float]:
        """Get all trust scores. Used for flight recorder logging."""
        with self._lock:
            return dict(self._trust_scores)

    def get_history(self, agent_id: str, last_n: int = 10) -> list[dict]:
        """Get recent observation history for an agent."""
        with self._lock:
            return list(self._history.get(agent_id, [])[-last_n:])

    def clear(self) -> None:
        """Full reset — new session."""
        with self._lock:
            self._trust_scores.clear()
            self._history.clear()
