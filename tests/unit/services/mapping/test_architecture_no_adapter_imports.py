"""E09 architecture test (import graph, AST-based like the E01/E04/E10 idiom):
`src/services/mapping` imports ZERO adapter modules — statelessness/purity
proven statically. No DB driver, no framework, no clock, no randomness
source: the pipeline's output is a pure function of its inputs, so the same
inputs twice yield byte-identical MappingResult JSON.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "src"
MAPPING_PACKAGE_DIR = SRC / "services" / "mapping"

# Name-based ban, deliberately broad: any adapter, DB driver, or framework
# showing up in the mapping service is a review-blocking defect.
_BANNED_IMPORT_SUBSTRINGS = (
    "adapters",
    "psycopg",
    "sqlalchemy",
    "asyncpg",
    "sqlite",
    "fastapi",
)

# Nondeterminism sources, banned by exact module root ("datetime" is allowed
# for pure date PARSING — `date.fromisoformat` — while "time"/"random"/"uuid"
# style entropy and clock reads are what break byte-identical output).
_BANNED_MODULE_ROOTS = frozenset({"random", "secrets", "uuid", "time"})

_ALLOWED_TOP_LEVEL = {
    "__future__",
    "collections",
    "dataclasses",
    "datetime",
    "domain",
    "pydantic",
    "services",
    "typing",
}


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _package_py_files() -> list[Path]:
    # rglob: steps/ is a subpackage. Excludes macOS AppleDouble shadow files.
    return sorted(path for path in MAPPING_PACKAGE_DIR.rglob("*.py") if not path.name.startswith("._"))


def test_mapping_service_package_imports_zero_adapter_or_nondeterminism_modules() -> None:
    py_files = _package_py_files()
    assert py_files, f"expected mapping service modules under {MAPPING_PACKAGE_DIR}"

    violations = [
        f"{path.relative_to(MAPPING_PACKAGE_DIR)}: banned import {module!r}"
        for path in py_files
        for module in _imported_module_names(path.read_text(encoding="utf-8"))
        if any(banned in module.lower() for banned in _BANNED_IMPORT_SUBSTRINGS)
        or module.split(".")[0] in _BANNED_MODULE_ROOTS
    ]
    assert not violations, f"mapping service package must stay pure: {violations}"


def test_mapping_service_package_only_imports_from_its_allow_list() -> None:
    violations = [
        f"{path.relative_to(MAPPING_PACKAGE_DIR)}: import {module!r} not in allow-list"
        for path in _package_py_files()
        for module in _imported_module_names(path.read_text(encoding="utf-8"))
        if module.split(".")[0] not in _ALLOWED_TOP_LEVEL
    ]
    assert not violations, f"mapping service package has an unreviewed import: {violations}"


def test_mapping_service_never_imports_from_services_outside_its_own_package() -> None:
    """`services.*` imports must stay within services.mapping itself — the
    pipeline depends on domain vocabulary and its own steps, nothing else."""
    violations = [
        f"{path.relative_to(MAPPING_PACKAGE_DIR)}: cross-service import {module!r}"
        for path in _package_py_files()
        for module in _imported_module_names(path.read_text(encoding="utf-8"))
        if module.startswith("services") and not module.startswith("services.mapping")
    ]
    assert not violations, f"mapping service reached into another service package: {violations}"
