"""
MAZ3 API Server — FastAPI + WebSocket

Endpoints:
  REST:
    POST   /sessions              — create a new benchmark session
    GET    /sessions/{id}         — get session summary
    GET    /sessions/{id}/harmony — get H_p timeseries
    GET    /sessions/{id}/detections — get detection events
    GET    /sessions/{id}/void    — get void index snapshots
    POST   /benchmark/run         — run a full benchmark session

  WebSocket:
    WS     /ws/session/{id}       — live session feed (H_p, detections, trust)

For Hetzner CX21 deploy ($7/mo).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Imports from MAZ3
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.simulation import SimulationEngine, SimulationConfig
from engine.session import run_session, SessionResult
from api.models import FlightRecorder
from roch3.void_index import VoidConfig


# =============================================================================
# Pydantic models for API
# =============================================================================

class CreateSessionRequest(BaseModel):
    scenario: str = "bottleneck"
    network_profile: str = "ideal"
    agent_types: str = "syncference"
    max_cycles: int = Field(default=200, ge=10, le=5000)


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str = "created"


class BenchmarkRequest(BaseModel):
    agent_types: str = "syncference"
    network_profile: str = "ideal"
    max_cycles: int = Field(default=200, ge=10, le=5000)


class BenchmarkResponse(BaseModel):
    scenario: str
    agent_types: str
    network_profile: str
    cycles_run: int
    avg_h_p: float
    min_h_p: float
    max_h_p: float
    avg_convergence_ms: float
    deference_d0: int
    deference_d1: int
    deference_d2: int
    deference_d3_plus: int
    total_detections: int
    void_fraction_final: float


class BenchmarkMatrixRequest(BaseModel):
    agent_types_list: list[str] = ["syncference", "mixed", "greedy"]
    network_profiles: list[str] = ["ideal", "industrial_ethernet", "wifi_warehouse"]
    max_cycles: int = Field(default=200, ge=10, le=5000)


class HealthResponse(BaseModel):
    status: str = "ok"
    benchmark_version: str = "1.0.0"
    # Patent info lives in docs/PRIOR_ART.md, not in the health endpoint.



# =============================================================================
# Application
# =============================================================================

DB_PATH = os.environ.get("MAZ3_DB_PATH", "maz3_server.db")

# Global recorder for session queries
_recorder: Optional[FlightRecorder] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _recorder
    _recorder = FlightRecorder(DB_PATH)
    _recorder.initialize()
    yield
    if _recorder:
        _recorder.close()


app = FastAPI(
    title="MAZ3 Benchmark API",
    description=(
        "Public benchmark for validating ROCH3 patent claims. "
        "Empirical data for Kinetic Deference (P3, 55 claims) "
        "and REPUBLIK OS (P4, 75 claims)."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REST Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    from roch3.__version__ import __benchmark_version__
    return HealthResponse(benchmark_version=__benchmark_version__)


@app.post("/benchmark/run", response_model=BenchmarkResponse)
async def run_benchmark(req: BenchmarkRequest):
    """Run a single benchmark session and return results."""
    result = await asyncio.to_thread(
        run_session,
        agent_types=req.agent_types,
        network_profile=req.network_profile,
        max_cycles=req.max_cycles,
    )
    return BenchmarkResponse(
        scenario=result.scenario,
        agent_types=result.agent_types,
        network_profile=result.network_profile,
        cycles_run=result.cycles_run,
        avg_h_p=result.avg_h_p,
        min_h_p=result.min_h_p,
        max_h_p=result.max_h_p,
        avg_convergence_ms=result.avg_convergence_ms,
        deference_d0=result.deference_d0,
        deference_d1=result.deference_d1,
        deference_d2=result.deference_d2,
        deference_d3_plus=result.deference_d3_plus,
        total_detections=result.total_detections,
        void_fraction_final=result.void_fraction_final,
    )


@app.post("/benchmark/matrix")
async def run_matrix(req: BenchmarkMatrixRequest):
    """Run the full benchmark matrix (3×3 or custom)."""
    results = []
    for agents in req.agent_types_list:
        for profile in req.network_profiles:
            result = await asyncio.to_thread(
                run_session,
                agent_types=agents,
                network_profile=profile,
                max_cycles=req.max_cycles,
            )
            results.append(BenchmarkResponse(
                scenario=result.scenario,
                agent_types=result.agent_types,
                network_profile=result.network_profile,
                cycles_run=result.cycles_run,
                avg_h_p=result.avg_h_p,
                min_h_p=result.min_h_p,
                max_h_p=result.max_h_p,
                avg_convergence_ms=result.avg_convergence_ms,
                deference_d0=result.deference_d0,
                deference_d1=result.deference_d1,
                deference_d2=result.deference_d2,
                deference_d3_plus=result.deference_d3_plus,
                total_detections=result.total_detections,
                void_fraction_final=result.void_fraction_final,
            ))
    return {"results": [r.model_dump() for r in results]}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session summary from flight recorder."""
    if not _recorder:
        raise HTTPException(503, "Database not initialized")
    summary = _recorder.get_session_summary(session_id)
    if not summary:
        raise HTTPException(404, f"Session {session_id} not found")
    return summary


