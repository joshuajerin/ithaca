"""Durable compute job profiles and admission metadata."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class JobProfile:
    name: str
    cpu: float
    memory_mb: int
    max_duration_seconds: int
    work: str


JOB_PROFILES: dict[str, JobProfile] = {
    "interactive": JobProfile("interactive", 1.0, 2048, 120, "quotes, account snapshots, small analytics"),
    "scan": JobProfile("scan", 4.0, 8192, 900, "screeners, IV surfaces, market scans"),
    "backtest": JobProfile("backtest", 8.0, 32768, 7200, "historical equity/options simulation"),
    "optimization": JobProfile("optimization", 16.0, 65536, 14400, "walk-forward, grids, Monte Carlo"),
    "stream": JobProfile("stream", 2.0, 4096, 0, "continuous provider ingestion and trigger evaluation"),
}


class UnknownJobProfile(ValueError):
    """The requested worker profile is not part of the supported compute plane."""


def get_job_profile(profile: str) -> JobProfile:
    key = str(profile or "").strip().lower()
    try:
        return JOB_PROFILES[key]
    except KeyError as exc:
        raise UnknownJobProfile(f"unknown job profile: {profile!r}") from exc


def job_profile_manifest(profile: str) -> dict[str, Any]:
    return asdict(get_job_profile(profile))


def all_job_profile_manifests() -> dict[str, dict[str, Any]]:
    return {name: asdict(profile) for name, profile in sorted(JOB_PROFILES.items())}


def admission_metadata(profile: str) -> dict[str, Any]:
    manifest = job_profile_manifest(profile)
    return {
        "profile": manifest["name"],
        "admitted": True,
        "limits": {
            "cpu": manifest["cpu"],
            "memory_mb": manifest["memory_mb"],
            "max_duration_seconds": manifest["max_duration_seconds"],
        },
        "work": manifest["work"],
    }
