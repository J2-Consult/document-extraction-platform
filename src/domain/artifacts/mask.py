"""Decoder-mask artifact: contextual meaning per tenant/system.

This is the ONLY place business/contextual meaning is allowed to live —
`semantic_role`, `target`, and `enum_map` map a structural template element to
a field in a versioned target schema for one system context. Attribution
tracks whether an entry originated at the vendor baseline or was overridden by
a customer, and (for customer masks) what it was inherited from.

Pure domain: no I/O, no framework imports.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from domain.artifacts.envelope import ArtifactEnvelope
from domain.artifacts.template import TemplateRef

MaskScope = Literal["vendor", "customer"]
TargetDatatype = Literal["string", "number", "boolean", "date", "array"]


class TargetBinding(BaseModel):
    """`target_schema` maps to the fixtures' JSON key "schema" via alias:
    `BaseModel` itself defines a (deprecated, v1-legacy) `schema` attribute,
    so a field literally named `schema` would both shadow it and fail mypy
    strict (`Incompatible types in assignment`) even though Pydantic allows
    it at runtime. `populate_by_name=True` also accepts the Python-friendly
    name for in-process construction (e.g. by a later epic's mask builder).
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, populate_by_name=True)

    target_schema: str = Field(min_length=1, alias="schema")
    field: str = Field(min_length=1)
    datatype: TargetDatatype


class MaskRef(BaseModel):
    """Pointer to a specific version of a mask, used by `EntryAttribution.inherited_from`."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    mask_id: str = Field(min_length=1)
    version: int = Field(ge=1)


class EntryAttribution(BaseModel):
    """Who authored a mask entry, and what (if anything) it overrides.

    Cross-field legality (`overridden` implies `inherited_from` is set; every
    vendor-scope entry has `validated_by`) is enforced by
    checks/mask_attribution.py, not here — see that module's docstring.
    """

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    origin: Literal["vendor", "customer"]
    inherited_from: MaskRef | None
    overridden: bool
    validated_by: str | None = None


class MaskEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    element_id: str = Field(min_length=1)
    semantic_role: str = Field(min_length=1)
    target: TargetBinding
    enum_map: dict[str, str | bool] | None = None
    section_path: str | None = None
    attribution: EntryAttribution


class DecoderMaskBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    mask_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    scope: MaskScope
    # Cross-field rule `scope == "vendor" <=> tenant_id is None` is enforced by
    # checks/mask_scope.py, not here.
    tenant_id: str | None
    template_ref: TemplateRef
    system_context: str = Field(min_length=1)
    entries: list[MaskEntry] = Field(min_length=1)


class DecoderMaskArtifact(ArtifactEnvelope[DecoderMaskBody]):
    """`decoder-mask.json`: envelope + `DecoderMaskBody`."""

    artifact_type: Literal["decoder_mask"] = "decoder_mask"
