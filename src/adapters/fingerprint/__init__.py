"""Fingerprint adapters (epic E04): born-digital + scanned feature
extraction, the fpv version registry, and the default `TemplateVerifier`.

Excluded by construction: this package and every module in it import
`pypdf` + stdlib only — never OCR, region classification, or VLM/model
provider modules. Enforced by
`tests/unit/adapters/fingerprint/test_architecture_no_provider_imports.py`,
which statically inspects every module's `import`/`from` statements.
"""

from __future__ import annotations
