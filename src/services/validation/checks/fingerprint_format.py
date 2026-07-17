"""Template fingerprints must match `^fpv\\d+:sha256:[0-9a-f]{64}$`.

`TemplateBody.fingerprint` is a plain, unconstrained string at the Pydantic
level (see template.py) precisely so a malformed fingerprint parses cleanly
and lands here as an itemized violation instead of a Pydantic parse error.
"""

from __future__ import annotations

import re

from domain.artifacts.errors import InvariantViolation
from domain.artifacts.template import FINGERPRINT_PATTERN
from services.validation.bundle import ArtifactBundle

CODE = "bad-fingerprint-format"

_FINGERPRINT_RE = re.compile(FINGERPRINT_PATTERN)


class FingerprintFormatCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.template is None:
            return []
        fingerprint = bundle.template.body.fingerprint
        if _FINGERPRINT_RE.match(fingerprint):
            return []
        return [
            InvariantViolation(
                path="/body/fingerprint",
                code=CODE,
                message="fingerprint does not match ^fpv<N>:sha256:<hex64>$",
            )
        ]
