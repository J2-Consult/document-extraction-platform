"""Template artifact: extraction-oriented document structure. No business meaning.

A template describes WHERE things are on a page (elements, bboxes, anchors) and
what geometric fingerprint identifies that layout. What an element MEANS to a
tenant/system belongs in a decoder-mask (`mask.py`), never here.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.artifacts.envelope import ArtifactEnvelope

# Generalized beyond the fixtures' current "fpv1" so a future fingerprint
# version (fpv2, ...) doesn't require a model change — only the InvariantValidator's
# fingerprint_format check enforces this pattern; see checks/fingerprint_format.py
# for why it is not also a Field(pattern=...) constraint here.
FINGERPRINT_PATTERN = r"^fpv\d+:sha256:[0-9a-f]{64}$"

ElementKind = Literal["label", "value_region", "table", "checkbox", "section_heading"]


class TemplateRef(BaseModel):
    """Pointer to a specific version of a template, used by content and mask bodies."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    template_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class Anchor(BaseModel):
    """The label a value element is positioned relative to."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    label_text: str = Field(min_length=1)
    label_bbox: list[float] = Field(min_length=4, max_length=4)


class TableColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1)
    datatype: str = Field(min_length=1)


class TemplateElement(BaseModel):
    """One addressable region on a page: a label, value, table, checkbox, or heading."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element_id: str = Field(min_length=1)
    kind: ElementKind
    page: int = Field(ge=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    anchor: Anchor | None = None
    columns: list[TableColumn] | None = Field(default=None, min_length=1)
    optional: bool | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _table_kind_requires_columns(self) -> TemplateElement:
        if self.kind == "table" and not self.columns:
            raise ValueError("table elements require a non-empty columns list")
        return self


class PageGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    page: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pt"]
    rotation: Literal[0, 90, 180, 270]


class TemplateBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    template_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    doc_class: str = Field(min_length=1)
    # Deliberately unconstrained by Field(pattern=...): a malformed fingerprint
    # must still parse so InvariantValidator's fingerprint_format check has
    # something to reject with an itemized, machine-readable violation instead
    # of a Pydantic parse error. See checks/fingerprint_format.py.
    fingerprint: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    pages: list[PageGeometry] = Field(min_length=1)
    elements: list[TemplateElement] = Field(min_length=1)


class TemplateArtifact(ArtifactEnvelope[TemplateBody]):
    """`template.json`: envelope + `TemplateBody`."""

    artifact_type: Literal["template"] = "template"
