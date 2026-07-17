"""Envelope-level `artifact_id`/`version`/`tenant_id` must agree with the
values a body repeats internally — a self-consistency rule JSON Schema cannot
express because it spans the envelope and body sibling subtrees independently.
"""

from __future__ import annotations

from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "envelope-body-mismatch"


class EnvelopeAgreementCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        return [
            *self._check_template(bundle),
            *self._check_content(bundle),
            *self._check_mask(bundle),
        ]

    def _check_template(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.template is None:
            return []
        envelope, body = bundle.template, bundle.template.body
        return [
            *_id_mismatch(envelope.artifact_id, body.template_id, "/body/template_id"),
            *_version_mismatch(envelope.version, body.version),
        ]

    def _check_content(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        envelope, body = bundle.content, bundle.content.body
        return [
            *_id_mismatch(envelope.artifact_id, body.content_id, "/body/content_id"),
            *_version_mismatch(envelope.version, body.version),
        ]

    def _check_mask(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.mask is None:
            return []
        envelope, body = bundle.mask, bundle.mask.body
        return [
            *_id_mismatch(envelope.artifact_id, body.mask_id, "/body/mask_id"),
            *_version_mismatch(envelope.version, body.version),
            *_tenant_mismatch(envelope.tenant_id, body.tenant_id),
        ]


def _id_mismatch(envelope_id: str, body_id: str, body_path: str) -> list[InvariantViolation]:
    if envelope_id == body_id:
        return []
    return [
        InvariantViolation(
            path=body_path,
            code=CODE,
            message=f"body id '{body_id}' does not match envelope artifact_id '{envelope_id}'",
        )
    ]


def _version_mismatch(envelope_version: int, body_version: int) -> list[InvariantViolation]:
    if envelope_version == body_version:
        return []
    return [
        InvariantViolation(
            path="/body/version",
            code=CODE,
            message=f"body version {body_version} does not match envelope version {envelope_version}",
        )
    ]


def _tenant_mismatch(envelope_tenant_id: str | None, body_tenant_id: str | None) -> list[InvariantViolation]:
    if envelope_tenant_id == body_tenant_id:
        return []
    return [
        InvariantViolation(
            path="/body/tenant_id",
            code=CODE,
            message="body tenant_id does not match envelope tenant_id",
        )
    ]
