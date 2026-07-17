"""Held first-document policy (v0.2 §5.4): the first document of an unknown
template is held in `pending_template_review`; once the template + mask
release unit activates, the held document's already-extracted content is
mapped WITHOUT re-extraction when it is compatible with the activated
template (every observed element resolves), and re-extracted otherwise.
"""

from __future__ import annotations

from domain.artifacts.content import ContentBody
from domain.artifacts.template import TemplateBody, TemplateRef
from services.lifecycle.held import HeldDocumentPolicy
from tests.unit.services.lifecycle._fixtures import load_artifact_json, load_template


def load_content_body(name: str) -> ContentBody:
    return ContentBody.model_validate(load_artifact_json(name)["body"])


def hold_fixture_document(policy: HeldDocumentPolicy) -> tuple[ContentBody, TemplateBody]:
    content = load_content_body("content_nv20260042.v1")
    template = load_template("tmpl_nvinv.v1").body
    return content, template


def test_first_document_of_unknown_template_is_held_pending_template_review() -> None:
    policy = HeldDocumentPolicy()

    held = policy.hold(
        document_id="doc_nv20260042",
        tenant_id="t-nordvik",
        fingerprint="fpv1:sha256:" + "c4" * 32,
        at=1000.0,
    )

    assert held.state == "pending_template_review"
    assert held.document_id == "doc_nv20260042"
    assert held.tenant_id == "t-nordvik"
    assert held.held_at == 1000.0


def test_compatible_content_is_mapped_after_activation_without_reextraction() -> None:
    policy = HeldDocumentPolicy()
    content, template = hold_fixture_document(policy)
    held = policy.hold(document_id="doc_nv20260042", tenant_id="t-nordvik", fingerprint=template.fingerprint, at=1000.0)

    decision = policy.release_decision(held, content, template)

    assert decision.action == "map_without_reextraction"
    assert decision.document_id == "doc_nv20260042"
    assert decision.template_ref == TemplateRef(template_id="tmpl_nvinv", version=1)


def test_incompatible_content_requires_reextraction_not_guessing() -> None:
    policy = HeldDocumentPolicy()
    content, template = hold_fixture_document(policy)
    held = policy.hold(document_id="doc_nv20260042", tenant_id="t-nordvik", fingerprint=template.fingerprint, at=1000.0)
    # The activated template lost an element the held content observed.
    shrunk = template.model_copy(
        update={"elements": [element for element in template.elements if element.element_id != "el_notes"]}
    )

    decision = policy.release_decision(held, content, shrunk)

    assert decision.action == "reextract"
    assert "el_notes" in decision.reason
