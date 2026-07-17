"""Test-only fixture loading for the E08 lifecycle suite (not a test module).

Loads the golden pair from fixtures/artifacts/ — mask_nvvendor (vendor
baseline) and mask_nvcust (materialized effective customer mask) — plus the
template they reference, as typed E01 models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.artifacts.mask import DecoderMaskArtifact
from domain.artifacts.template import Anchor, TemplateArtifact, TemplateBody, TemplateElement

REPO_ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = REPO_ROOT / "fixtures" / "artifacts"


def load_artifact_json(name: str) -> dict[str, Any]:
    """fixtures/artifacts/<name>.json as a plain wire-form dict."""
    return dict(json.loads((ARTIFACTS_DIR / f"{name}.json").read_text(encoding="utf-8")))


def load_template(name: str) -> TemplateArtifact:
    return TemplateArtifact.model_validate(load_artifact_json(name))


def load_mask(name: str) -> DecoderMaskArtifact:
    return DecoderMaskArtifact.model_validate(load_artifact_json(name))


def build_tmpl_nvinv_v2() -> TemplateBody:
    """tmpl_nvinv v2 — the criterion-5 evolution of the fixture template.

    Relative to v1: `el_payment_terms` is MOVED (same anchor label text, new
    bbox), `el_total_amount` is SPLIT into `el_total_excl_vat` +
    `el_total_incl_vat` (two new labels sharing the old bbox row), and
    `el_reference` is ADDED. Every other element is unchanged.
    """
    v1 = load_template("tmpl_nvinv.v1").body
    elements: list[TemplateElement] = []
    for element in v1.elements:
        if element.element_id == "el_payment_terms":
            elements.append(element.model_copy(update={"bbox": [206.0, 516.0, 346.0, 528.0]}))
        elif element.element_id == "el_total_amount":
            elements.append(
                TemplateElement(
                    element_id="el_total_excl_vat",
                    kind="value_region",
                    page=1,
                    bbox=[206.0, 612.0, 274.0, 624.0],
                    anchor=Anchor(label_text="Total excl. VAT:", label_bbox=[56.0, 612.0, 196.0, 624.0]),
                )
            )
            elements.append(
                TemplateElement(
                    element_id="el_total_incl_vat",
                    kind="value_region",
                    page=1,
                    bbox=[278.0, 612.0, 346.0, 624.0],
                    anchor=Anchor(label_text="Total incl. VAT:", label_bbox=[56.0, 600.0, 196.0, 612.0]),
                )
            )
        else:
            elements.append(element)
    elements.append(
        TemplateElement(
            element_id="el_reference",
            kind="value_region",
            page=1,
            bbox=[206.0, 300.0, 346.0, 312.0],
            anchor=Anchor(label_text="Reference:", label_bbox=[56.0, 300.0, 196.0, 312.0]),
        )
    )
    return v1.model_copy(update={"version": 2, "elements": elements})
