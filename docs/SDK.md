# MAZ3 SDK

The MAZ3 SDK is the agent-side interface for connecting to a Syncference benchmark.

## Design Principles

1. **Wrappable.** The SDK is designed to be wrapped by ROS 2, MQTT, gRPC, or any robotics middleware. The agent contract uses primitive types and JSON-serializable schemas.

2. **Sovereign by default.** Agents project MVR fields. They do NOT receive other agents' raw projections — only the converged shared MVR (M*).

3. **No hidden state.** Everything an agent needs is in `BaseAgent`. There are no magic methods, no metaclasses, no private engine APIs that subclasses must implement.

## Agent Contract

Subclass `BaseAgent` and implement four methods (the four agent-side phases of Syncference):

```python
from agents.base_agent import BaseAgent, AgentConfig
from roch3.mvr import MVRProjection

class MyAgent(BaseAgent):
    def sense(self, environment: dict) -> None:
        # Phase 1: read boundary, cycle, public obstacles
        ...

    def infer(self) -> None:
        # Phase 2: produce internal model + intent
        ...

    def project(self) -> MVRProjection:
        # Phase 3: extract 5 MVR fields from internal state
        ...

    def act(self, shared_mvr: dict, dt: float) -> None:
        # Phase 5: execute action constrained by M*
        ...
```

Phase 4 (CONVERGE) is handled by the engine, not the agent.

## Wire Format (JSON)

`MVRProjection` supports JSON serialization for transport across language/process boundaries:

```python
proj = MVRProjection(...)
wire = proj.to_json()        # str
recv = MVRProjection.from_json(wire)
```

This is what enables a ROS 2 wrapper: a Python ROS 2 node can subscribe to a topic carrying JSON-encoded MVR projections from agents written in C++, Rust, or any other language.

## Integration Patterns

### Pattern 1: Direct subclass (Python only)
The reference implementation. Subclass `BaseAgent`, register with `engine.add_agent()`, run.

### Pattern 2: ROS 2 wrapper
A `MazAdapterNode` subscribes to a topic carrying agent state, projects to MVR, calls a MAZ3 client over the API, and publishes the shared MVR back. The ROS 2 agent never imports MAZ3 directly.

### Pattern 3: WebSocket client
For browser-based or remote agents. Connect to `/ws/live`, send config, receive cycle-by-cycle updates including the shared MVR.

## Physical Enforcement Note

The engine reserves the right to override an agent's state via `engine_override_state()` when deference level reaches D3 or D4. Subclasses MUST NOT override this method. In a real deployment, this corresponds to a hardware safety system cutting motor power. In MAZ3, it's the simulation enforcing P3's "physically enforced" claim.

## See Also

- `docs/SOVEREIGNTY.md` — the architectural sovereignty guarantee
- `docs/AXIOM.md` — operational legitimacy framework
- `docs/PRIOR_ART.md` — differentiation from existing systems
