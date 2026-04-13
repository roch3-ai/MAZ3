"""
Database Models — Flight Recorder Schema

SQLite-first for benchmark. PostgreSQL migration at production deploy.
Schema is compatible with both — key differences handled:
  - gen_random_uuid() → Python uuid4
  - TIMESTAMPTZ → TEXT (ISO format)
  - JSONB → JSON (SQLite stores as TEXT, both parse the same)

The flight recorder is the SINGLE SOURCE OF TRUTH.
No feed uses in-memory state directly. Everything is computed from snapshots.

Patent ref: P3/P4 flight recorder requirements
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Generator


DEFAULT_DB_PATH = "maz3_flight_recorder.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# =============================================================================
# Schema creation
# =============================================================================

SCHEMA_SQL = """
-- Sessions
CREATE TABLE IF NOT EXISTS maze_sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    scenario TEXT NOT NULL,
    network_profile TEXT NOT NULL,
    agent_count INTEGER NOT NULL,
    status TEXT DEFAULT 'active',
    maze_version TEXT NOT NULL DEFAULT '1.0.0'
);

-- Flight snapshots (source of truth)
CREATE TABLE IF NOT EXISTS flight_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES maze_sessions(id),
    cycle_number INTEGER NOT NULL,
    h_p REAL NOT NULL,
    convergence_time_ms REAL,
    agent_projections TEXT,
    shared_mvr TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_session_cycle
ON flight_snapshots(session_id, cycle_number);

