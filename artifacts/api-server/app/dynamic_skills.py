"""Loader for AI-generated, additive skills.

Generated skills live as standalone ``.py`` modules in ``skills_generated/``.
Each module must expose:

- ``SKILL_DEFINITION``: a dict describing the skill (id, name, panel_type,
  description, default_title, subskills, invoke_phrases, parameters).
- ``build(params: dict) -> dict``: a builder that returns the panel ``data``
  dict (optionally with ``asOf``/``source`` keys, stripped by the harness).

The loader imports each module in-process and registers a :class:`skills.SkillDef`
into ``skills.SKILLS`` so the orchestrator can dispatch it WITHOUT a server
restart. Panel types from generated skills have no pydantic model, so the
harness passes their data through untouched.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from typing import Dict, List

from . import code_guard, skills

log = logging.getLogger("dynamic_skills")

GENERATED_DIR = os.path.join(os.path.dirname(__file__), "skills_generated")

# panel_type -> the raw SKILL_DEFINITION dict (used to build tools/heuristics).
_DEFINITIONS: Dict[str, dict] = {}

_REQUIRED_KEYS = ("id", "name", "panel_type", "description")


def ensure_dir() -> None:
    os.makedirs(GENERATED_DIR, exist_ok=True)


def _module_path(panel_type: str) -> str:
    return os.path.join(GENERATED_DIR, f"{panel_type}.py")


def _import_module(path: str):
    # Re-run the static safety audit on the on-disk source BEFORE executing it.
    # This guards files imported at startup as well as freshly generated ones, so
    # a module that bypassed the build pipeline can never execute in-process.
    with open(path, "r", encoding="utf-8") as fh:
        code_guard.validate_python_source(fh.read())
    name = "app.skills_generated." + os.path.splitext(os.path.basename(path))[0]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _validate_definition(definition: dict) -> None:
    if not isinstance(definition, dict):
        raise ValueError("SKILL_DEFINITION must be a dict")
    for key in _REQUIRED_KEYS:
        if not definition.get(key):
            raise ValueError(f"SKILL_DEFINITION missing required key: {key}")
    pt = definition["panel_type"]
    if not isinstance(pt, str) or not pt.replace("_", "").isalnum():
        raise ValueError(f"invalid panel_type: {pt!r}")


def register_module(module) -> dict:
    """Validate and register a single generated module. Returns its definition."""
    definition = getattr(module, "SKILL_DEFINITION", None)
    _validate_definition(definition)
    builder = getattr(module, "build", None)
    if not callable(builder):
        raise ValueError("module must define a callable build(params)")

    pt = definition["panel_type"]
    skill = skills.SkillDef(
        id=definition["id"],
        name=definition["name"],
        panel_type=pt,
        description=definition["description"],
        subskills=definition.get("subskills") or [],
        builder=builder,
        default_title=definition.get("default_title") or definition["name"],
    )
    skills.SKILLS[pt] = skill
    _DEFINITIONS[pt] = definition
    return definition


def load_one(panel_type: str) -> dict:
    """Import+register a single generated skill by panel_type. Raises on failure."""
    module = _import_module(_module_path(panel_type))
    return register_module(module)


def unregister(panel_type: str) -> bool:
    """Remove a generated skill from the in-process registry.

    Drops it from both ``skills.SKILLS`` and the local definitions map so the
    orchestrator can no longer dispatch it. Returns True if it was registered.
    Does NOT touch any files on disk — callers handle removal of the source.
    """
    was_dynamic = panel_type in _DEFINITIONS
    _DEFINITIONS.pop(panel_type, None)
    if skills.SKILLS.get(panel_type) is not None and was_dynamic:
        skills.SKILLS.pop(panel_type, None)
    return was_dynamic


def get_definition(panel_type: str) -> dict | None:
    return _DEFINITIONS.get(panel_type)


def load_generated_skills() -> List[str]:
    """Scan the generated dir and (re)register every valid skill in-process.

    Returns the list of panel_types successfully loaded. Failures are logged and
    skipped so one bad module never blocks the others or the server startup.
    """
    ensure_dir()
    loaded: List[str] = []
    for fname in sorted(os.listdir(GENERATED_DIR)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        path = os.path.join(GENERATED_DIR, fname)
        try:
            module = _import_module(path)
            definition = register_module(module)
            loaded.append(definition["panel_type"])
        except Exception:  # noqa: BLE001 — never let one module break the rest
            log.exception("Failed to load generated skill: %s", fname)
    if loaded:
        log.info("Loaded %d generated skill(s): %s", len(loaded), ", ".join(loaded))
    return loaded


def get_definitions() -> List[dict]:
    return list(_DEFINITIONS.values())


def is_dynamic(panel_type: str) -> bool:
    return panel_type in _DEFINITIONS


def panel_types() -> List[str]:
    return list(_DEFINITIONS.keys())
