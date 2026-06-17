"""Static safety guard for AI-generated skill code.

The self-building feature lets an LLM author a Python skill module that is later
imported in-process and executed. Before any generated source is written to disk
or executed, it is run through :func:`validate_python_source`, an allow-list based
AST audit that rejects anything outside the narrow "stdlib-only synthetic data
builder" contract: dangerous imports, ``eval``/``exec``/``compile``/``__import__``,
filesystem/network access, dynamic attribute escapes (``getattr``/dunder access),
and so on.

This is the first line of defense. It runs *before* the isolated validation
subprocess and *before* the in-process import, so a malicious or malformed
generation is rejected cleanly with nothing written and nothing executed.
"""
from __future__ import annotations

import ast
from typing import List

# Stdlib modules a synthetic-data builder legitimately needs. Roots only — any
# submodule of an allowed root is allowed (e.g. ``datetime`` -> ``datetime.timezone``).
ALLOWED_IMPORT_ROOTS = frozenset({
    "math",
    "random",
    "datetime",
    "statistics",
    "json",
    "collections",
    "itertools",
    "functools",
    "re",
    "decimal",
    "fractions",
    "string",
    "enum",
    "dataclasses",
    "typing",
    "calendar",
    "time",
    "bisect",
    "heapq",
    "numbers",
    "operator",
    "copy",
    "textwrap",
    "uuid",
    "hashlib",
    "secrets",
    "array",
    "abc",
    "__future__",
})

# Builtins that enable code execution, dynamic import, IO, or sandbox escapes.
# Referencing any of these names (calling them or passing them around) is rejected.
BANNED_NAMES = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
    "help",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "memoryview",
    "__builtins__",
})


class CodeGuardError(ValueError):
    """Raised when generated source violates the safety contract."""


def _is_dunder(name: str) -> bool:
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


class _Auditor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: List[str] = []

    # --- imports -------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                self.violations.append(f"import of disallowed module '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level and node.level > 0:
            self.violations.append("relative imports are not allowed")
        elif node.module:
            root = node.module.split(".")[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                self.violations.append(f"import from disallowed module '{node.module}'")
        else:
            self.violations.append("malformed import")
        self.generic_visit(node)

    # --- names & attributes -------------------------------------------
    def visit_Name(self, node: ast.Name) -> None:
        if node.id in BANNED_NAMES:
            self.violations.append(f"use of disallowed name '{node.id}'")
        elif _is_dunder(node.id):
            self.violations.append(f"use of disallowed dunder name '{node.id}'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_dunder(node.attr):
            self.violations.append(f"access to disallowed dunder attribute '{node.attr}'")
        self.generic_visit(node)

    # --- dynamic execution / escapes ----------------------------------
    def _check_func_name(self, func: ast.AST) -> None:
        if isinstance(func, ast.Name) and func.id in BANNED_NAMES:
            self.violations.append(f"call to disallowed function '{func.id}'")

    def visit_Call(self, node: ast.Call) -> None:
        self._check_func_name(node.func)
        self.generic_visit(node)


def validate_python_source(code: str) -> None:
    """Audit generated Python source. Raises :class:`CodeGuardError` on violation.

    Parses the source and walks the AST, rejecting anything outside the
    stdlib-only builder contract. Performs no execution.
    """
    if not isinstance(code, str) or not code.strip():
        raise CodeGuardError("generated code is empty")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise CodeGuardError(f"generated code has a syntax error: {exc.msg}") from exc

    auditor = _Auditor()
    auditor.visit(tree)
    if auditor.violations:
        # De-duplicate while preserving order so the message is concise.
        seen: List[str] = []
        for v in auditor.violations:
            if v not in seen:
                seen.append(v)
        raise CodeGuardError(
            "generated code rejected by safety guard: " + "; ".join(seen)
        )