-- Detection events (adversarial)
CREATE TABLE IF NOT EXISTS detection_events (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES maze_sessions(id),
    cycle_number INTEGER NOT NULL,
    attack_type TEXT NOT NULL,
    detection_latency_ms REAL,
    deference_level TEXT,
    details TEXT,
    detected_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_detection_session
ON detection_events(session_id, attack_type);

-- Antifragility loop updates
CREATE TABLE IF NOT EXISTS antifragility_loop_updates (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES maze_sessions(id),
    trigger_type TEXT NOT NULL,
    theta_k_before REAL,
    theta_k_after REAL,
    sessions_incorporated INTEGER,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_antifragility_trigger
ON antifragility_loop_updates(trigger_type);

CREATE INDEX IF NOT EXISTS idx_antifragility_updated
ON antifragility_loop_updates(updated_at DESC);

-- Void index snapshots
CREATE TABLE IF NOT EXISTS void_index_snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES maze_sessions(id),
    cycle_number INTEGER NOT NULL,
    total_void_volume REAL NOT NULL,
    void_zones_count INTEGER NOT NULL,
    void_collapse_flag INTEGER DEFAULT 0,
    collapse_delta REAL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_void_collapse
ON void_index_snapshots(session_id, void_collapse_flag);

-- Custom metrics (extension point for v2 industrial deployments)
-- Phase 1 only creates the table; v1 doesn't write to it.
-- v2 will use it for throughput, recovery_time, fairness, energy_proxy.
CREATE TABLE IF NOT EXISTS custom_metrics (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES maze_sessions(id),
    cycle_number INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    metadata TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_custom_metrics_name
ON custom_metrics(session_id, metric_name);
"""


# =============================================================================
# Database connection
# =============================================================================

class FlightRecorder:
    """
    Flight Recorder — single source of truth for all MAZ3 data.

    All simulation state must be written here. No feed, display, or
    analysis reads from in-memory state directly — everything goes
    through the flight recorder.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Create database and tables."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        if not self._conn:
            raise RuntimeError("FlightRecorder not initialized. Call initialize() first.")
        cursor = self._conn.cursor()
        try:
            yield cursor
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # =========================================================================
    # Sessions
    # =========================================================================

    def create_session(
        self,
        scenario: str,
        network_profile: str,
        agent_count: int,
        maze_version: str = "1.0.0",
    ) -> str:
        """Create a new maze session. Returns session_id."""
        session_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO maze_sessions "
                "(id, created_at, scenario, network_profile, agent_count, maze_version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, _now_iso(), scenario, network_profile,
                 agent_count, maze_version),
            )
        return session_id

    def end_session(self, session_id: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE maze_sessions SET status = 'completed' WHERE id = ?",
                (session_id,),
            )

    # =========================================================================
    # Flight snapshots
    # =========================================================================

    def record_snapshot(
        self,
        session_id: str,
        cycle_number: int,
        h_p: float,
        convergence_time_ms: Optional[float] = None,
        agent_projections: Optional[list[dict]] = None,
        shared_mvr: Optional[dict] = None,
    ) -> str:
        """Record a flight snapshot. Returns snapshot_id."""
        snapshot_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO flight_snapshots "
                "(id, session_id, cycle_number, h_p, convergence_time_ms, "
                "agent_projections, shared_mvr, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    session_id,
                    cycle_number,
                    h_p,
                    convergence_time_ms,
                    json.dumps(agent_projections) if agent_projections else None,
                    json.dumps(shared_mvr) if shared_mvr else None,
                    _now_iso(),
                ),
            )
        return snapshot_id

    def get_snapshots(
        self, session_id: str, limit: int = 1000
    ) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM flight_snapshots WHERE session_id = ? "
                "ORDER BY cycle_number ASC LIMIT ?",
                (session_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Detection events
    # =========================================================================

    def record_detection(
        self,
        session_id: str,
        cycle_number: int,
        attack_type: str,
        detection_latency_ms: float,
        deference_level: str,
        details: Optional[dict] = None,
    ) -> str:
        event_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO detection_events "
                "(id, session_id, cycle_number, attack_type, detection_latency_ms, "
                "deference_level, details, detected_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    session_id,
                    cycle_number,
                    attack_type,
                    detection_latency_ms,
                    deference_level,
                    json.dumps(details) if details else None,
                    _now_iso(),
                ),
            )
        return event_id

    def get_detections(self, session_id: str) -> list[dict]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM detection_events WHERE session_id = ? "
                "ORDER BY cycle_number ASC",
                (session_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Antifragility loop
    # =========================================================================

    def record_antifragility_update(
        self,
        session_id: str,
        trigger_type: str,
        theta_k_before: float,
        theta_k_after: float,
        sessions_incorporated: int,
    ) -> str:
        update_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO antifragility_loop_updates "
                "(id, session_id, trigger_type, theta_k_before, theta_k_after, "
                "sessions_incorporated, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    update_id,
                    session_id,
                    trigger_type,
                    theta_k_before,
                    theta_k_after,
                    sessions_incorporated,
                    _now_iso(),
                ),
            )
        return update_id

    # =========================================================================
    # Void index snapshots
    # =========================================================================

    def record_void_snapshot(
        self,
        session_id: str,
        cycle_number: int,
        total_void_volume: float,
        void_zones_count: int,
        void_collapse_flag: bool = False,
        collapse_delta: Optional[float] = None,
    ) -> str:
        snapshot_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO void_index_snapshots "
                "(id, session_id, cycle_number, total_void_volume, void_zones_count, "
                "void_collapse_flag, collapse_delta, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    session_id,
                    cycle_number,
                    total_void_volume,
                    void_zones_count,
                    1 if void_collapse_flag else 0,
                    collapse_delta,
                    _now_iso(),
                ),
            )
        return snapshot_id

    # =========================================================================
    # Custom metrics (extension point for v2)
    # =========================================================================

    def record_custom_metric(
        self,
        session_id: str,
        cycle_number: int,
        metric_name: str,
        metric_value: float,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Record a custom metric. Extension point for v2 industrial deployments.

        v1 (current) does not write to this table — but the schema exists
        so v2 can add throughput, recovery_time, fairness, energy_proxy
        without requiring data migration.
        """
        metric_id = _new_id()
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO custom_metrics "
                "(id, session_id, cycle_number, metric_name, metric_value, "
                "metadata, recorded_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    metric_id,
                    session_id,
                    cycle_number,
                    metric_name,
                    metric_value,
                    json.dumps(metadata) if metadata else None,
                    _now_iso(),
                ),
            )
        return metric_id

    def get_custom_metrics(
        self, session_id: str, metric_name: Optional[str] = None
    ) -> list[dict]:
        """Query custom metrics, optionally filtered by metric_name."""
        with self._cursor() as cur:
            if metric_name:
                cur.execute(
                    "SELECT * FROM custom_metrics WHERE session_id = ? "
                    "AND metric_name = ? ORDER BY cycle_number ASC",
                    (session_id, metric_name),
                )
            else:
                cur.execute(
                    "SELECT * FROM custom_metrics WHERE session_id = ? "
                    "ORDER BY cycle_number ASC",
                    (session_id,),
                )
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # Queries for analysis
    # =========================================================================

    def get_session_summary(self, session_id: str) -> Optional[dict]:
        """Get summary stats for a session."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT s.*, "
                "  (SELECT COUNT(*) FROM flight_snapshots WHERE session_id = s.id) as snapshot_count, "
                "  (SELECT AVG(h_p) FROM flight_snapshots WHERE session_id = s.id) as avg_h_p, "
                "  (SELECT MIN(h_p) FROM flight_snapshots WHERE session_id = s.id) as min_h_p, "
                "  (SELECT MAX(h_p) FROM flight_snapshots WHERE session_id = s.id) as max_h_p, "
                "  (SELECT COUNT(*) FROM detection_events WHERE session_id = s.id) as detection_count "
                "FROM maze_sessions s WHERE s.id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_harmony_timeseries(self, session_id: str) -> list[tuple[int, float]]:
        """Get (cycle, h_p) pairs for plotting."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT cycle_number, h_p FROM flight_snapshots "
                "WHERE session_id = ? ORDER BY cycle_number ASC",
                (session_id,),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]
