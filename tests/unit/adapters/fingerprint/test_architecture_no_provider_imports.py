"""Architecture test: `src/adapters/fingerprint/` imports no OCR/VLM/model
provider module — enforced statically (AST inspection of every module's
`import`/`from` statements), not by "no such package is installed", so the
test fails loudly even if such a package were later added to the
environment for an unrelated reason.
"""

from __future__ import annotations

import ast
from pathlib import Path

FINGERPRINT_PACKAGE_DIR = Path(__file__).resolve().parents[4] / "src" / "adapters" / "fingerprint"

# Substrings banned anywhere in an imported module's dotted path. Deliberately
# broad (name-based, not an allow-list) so a new banned dependency doesn't
# need a matching test update — only an allow-listed import ever needs one.
_BANNED_IMPORT_SUBSTRINGS = (
    "ocr",
    "tesseract",
    "vlm",
    "vision",
    "openai",
    "anthropic",
    "google.generativeai",
    "genai",
    "mistralai",
    "cohere",
    "ollama",
    "boto3",  # cloud model/vision APIs
    "torch",
    "transformers",
)

_ALLOWED_TOP_LEVEL_IMPORTS = {
    # stdlib + this package's own modules + the ports/domain vocabulary it's
    # allowed to depend on.
    "__future__",
    "adapters",
    "ast",
    "collections",
    "concurrent",
    "dataclasses",
    "domain",
    "hashlib",
    "io",
    "json",
    "pathlib",
    "ports",
    "pypdf",
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


def _fingerprint_package_py_files() -> list[Path]:
    # Excludes macOS AppleDouble shadow files (`._foo.py`) that this
    # filesystem sometimes materializes alongside real files — they are not
    # valid UTF-8 Python source and were never written by this epic.
    return sorted(path for path in FINGERPRINT_PACKAGE_DIR.glob("*.py") if not path.name.startswith("._"))


def test_fingerprint_package_imports_no_banned_ocr_vlm_or_provider_modules() -> None:
    py_files = _fingerprint_package_py_files()
    assert py_files, f"expected fingerprint adapter modules under {FINGERPRINT_PACKAGE_DIR}"

    violations: list[str] = []
    for path in py_files:
        for module_name in _imported_module_names(path.read_text(encoding="utf-8")):
            lowered = module_name.lower()
            if any(banned in lowered for banned in _BANNED_IMPORT_SUBSTRINGS):
                violations.append(f"{path.name}: banned import {module_name!r}")

    assert not violations, f"fingerprint package imported a banned OCR/VLM/provider module: {violations}"


def test_fingerprint_package_only_imports_from_its_own_allow_list() -> None:
    """Belt-and-braces: every top-level import root must be in the explicit
    allow-list above, so a genuinely new dependency (banned or not) requires
    a deliberate edit to this test rather than silently passing."""
    py_files = _fingerprint_package_py_files()

    violations: list[str] = []
    for path in py_files:
        for module_name in _imported_module_names(path.read_text(encoding="utf-8")):
            root = module_name.split(".")[0]
            if root not in _ALLOWED_TOP_LEVEL_IMPORTS:
                violations.append(f"{path.name}: import {module_name!r} not in allow-list")

    assert not violations, f"fingerprint package has an unreviewed import: {violations}"