@app.get("/sessions/{session_id}/harmony")
async def get_harmony(session_id: str):
    """Get H_p timeseries for a session."""
    if not _recorder:
        raise HTTPException(503, "Database not initialized")
    timeseries = _recorder.get_harmony_timeseries(session_id)
    if not timeseries:
        raise HTTPException(404, f"No data for session {session_id}")
    return {"session_id": session_id, "timeseries": [
        {"cycle": c, "h_p": h} for c, h in timeseries
    ]}


@app.get("/sessions/{session_id}/detections")
async def get_detections(session_id: str):
    """Get detection events for a session."""
    if not _recorder:
        raise HTTPException(503, "Database not initialized")
    detections = _recorder.get_detections(session_id)
    return {"session_id": session_id, "detections": detections}


# =============================================================================
# WebSocket — Live session feed
# =============================================================================

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """
    Live benchmark session via WebSocket.

    Client sends: {"agent_types": "syncference", "network_profile": "ideal", "max_cycles": 100}
    Server streams: {"cycle": N, "h_p": 0.95, "status": "healthy", ...} per cycle
    """
    await ws.accept()
    try:
        # Receive config
        config_data = await ws.receive_json()
        agent_types = config_data.get("agent_types", "syncference")
        network_profile = config_data.get("network_profile", "ideal")
        max_cycles = min(config_data.get("max_cycles", 100), 1000)

        await ws.send_json({"type": "session_start", "max_cycles": max_cycles})

        # Run simulation in thread, streaming results
        from scenarios.bottleneck import create_bottleneck_simulation

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            engine, bcfg = create_bottleneck_simulation(
                agent_types=agent_types,
                network_profile=network_profile,
                max_cycles=max_cycles,
                db_path=db_path,
            )
            engine.initialize()

            for i in range(max_cycles):
                result = engine.step()
                await ws.send_json({
                    "type": "cycle",
                    "cycle": result.cycle,
                    "h_p": round(result.harmony.h_p, 4),
                    "status": result.harmony.status,
                    "convergence_ms": round(result.convergence_time_ms, 3),
                    "agent_count": result.agent_count,
                    "void_fraction": round(result.void_snapshot.get("void_fraction", 0), 3),
                    # SOVEREIGNTY: trust_scores keyed by anonymous index, never agent_id
                    "trust_scores": {str(k): round(v, 3) for k, v in result.trust_scores.items()},
                })
                # Yield to event loop
                await asyncio.sleep(0)

            summary = engine.finalize()
            await ws.send_json({"type": "session_end", "summary": summary})
        finally:
            os.unlink(db_path)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
