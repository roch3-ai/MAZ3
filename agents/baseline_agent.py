"""
BaselineAgent — marker class for non-sovereign baseline agents.

Agents that inherit from BaselineAgent explicitly opt out of the sovereignty
guarantee by requesting ground-truth neighbor state from the engine.

Sovereign agents (ReferenceSyncferenceAgent, adversarial variants, etc.)
inherit directly from BaseAgent and MUST NOT have this access. The engine
attaches `_engine_hook` ONLY to BaselineAgent instances.

This makes the sovereignty violation of baselines (ORCA, RVO, etc.) explicit
in the type system: an auditor greps for `BaselineAgent` to find every
baseline that requires ground-truth access.

Patent ref: P3 Claims 1-6 — sovereignty guarantee is architectural.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent


class BaselineAgent(BaseAgent):
    """
    Marker base class for non-sovereign baseline agents.

    The simulation engine attaches `_engine_hook` on `add_agent()` for every
    BaselineAgent instance. The hook exposes:
        _engine_hook.get_neighbors(self.agent_id, radius)
            → list[(neighbor_id, (x, y), (vx, vy), radius)]

    Sovereign agents do not have this attribute and calling the helper
    raises RuntimeError — structural enforcement of sovereignty.
    """

    def _get_ground_truth_neighbors(
        self, radius: float,
    ) -> list[tuple[str, tuple[float, float], tuple[float, float], float]]:
        hook = getattr(self, "_engine_hook", None)
        if hook is None:
            raise RuntimeError(
                "BaselineAgent requires engine hook for ground-truth access; "
                "did you forget to call engine.add_agent() before engine.run()?"
            )
        return hook.get_neighbors(self.agent_id, radius)
