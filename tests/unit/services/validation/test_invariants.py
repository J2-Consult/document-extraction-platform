"""InvariantValidator (src/services/validation/): the platform's contract law.

Mutation coverage (one test per invariant, per specs/epics/E01-artifact-contracts.md
"Tests first" list — each constructs a bundle by mutating a *parsed, valid*
fixture artifact via `model_copy(update=...)`, which bypasses Pydantic field
validation the same way an in-process caller assembling a bundle from partial
data could, then asserts the InvariantValidator rejects it with the itemized
path+code+message the epic requires):

  1. unknown_element_id                    -> code "unknown-element-id"
  2. missing_provenance                    -> code "missing-provenance"
  3. envelope_body_contradiction            -> code "envelope-body-mismatch"
  4. illegal_state_present_without_value    -> code "state-value-conflict"
  5. illegal_state_non_present_with_value   -> code "state-value-conflict" (the reverse direction)
  6. vendor_mask_with_tenant_id             -> code "vendor-mask-with-tenant"
  7. overridden_without_inherited_from      -> code "overridden-without-inherited-from"
  8. bad_fingerprint_format                 -> code "bad-fingerprint-format"

Additional coverage beyond the epic's mandatory list, exercising the other
half of invariants whose full statement is a biconditional or a "some/all"
rule (FIXTURES-SPEC.md's decoder-mask body rules), not scope creep — these
sub-rules are implemented by the same check modules the mandatory list above
already requires:

  9. customer_mask_missing_tenant_id        -> code "customer-mask-missing-tenant"
 10. vendor_entry_missing_validated_by      -> code "vendor-entry-missing-validated-by"
 11. unknown_element_id_via_mask_entry      -> code "unknown-element-id" (mask path, not content)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from domain.artifacts.content import ContentArtifact
from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.template import TemplateArtifact
from services.validation.bundle import ArtifactBundle
from services.validation.validator import default_validator

# Relative, not `from tests.unit.domain._loaders import ...`: see
# tests/unit/domain/test_artifact_models.py's comment on why.
from ...domain._loaders import ALL_FIXTURE_ARTIFACT_NAMES, parse_fixture_artifact

REPO_ROOT = Path(__file__).resolve().parents[4]

# Fixture artifact name -> the template fixture name it references, or None.
_TEMPLATE_FOR_FIXTURE: dict[str, str | None] = {
    "tmpl_nvinv.v1": None,
    "tmpl_mbr.v1": None,
    "mask_nvvendor.v1": "tmpl_nvinv.v1",
    "mask_nvcust.v1": "tmpl_nvinv.v1",
    "mask_mbrvendor.v1": "tmpl_mbr.v1",
    "content_nv20260042.v1": "tmpl_nvinv.v1",
    "content_nv20260043.v1": "tmpl_nvinv.v1",
    "content_mbr001.v1": None,
}


def _bundle_for(fixture_name: str, load_fixture_artifact: object) -> ArtifactBundle:
    artifact = parse_fixture_artifact(load_fixture_artifact(fixture_name))  # type: ignore[operator]
    template_name = _TEMPLATE_FOR_FIXTURE[fixture_name]
    template = (
        parse_fixture_artifact(load_fixture_artifact(template_name))  # type: ignore[operator]
        if template_name is not None
        else None
    )
    assert template is None or isinstance(template, TemplateArtifact)
    if isinstance(artifact, TemplateArtifact):
        return ArtifactBundle(template=artifact)
    if isinstance(artifact, ContentArtifact):
        return ArtifactBundle(template=template, content=artifact)
    return ArtifactBundle(template=template, mask=artifact)


def _codes(bundle: ArtifactBundle) -> set[str]:
    return {violation.code for violation in default_validator().validate(bundle).violations}


def _violation(bundle: ArtifactBundle, code: str) -> object:
    report = default_validator().validate(bundle)
    matches = [v for v in report.violations if v.code == code]
    assert matches, f"expected a violation with code {code!r}, got {[v.code for v in report.violations]}"
    return matches[0]


def _with_content(base: ArtifactBundle, content: ContentArtifact) -> ArtifactBundle:
    return ArtifactBundle(template=base.template, content=content)


def _with_mask(base: ArtifactBundle, mask: DecoderMaskArtifact) -> ArtifactBundle:
    return ArtifactBundle(template=base.template, mask=mask)


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_ARTIFACT_NAMES)
def test_every_fixture_artifact_validates_clean(fixture_name: str, load_fixture_artifact: object) -> None:
    bundle = _bundle_for(fixture_name, load_fixture_artifact)

    report = default_validator().validate(bundle)

    assert report.ok is True
    assert report.violations == ()


# --- 1. unknown_element_id (content path) -----------------------------------


def test_unknown_element_id_in_content_observation_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("content_nv20260042.v1", load_fixture_artifact)
    assert isinstance(bundle.content, ContentArtifact)
    observations = list(bundle.content.body.observations)
    observations[0] = observations[0].model_copy(update={"element_id": "el_does_not_exist"})
    mutated_content = bundle.content.model_copy(
        update={"body": bundle.content.body.model_copy(update={"observations": observations})}
    )

    mutated = _with_content(bundle, mutated_content)

    violation = _violation(mutated, "unknown-element-id")
    assert violation.path == "/body/observations/0/element_id"  # type: ignore[attr-defined]


# --- 2. missing_provenance ---------------------------------------------------


def test_missing_provenance_on_an_observation_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("content_nv20260042.v1", load_fixture_artifact)
    assert isinstance(bundle.content, ContentArtifact)
    observations = list(bundle.content.body.observations)
    observations[0] = observations[0].model_copy(update={"provenance": None})
    mutated_content = bundle.content.model_copy(
        update={"body": bundle.content.body.model_copy(update={"observations": observations})}
    )

    mutated = _with_content(bundle, mutated_content)

    violation = _violation(mutated, "missing-provenance")
    assert violation.path == "/body/observations/0/provenance"  # type: ignore[attr-defined]


# --- 3. envelope_body_contradiction ------------------------------------------


def test_envelope_artifact_id_disagreeing_with_body_id_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("content_nv20260042.v1", load_fixture_artifact)
    assert isinstance(bundle.content, ContentArtifact)

    mutated_content = bundle.content.model_copy(update={"artifact_id": "content_someone_else"})
    mutated = _with_content(bundle, mutated_content)

    violation = _violation(mutated, "envelope-body-mismatch")
    assert violation.path == "/body/content_id"  # type: ignore[attr-defined]


def test_envelope_version_disagreeing_with_body_version_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("tmpl_nvinv.v1", load_fixture_artifact)
    assert isinstance(bundle.template, TemplateArtifact)

    mutated_template = bundle.template.model_copy(update={"version": 2})
    mutated = ArtifactBundle(template=mutated_template)

    violation = _violation(mutated, "envelope-body-mismatch")
    assert violation.path == "/body/version"  # type: ignore[attr-defined]


# --- 4. illegal_state_present_without_value ----------------------------------


def test_state_present_with_null_value_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("content_nv20260042.v1", load_fixture_artifact)
    assert isinstance(bundle.content, ContentArtifact)
    observations = list(bundle.content.body.observations)
    assert observations[0].state == "present"
    observations[0] = observations[0].model_copy(update={"value": None})
    mutated_content = bundle.content.model_copy(
        update={"body": bundle.content.body.model_copy(update={"observations": observations})}
    )

    mutated = _with_content(bundle, mutated_content)

    violation = _violation(mutated, "state-value-conflict")
    assert violation.path == "/body/observations/0/value"  # type: ignore[attr-defined]


# --- 5. illegal_state_non_present_with_value (the reverse direction) --------


def test_state_empty_with_non_null_value_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("content_nv20260042.v1", load_fixture_artifact)
    assert isinstance(bundle.content, ContentArtifact)
    observations = list(bundle.content.body.observations)
    empty_index = next(i for i, obs in enumerate(observations) if obs.state == "empty")
    observations[empty_index] = observations[empty_index].model_copy(update={"value": "unexpectedly present"})
    mutated_content = bundle.content.model_copy(
        update={"body": bundle.content.body.model_copy(update={"observations": observations})}
    )

    mutated = _with_content(bundle, mutated_content)

    violation = _violation(mutated, "state-value-conflict")
    assert violation.path == f"/body/observations/{empty_index}/value"  # type: ignore[attr-defined]


# --- 6. vendor_mask_with_tenant_id -------------------------------------------


def test_vendor_scope_mask_with_non_null_tenant_id_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("mask_nvvendor.v1", load_fixture_artifact)
    assert isinstance(bundle.mask, DecoderMaskArtifact)

    mutated_body = bundle.mask.body.model_copy(update={"tenant_id": "t-nordvik"})
    mutated_mask = bundle.mask.model_copy(update={"body": mutated_body})
    mutated = _with_mask(bundle, mutated_mask)

    violation = _violation(mutated, "vendor-mask-with-tenant")
    assert violation.path == "/body/tenant_id"  # type: ignore[attr-defined]


# --- 7. overridden_without_inherited_from ------------------------------------


def test_overridden_entry_without_inherited_from_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("mask_nvcust.v1", load_fixture_artifact)
    assert isinstance(bundle.mask, DecoderMaskArtifact)
    entries = list(bundle.mask.body.entries)
    overridden_index = next(i for i, e in enumerate(entries) if e.attribution.overridden)
    entries[overridden_index] = entries[overridden_index].model_copy(
        update={"attribution": entries[overridden_index].attribution.model_copy(update={"inherited_from": None})}
    )
    mutated_mask = bundle.mask.model_copy(update={"body": bundle.mask.body.model_copy(update={"entries": entries})})

    mutated = _with_mask(bundle, mutated_mask)

    violation = _violation(mutated, "overridden-without-inherited-from")
    assert violation.path == f"/body/entries/{overridden_index}/attribution/inherited_from"  # type: ignore[attr-defined]


# --- 8. bad_fingerprint_format ------------------------------------------------


def test_malformed_fingerprint_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("tmpl_nvinv.v1", load_fixture_artifact)
    assert isinstance(bundle.template, TemplateArtifact)

    mutated_template = bundle.template.model_copy(
        update={"body": bundle.template.body.model_copy(update={"fingerprint": "not-a-real-fingerprint"})}
    )
    mutated = ArtifactBundle(template=mutated_template)

    violation = _violation(mutated, "bad-fingerprint-format")
    assert violation.path == "/body/fingerprint"  # type: ignore[attr-defined]


# --- 9. customer_mask_missing_tenant_id (biconditional's other direction) ---


def test_customer_scope_mask_with_null_tenant_id_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("mask_nvcust.v1", load_fixture_artifact)
    assert isinstance(bundle.mask, DecoderMaskArtifact)

    mutated_mask = bundle.mask.model_copy(update={"body": bundle.mask.body.model_copy(update={"tenant_id": None})})
    mutated = _with_mask(bundle, mutated_mask)

    assert "customer-mask-missing-tenant" in _codes(mutated)


# --- 10. vendor_entry_missing_validated_by -----------------------------------


def test_vendor_scope_entry_without_validated_by_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("mask_nvvendor.v1", load_fixture_artifact)
    assert isinstance(bundle.mask, DecoderMaskArtifact)
    entries = list(bundle.mask.body.entries)
    entries[0] = entries[0].model_copy(
        update={"attribution": entries[0].attribution.model_copy(update={"validated_by": None})}
    )
    mutated_mask = bundle.mask.model_copy(update={"body": bundle.mask.body.model_copy(update={"entries": entries})})

    mutated = _with_mask(bundle, mutated_mask)

    assert "vendor-entry-missing-validated-by" in _codes(mutated)


# --- 11. unknown_element_id via a mask entry (not the content path) ---------


def test_unknown_element_id_in_mask_entry_is_rejected(load_fixture_artifact: object) -> None:
    bundle = _bundle_for("mask_nvvendor.v1", load_fixture_artifact)
    assert isinstance(bundle.mask, DecoderMaskArtifact)
    entries = list(bundle.mask.body.entries)
    entries[0] = entries[0].model_copy(update={"element_id": "el_ghost"})
    mutated_mask = bundle.mask.model_copy(update={"body": bundle.mask.body.model_copy(update={"entries": entries})})

    mutated = _with_mask(bundle, mutated_mask)

    violation = _violation(mutated, "unknown-element-id")
    assert violation.path == "/body/entries/0/element_id"  # type: ignore[attr-defined]


# --- purity: no framework imports anywhere in the domain/services.validation graph --


def test_invariant_validator_import_graph_has_no_framework_imports() -> None:
    """InvariantValidator (and everything it pulls in — domain/artifacts/*,
    domain/registry.py) must never import fastapi or sqlalchemy. Run in a
    fresh subprocess: within this test process other modules may already have
    imported those packages, which would give a false pass/fail either way."""
    probe = (
        "import sys\n"
        "import services.validation.validator\n"
        "import domain.registry\n"
        "loaded = set(sys.modules)\n"
        "forbidden = {m for m in loaded if m.startswith(('fastapi', 'sqlalchemy'))}\n"
        "assert not forbidden, f'framework modules leaked into domain import graph: {forbidden}'\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "src"), str(REPO_ROOT)])}

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
