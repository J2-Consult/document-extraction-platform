"""Test-only helper: parse a fixture artifact dict into its typed model.

Not a test module itself (no `test_` prefix) — shared by
tests/unit/domain/ and tests/unit/services/validation/ so both can dispatch
on `artifact_type` without duplicating the mapping.
"""

from __future__ import annotations

from domain.artifacts.content import ContentArtifact
from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.template import TemplateArtifact

FixtureArtifact = TemplateArtifact | ContentArtifact | DecoderMaskArtifact

_MODEL_BY_ARTIFACT_TYPE: dict[str, type[FixtureArtifact]] = {
    "template": TemplateArtifact,
    "content": ContentArtifact,
    "decoder_mask": DecoderMaskArtifact,
}

# The fixture bundle's non-document artifact files (specs/FIXTURES-SPEC.md):
# 2 templates, 3 masks, 3 content artifacts. `doc_*.json` files are document
# registrations, not one of E01's three artifact kinds — out of scope here.
ALL_FIXTURE_ARTIFACT_NAMES = (
    "tmpl_nvinv.v1",
    "tmpl_mbr.v1",
    "mask_nvvendor.v1",
    "mask_nvcust.v1",
    "mask_mbrvendor.v1",
    "content_nv20260042.v1",
    "content_nv20260043.v1",
    "content_mbr001.v1",
)


def parse_fixture_artifact(data: dict[str, object]) -> FixtureArtifact:
    artifact_type = data["artifact_type"]
    model_cls = _MODEL_BY_ARTIFACT_TYPE[str(artifact_type)]
    return model_cls.model_validate(data)
