"""Patch datamodel-code-generator's optional-field nullability for Ithaca contracts.

JSON Schema distinguishes "field may be omitted" from "field may be null". The Python
generator currently emits ``T | None = default`` for several optional non-null properties,
which accepts explicit ``null`` even though JSON Schema and generated Zod reject it.

Keep this as a small deterministic post-process until the generator exposes a flag that
preserves omitted-only fields for pydantic v2.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "py" / "ithaca_contracts" / "generated"

REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "platform_run.py": [
        ("payload: dict[str, Any] | None = {}", "payload: dict[str, Any] = {}"),
        ("max_attempts: int | None = Field(None, ge=1)", "max_attempts: int = Field(None, ge=1)"),
        ("metadata: dict[str, Any] | None = {}", "metadata: dict[str, Any] = {}"),
        ("job: Job | None = None", "job: Job = None"),
        ("attempts: list[RunAttempt] | None = []", "attempts: list[RunAttempt] = []"),
        ("artifacts: list[Artifact] | None = []", "artifacts: list[Artifact] = []"),
    ],
    "execution.py": [
        ("orders: list[Order] | None = []", "orders: list[Order] = []"),
        ("fills: list[Fill] | None = []", "fills: list[Fill] = []"),
    ],
    "skill_manifest.py": [
        ("cpu: float | None = Field(None, ge=0.0)", "cpu: float = Field(None, ge=0.0)"),
        ("memory_mb: int | None = Field(None, ge=0)", "memory_mb: int = Field(None, ge=0)"),
        ("datasets: list[str] | None = []", "datasets: list[str] = []"),
        ("broker: list[str] | None = []", "broker: list[str] = []"),
        ("network: list[str] | None = []", "network: list[str] = []"),
        ("source_classes: list[SourceClass] | None = []", "source_classes: list[SourceClass] = []"),
        ("artifact_types: list[str] | None = []", "artifact_types: list[str] = []"),
    ],
    "trigger_policy.py": [
        ("notify: Notify | None = {}", "notify: Notify = {}"),
    ],
}


def main() -> int:
    for filename, replacements in REPLACEMENTS.items():
        path = ROOT / filename
        text = path.read_text()
        for old, new in replacements:
            if old not in text and new not in text:
                raise SystemExit(f"{filename}: expected generated line missing: {old}")
            text = text.replace(old, new)
        path.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
