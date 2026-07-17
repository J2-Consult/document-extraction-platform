"""E10 architecture test (import graph, AST-based like the E04 fingerprint
idiom): the orchestrator SERVICE package has no SQL surface — it imports no
DB driver and no adapter; it sees the world only through `ports.retrieval`.
The Postgres-backed implementation lives in `src/adapters/orchestrator/` and
may import ONLY `adapters.postgres.queries` (E07's sanctioned read seam) from
the postgres adapter package — never `session`, never raw SQL of its own.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "src"
SERVICE_PACKAGE_DIR = SRC / "services" / "orchestrator"
ADAPTER_PACKAGE_DIR = SRC / "adapters" / "orchestrator"
PORT_FILE = SRC / "ports" / "retrieval.py"

# Name-based ban, deliberately broad: any DB driver / ORM / framework showing
# up in the LLM-facing service package is a review-blocking defect.
_BANNED_SERVICE_IMPORT_SUBSTRINGS = (
    "psycopg",
    "sqlalchemy",
    "asyncpg",
    "sqlite",
    "adapters",
    "fastapi",
)

_SERVICE_ALLOWED_TOP_LEVEL = {
    "__future__",
    "collections",
    "dataclasses",
    "logging",
    "math",
    "ports",
    "re",
    "services",
    "typing",
}

_PORT_ALLOWED_TOP_LEVEL = {"__future__", "collections", "dataclasses", "typing"}

_ADAPTER_ALLOWED_TOP_LEVEL = {"__future__", "adapters", "collections", "psycopg", "ports", "typing"}


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _package_py_files(package_dir: Path) -> list[Path]:
    # Excludes macOS AppleDouble shadow files (`._foo.py`).
    return sorted(path for path in package_dir.glob("*.py") if not path.name.startswith("._"))


def test_orchestrator_service_package_imports_no_db_driver_or_adapter() -> None:
    py_files = _package_py_files(SERVICE_PACKAGE_DIR)
    assert py_files, f"expected orchestrator service modules under {SERVICE_PACKAGE_DIR}"

    violations = [
        f"{path.name}: banned import {module!r}"
        for path in py_files
        for module in _imported_module_names(path.read_text(encoding="utf-8"))
        if any(banned in module.lower() for banned in _BANNED_SERVICE_IMPORT_SUBSTRINGS)
    ]
    assert not violations, f"orchestrator service package has a SQL/adapter surface: {violations}"


def test_orchestrator_service_package_only_imports_from_its_allow_list() -> None:
    violations = [
        f"{path.name}: import {module!r} not in allow-list"
        for path in _package_py_files(SERVICE_PACKAGE_DIR)
        for module in _imported_module_names(path.read_text(encoding="utf-8"))
        if module.split(".")[0] not in _SERVICE_ALLOWED_TOP_LEVEL
    ]
    assert not violations, f"orchestrator service package has an unreviewed import: {violations}"


def test_retrieval_port_is_pure_vocabulary() -> None:
    violations = [
        f"ports/retrieval.py: import {module!r} not in allow-list"
        for module in _imported_module_names(PORT_FILE.read_text(encoding="utf-8"))
        if module.split(".")[0] not in _PORT_ALLOWED_TOP_LEVEL
    ]
    assert not violations, f"retrieval port must stay pure: {violations}"


def test_orchestrator_adapter_reaches_postgres_only_through_the_e07_query_seam() -> None:
    py_files = _package_py_files(ADAPTER_PACKAGE_DIR)
    assert py_files, f"expected orchestrator adapter modules under {ADAPTER_PACKAGE_DIR}"

    violations: list[str] = []
    for path in py_files:
        for module in _imported_module_names(path.read_text(encoding="utf-8")):
            if module.split(".")[0] not in _ADAPTER_ALLOWED_TOP_LEVEL:
                violations.append(f"{path.name}: import {module!r} not in allow-list")
            if module.startswith("adapters.") and module not in (
                "adapters.postgres.queries",
                "adapters.orchestrator",
            ):
                violations.append(f"{path.name}: adapter seam violation {module!r}")
    assert not violations, f"orchestrator adapter must use only the E07 query seam: {violations}"
