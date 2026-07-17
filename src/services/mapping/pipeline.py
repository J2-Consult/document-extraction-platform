"""MappingPipeline (E09): ResolveRefs -> ApplyMask -> CoerceNormalize ->
BindTargetSchema -> DecideOutcome.

Stateless composition of single-purpose steps, all constructor-injected. The
pipeline holds no clock, no randomness, and imports zero adapter modules
(proven by tests/unit/services/mapping/test_architecture_no_adapter_imports.py)
— the same `MappingRequest` twice yields byte-identical `MappingResult` JSON.

Failure surface: a template-version disagreement is a workflow state
(`pending_template_review`), not an error; a missing/unknown target schema is
a `technical` failure (nothing wrong with the document). Anything else raises
to the caller — this module never swallows an unexpected exception into a
result (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.artifacts.content import ContentBody
from domain.artifacts.mask import DecoderMaskBody
from domain.artifacts.template import TemplateBody
from domain.registry import TargetSchemaRegistry, UnknownTargetSchemaError
from services.mapping.constants import DEFAULT_CONFIDENCE_THRESHOLD, MAPPING_PIPELINE_VERSION
from services.mapping.outcome import MappingResult
from services.mapping.steps.apply_mask import ApplyMask
from services.mapping.steps.bind_target_schema import BindTargetSchema
from services.mapping.steps.coerce_normalize import CoerceNormalize
from services.mapping.steps.decide_outcome import DecideOutcome
from services.mapping.steps.resolve_refs import ResolveRefs, TemplateMismatchError


@dataclass(frozen=True, slots=True)
class MappingRequest:
    """Everything one mapping run reads — artifacts pinned by the caller."""

    content: ContentBody
    mask: DecoderMaskBody
    template: TemplateBody
    target_schema_version: int


class MappingPipeline:
    def __init__(
        self,
        resolve_refs: ResolveRefs,
        apply_mask: ApplyMask,
        coerce_normalize: CoerceNormalize,
        bind_target_schema: BindTargetSchema,
        decide_outcome: DecideOutcome,
        *,
        component_versions: dict[str, str],
    ) -> None:
        self._resolve_refs = resolve_refs
        self._apply_mask = apply_mask
        self._coerce_normalize = coerce_normalize
        self._bind_target_schema = bind_target_schema
        self._decide_outcome = decide_outcome
        self._component_versions = dict(component_versions)

    def run(self, request: MappingRequest) -> MappingResult:
        try:
            refs = self._resolve_refs.resolve(request.content, request.mask, request.template)
        except TemplateMismatchError:
            return self._pending_template_review()
        application = self._apply_mask.apply(refs)
        coercion = self._coerce_normalize.coerce(application, request.template)
        try:
            bound = self._bind_target_schema.bind(
                coercion, _single_target_schema(request.mask), request.target_schema_version
            )
        except UnknownTargetSchemaError:
            return self._technical_failure()
        return self._decide_outcome.decide(application, coercion, bound)

    def _pending_template_review(self) -> MappingResult:
        return MappingResult(
            outcome="pending_template_review",
            record=None,
            contract_validation="not_evaluated",
            error_category=None,
            component_versions=self._component_versions,
        )

    def _technical_failure(self) -> MappingResult:
        return MappingResult(
            outcome="failed",
            record=None,
            contract_validation="not_evaluated",
            error_category="technical",
            component_versions=self._component_versions,
        )


def _single_target_schema(mask: DecoderMaskBody) -> str:
    """Every entry of one mask binds into ONE target schema; anything else is
    a mis-built mask and must fail loudly, not map partially."""
    schema_ids = {entry.target.target_schema for entry in mask.entries}
    if len(schema_ids) != 1:
        raise ValueError(f"mask '{mask.mask_id}' v{mask.version} binds {len(schema_ids)} target schemas, expected 1")
    return next(iter(schema_ids))


def build_default_pipeline(
    *,
    registry: TargetSchemaRegistry,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> MappingPipeline:
    """Composition root mirroring `default_validator()` / `default_registry()`."""
    component_versions = {"mapping_pipeline": MAPPING_PIPELINE_VERSION}
    return MappingPipeline(
        resolve_refs=ResolveRefs(),
        apply_mask=ApplyMask(),
        coerce_normalize=CoerceNormalize(),
        bind_target_schema=BindTargetSchema(registry),
        decide_outcome=DecideOutcome(confidence_threshold, component_versions),
        component_versions=component_versions,
    )
