"""
Network Jitter Model — 4 profiles simulating real network conditions.

Profiles map to ODIN operational modes:
  - ideal: lab/testing baseline
  - industrial_ethernet: ODIN Nominal operations
  - wifi_warehouse: conventional autonomous systems
  - lora_mesh: SparkNet degraded / mesh fallback

CRITICAL BUG FIX (from handoff):
  Lognormal sigma must be: sqrt(ln(1 + (std/mean)²))
  NOT the naive: std/mean

Patent ref: P3 Claims related to network resilience, P4 SparkNet layer
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np


PROFILES: dict[str, dict] = {
    "ideal": {
        "latency_mean_ms": 1.0,
        "latency_std_ms": 0.1,
        "packet_loss_rate": 0.0,
        "jitter_distribution": "normal",
    },
    "industrial_ethernet": {
        "latency_mean_ms": 4.0,
        "latency_std_ms": 1.5,
        "packet_loss_rate": 0.001,
        "jitter_distribution": "lognormal",
    },
    "wifi_warehouse": {
        "latency_mean_ms": 12.0,
        "latency_std_ms": 8.0,
        "packet_loss_rate": 0.01,
        "jitter_distribution": "lognormal",
    },
    "lora_mesh": {
        "latency_mean_ms": 200.0,
        "latency_std_ms": 80.0,
        "packet_loss_rate": 0.05,
        "jitter_distribution": "exponential",
    },
}

# Mapping: operational mode → network profile
OPERATIONAL_MODE_MAP = {
    "odin_nominal": "industrial_ethernet",
    "conventional": "wifi_warehouse",
    "mesh_fallback": "lora_mesh",
    "testing": "ideal",
}


@dataclass
class JitterResult:
    """Result of applying network jitter to a message."""
    latency_ms: float
    packet_lost: bool
    profile_name: str


class NetworkJitterModel:
    """
    Simulates realistic network conditions for MAZ3 benchmark.

    Each projection/message passes through this model, which applies:
    1. Latency drawn from the profile's distribution
    2. Packet loss at the profile's rate

    Used to test Syncference convergence under degraded conditions.
    """

    def __init__(self, profile_name: str = "ideal",
                 seed: Optional[int] = None) -> None:
        if profile_name not in PROFILES:
            raise ValueError(
                f"Unknown profile '{profile_name}'. "
                f"Available: {list(PROFILES.keys())}"
            )
        self._profile_name = profile_name
        self._profile = PROFILES[profile_name]
        self._rng = np.random.default_rng(seed)
        # Precompute lognormal parameters (corrected formula)
        self._ln_mu: Optional[float] = None
        self._ln_sigma: Optional[float] = None
        if self._profile["jitter_distribution"] == "lognormal":
            self._ln_mu, self._ln_sigma = self._compute_lognormal_params(
                self._profile["latency_mean_ms"],
                self._profile["latency_std_ms"],
            )

    @staticmethod
    def _compute_lognormal_params(mean: float, std: float) -> tuple[float, float]:
        """
        Correct lognormal parameterization.

        For X ~ Lognormal(mu, sigma):
          E[X] = exp(mu + sigma²/2)
          Var[X] = (exp(sigma²) - 1) * exp(2*mu + sigma²)

        Given desired mean and std of X, solve for mu and sigma:
          sigma² = ln(1 + (std/mean)²)
          mu = ln(mean) - sigma²/2

        BUG FIX: The naive sigma = std/mean is WRONG.
        """
        sigma_sq = math.log(1 + (std / mean) ** 2)
        sigma = math.sqrt(sigma_sq)
        mu = math.log(mean) - sigma_sq / 2
        return mu, sigma

    def apply(self) -> JitterResult:
        """
        Apply network jitter. Returns latency and packet loss status.
        """
        # Check packet loss first
        packet_lost = self._rng.random() < self._profile["packet_loss_rate"]

        # Generate latency even if packet is lost (for logging)
        dist = self._profile["jitter_distribution"]

        if dist == "normal":
            latency = self._rng.normal(
                self._profile["latency_mean_ms"],
                self._profile["latency_std_ms"],
            )
            latency = max(0.1, latency)  # Floor: 0.1ms minimum

        elif dist == "lognormal":
            latency = self._rng.lognormal(self._ln_mu, self._ln_sigma)

        elif dist == "exponential":
            # Exponential with the given mean
            latency = self._rng.exponential(self._profile["latency_mean_ms"])

        else:
            raise ValueError(f"Unknown distribution: {dist}")

        return JitterResult(
            latency_ms=float(latency),
            packet_lost=packet_lost,
            profile_name=self._profile_name,
        )

    def apply_batch(self, count: int) -> list[JitterResult]:
        """Apply jitter to multiple messages. Used in batch simulation."""
        return [self.apply() for _ in range(count)]

    @property
    def profile_name(self) -> str:
        return self._profile_name

    @property
    def expected_latency_ms(self) -> float:
        return self._profile["latency_mean_ms"]

    @property
    def packet_loss_rate(self) -> float:
        return self._profile["packet_loss_rate"]

    def stats(self, n_samples: int = 10000) -> dict:
        """Generate empirical statistics for validation."""
        results = self.apply_batch(n_samples)
        latencies = [r.latency_ms for r in results]
        losses = sum(1 for r in results if r.packet_lost)
        return {
            "profile": self._profile_name,
            "n_samples": n_samples,
            "latency_mean": float(np.mean(latencies)),
            "latency_std": float(np.std(latencies)),
            "latency_p50": float(np.percentile(latencies, 50)),
            "latency_p95": float(np.percentile(latencies, 95)),
            "latency_p99": float(np.percentile(latencies, 99)),
            "packet_loss_observed": losses / n_samples,
            "packet_loss_configured": self._profile["packet_loss_rate"],
        }
