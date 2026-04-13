"""
Void Index — Unclaimed regions as first-class entities.

"The space that nobody claims is where real safety lives."

Key concepts:
  - void_zone: a cell with N+ consecutive cycles unclaimed
  - nearest_void: used by HARMONIZE for D2/D3 corrections (project toward empty space)
  - void_collapse: rapid reduction in void volume without real agent movement
    (adversarial attack detection)

Grid: 2D discrete, configurable resolution (default 1m × 1m).
Scenarios: Bottleneck, Intersection, Open Field are all floor-plan 2D.
3D (drones) deferred to Phase 2+.

Patent ref: P3 Void-related claims, P4 ATHENS/ZENZE spatial awareness
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoidConfig:
    """Configuration for the VoidIndex grid."""
    width: float = 50.0  # meters
    height: float = 50.0  # meters
    resolution: float = 1.0  # meters per cell
    void_threshold_cycles: int = 5  # cycles unclaimed → void zone
    collapse_window_cycles: int = 3  # window for collapse detection
    collapse_delta_threshold: float = 0.20  # 20% drop in void volume → alert


@dataclass
class CellState:
    """State of a single grid cell."""
    unclaimed_cycles: int = 0
    is_void: bool = False
    last_claimed_cycle: int = -1


class VoidIndex:
    """
    Tracks persistently unclaimed regions on the simulation grid.

    Every cycle:
    1. Receive current MVR spatial envelopes
    2. Mark cells as claimed/unclaimed
    3. Increment unclaimed counters
    4. Promote cells to void_zone after threshold
    5. Check for void collapse attacks

    Γ uses nearest_void() to find safe escape space for D2/D3 corrections.
    """

    def __init__(self, config: Optional[VoidConfig] = None) -> None:
        self._config = config or VoidConfig()
        c = self._config
        self._cols = int(math.ceil(c.width / c.resolution))
        self._rows = int(math.ceil(c.height / c.resolution))
        # Grid of cell states
        self._grid: list[list[CellState]] = [
            [CellState() for _ in range(self._cols)]
            for _ in range(self._rows)
        ]
        # History of void volume for collapse detection
        self._void_volume_history: list[float] = []
        self._current_cycle: int = 0

    def update(self, spatial_envelopes: list[dict], cycle_number: int) -> None:
        """
        Update void index with current cycle's claimed spaces.

        spatial_envelopes: list of {"x_min", "y_min", "x_max", "y_max"}
            from MVR projections (already anonymized by SovereignProjectionBuffer).
        """
        self._current_cycle = cycle_number

        # Mark all cells as unclaimed for this cycle
        claimed = set()

        for env in spatial_envelopes:
            # Convert spatial envelope to grid cells
            col_min = max(0, int(env["x_min"] / self._config.resolution))
            col_max = min(self._cols - 1,
                          int(env["x_max"] / self._config.resolution))
            row_min = max(0, int(env["y_min"] / self._config.resolution))
            row_max = min(self._rows - 1,
                          int(env["y_max"] / self._config.resolution))

            for r in range(row_min, row_max + 1):
                for c in range(col_min, col_max + 1):
                    claimed.add((r, c))

        # Update cell states
        for r in range(self._rows):
            for c in range(self._cols):
                cell = self._grid[r][c]
                if (r, c) in claimed:
                    cell.unclaimed_cycles = 0
                    cell.is_void = False
                    cell.last_claimed_cycle = cycle_number
                else:
                    cell.unclaimed_cycles += 1
                    if cell.unclaimed_cycles >= self._config.void_threshold_cycles:
                        cell.is_void = True

        # Track void volume for collapse detection
        self._void_volume_history.append(self.total_void_volume())
        # Bound history to prevent unbounded memory growth
        if len(self._void_volume_history) > 1000:
            self._void_volume_history = self._void_volume_history[-500:]

    def nearest_void(self, position: tuple[float, float]) -> Optional[tuple[float, float]]:
        """
        Find the nearest void zone center to a given position.
        Used by HARMONIZE for D2/D3 corrections — project corrections
        toward structurally empty space.

        Returns (x, y) center of nearest void cell, or None if no voids exist.
        """
        px, py = position
        col = int(px / self._config.resolution)
        row = int(py / self._config.resolution)

        best_dist_sq = float("inf")
        best_pos = None

        for r in range(self._rows):
            for c in range(self._cols):
                if self._grid[r][c].is_void:
                    # Center of cell
                    cx = (c + 0.5) * self._config.resolution
                    cy = (r + 0.5) * self._config.resolution
                    dist_sq = (cx - px) ** 2 + (cy - py) ** 2
                    if dist_sq < best_dist_sq:
                        best_dist_sq = dist_sq
                        best_pos = (cx, cy)

        return best_pos

    def void_collapse_detected(self) -> bool:
        """
        Detect Void Collapse Attack: rapid reduction of void volume
        without corresponding real agent movement.

        Check: if void volume dropped by more than collapse_delta_threshold
        within the collapse_window, flag it.
        """
        window = self._config.collapse_window_cycles
        if len(self._void_volume_history) < window + 1:
            return False

        recent = self._void_volume_history[-window:]
        previous = self._void_volume_history[-(window + 1)]

        if previous <= 0:
            return False

        current = recent[-1]
        delta = (previous - current) / previous

        return delta >= self._config.collapse_delta_threshold

    def total_void_volume(self) -> float:
        """Total void area in square meters."""
        count = sum(
            1 for r in range(self._rows) for c in range(self._cols)
            if self._grid[r][c].is_void
        )
        return count * (self._config.resolution ** 2)

    def void_zones_count(self) -> int:
        """Number of individual void cells."""
        return sum(
            1 for r in range(self._rows) for c in range(self._cols)
            if self._grid[r][c].is_void
        )

    def void_fraction(self) -> float:
        """Fraction of grid that is void [0, 1]."""
        total_cells = self._rows * self._cols
        if total_cells == 0:
            return 0.0
        return self.void_zones_count() / total_cells

    def collapse_delta(self) -> Optional[float]:
        """Current collapse delta (for logging). None if insufficient history."""
        window = self._config.collapse_window_cycles
        if len(self._void_volume_history) < window + 1:
            return None
        previous = self._void_volume_history[-(window + 1)]
        if previous <= 0:
            return 0.0
        current = self._void_volume_history[-1]
        return (previous - current) / previous

    def get_snapshot(self) -> dict:
        """Snapshot for flight recorder."""
        return {
            "cycle": self._current_cycle,
            "total_void_volume": self.total_void_volume(),
            "void_zones_count": self.void_zones_count(),
            "void_fraction": self.void_fraction(),
            "void_collapse_flag": self.void_collapse_detected(),
            "collapse_delta": self.collapse_delta(),
        }

    @property
    def grid_dimensions(self) -> tuple[int, int]:
        """(rows, cols) of the grid."""
        return (self._rows, self._cols)
