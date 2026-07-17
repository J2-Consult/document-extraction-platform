"""ReleaseService: release units (template + required compatible masks)
activate atomically through the LifecycleRepository port; an old mask NEVER
implicitly applies to an incompatible template version (rejected, not
guessed); every lifecycle mutation is an append carrying actor identity;
vendor-mask publication requires the admin scope (authorization at the
service boundary); pinned v1 artifacts stay reproducible after activation.
"""

from __future__ import annotations

import pytest

from domain.artifacts.mask import DecoderMaskArtifact, MaskRef
from domain.artifacts.template import TemplateArtifact, TemplateRef
from domain.lineage.generator import LineageGenerator
from ports.lifecycle import (
    ChangeRecord,
    DuplicateVersionError,
    LifecycleRepository,
    ReleaseUnit,
    UnknownReleaseRefError,
)
from services.lifecycle.errors import (
    AdminScopeRequiredError,
    DraftValidationError,
    IncompatibleReleaseError,
    UnknownArtifactError,
)
from services.lifecycle.migration import MaskMigrator
from services.lifecycle.release import ADMIN_SCOPE, Principal, ReleaseService
from services.validation.validator import default_validator
from tests.unit.fakes.clock import FakeClock
from tests.unit.services.lifecycle._fixtures import build_tmpl_nvinv_v2, load_mask, load_template
from tests.unit.services.lifecycle.fakes import InMemoryLifecycleRepository

ADMIN = Principal(actor="vendor-consultant-1", scopes=frozenset({ADMIN_SCOPE}))
NON_ADMIN = Principal(actor="customer-analyst-1", scopes=frozenset({"mask:write"}))

TEMPLATE_V1_REF = TemplateRef(template_id="tmpl_nvinv", version=1)
TEMPLATE_V2_REF = TemplateRef(template_id="tmpl_nvinv", version=2)
MASK_V1_REF = MaskRef(mask_id="mask_nvvendor", version=1)
MASK_V2_REF = MaskRef(mask_id="mask_nvvendor", version=2)


def build_service() -> tuple[ReleaseService, InMemoryLifecycleRepository]:
    repository = InMemoryLifecycleRepository()
    service = ReleaseService(repository, default_validator(), FakeClock(start=1000.0))
    return service, repository


def template_v2_artifact() -> TemplateArtifact:
    v1 = load_template("tmpl_nvinv.v1")
    return v1.model_copy(update={"version": 2, "body": build_tmpl_nvinv_v2()})


def draft_mask_v2_artifact() -> DecoderMaskArtifact:
    lineage = LineageGenerator().compare(load_template("tmpl_nvinv.v1").body, build_tmpl_nvinv_v2())
    draft = MaskMigrator(default_validator()).draft(load_mask("mask_nvvendor.v1").body, lineage).draft_mask_body
    return load_mask("mask_nvvendor.v1").model_copy(update={"version": 2, "body": draft})


def publish_v1(service: ReleaseService) -> None:
    service.publish_template_version(load_template("tmpl_nvinv.v1"), ADMIN, reason="initial registration")
    service.publish_mask_version(load_mask("mask_nvvendor.v1"), ADMIN, reason="initial vendor baseline")


def test_fake_repository_satisfies_the_port_protocol() -> None:
    assert isinstance(InMemoryLifecycleRepository(), LifecycleRepository)


def test_release_unit_activates_template_and_mask_together() -> None:
    service, repository = build_service()
    publish_v1(service)
    service.publish_template_version(template_v2_artifact(), ADMIN, reason="v2 layout")
    service.publish_mask_version(draft_mask_v2_artifact(), ADMIN, reason="migrated draft")

    service.activate(ReleaseUnit(template_ref=TEMPLATE_V2_REF, mask_refs=(MASK_V2_REF,)), ADMIN, reason="release v2")

    active = repository.get_active_mask("tmpl_nvinv", "erp_invoice", tenant_id=None)
    assert active is not None
    assert active.version == 2
    assert active.body.template_ref == TEMPLATE_V2_REF


def test_every_lifecycle_mutation_is_an_append_with_actor_identity() -> None:
    service, repository = build_service()
    publish_v1(service)

    template_change = repository.template_change("tmpl_nvinv", 1)
    mask_change = repository.mask_change("mask_nvvendor", 1)
    assert template_change.actor == ADMIN.actor
    assert template_change.reason == "initial registration"
    assert template_change.at == 1000.0
    assert mask_change.actor == ADMIN.actor

    with pytest.raises(DuplicateVersionError):  # append-only: no overwrite path exists
        service.publish_mask_version(load_mask("mask_nvvendor.v1"), ADMIN, reason="again")


def test_activation_records_actor_identity() -> None:
    service, repository = build_service()
    publish_v1(service)

    service.activate(
        ReleaseUnit(template_ref=TEMPLATE_V1_REF, mask_refs=(MASK_V1_REF,)), ADMIN, reason="initial release"
    )

    assert len(repository.activations) == 1
    _, change = repository.activations[0]
    assert change.actor == ADMIN.actor
    assert change.reason == "initial release"


def test_vendor_mask_publication_requires_admin_scope() -> None:
    service, repository = build_service()
    service.publish_template_version(load_template("tmpl_nvinv.v1"), ADMIN, reason="initial registration")

    with pytest.raises(AdminScopeRequiredError):
        service.publish_mask_version(load_mask("mask_nvvendor.v1"), NON_ADMIN, reason="not allowed")

    assert repository.get_mask(MASK_V1_REF) is None, "a refused publication must append nothing"


def test_customer_mask_publication_does_not_require_admin_scope() -> None:
    service, repository = build_service()
    service.publish_template_version(load_template("tmpl_nvinv.v1"), ADMIN, reason="initial registration")

    service.publish_mask_version(load_mask("mask_nvcust.v1"), NON_ADMIN, reason="customer mask")

    assert repository.get_mask(MaskRef(mask_id="mask_nvcust", version=1)) is not None


def test_old_mask_never_implicitly_applies_to_an_incompatible_template_version() -> None:
    service, repository = build_service()
    publish_v1(service)
    service.publish_template_version(template_v2_artifact(), ADMIN, reason="v2 layout")

    with pytest.raises(IncompatibleReleaseError):  # v1 mask against v2 template: rejected, never guessed
        service.activate(
            ReleaseUnit(template_ref=TEMPLATE_V2_REF, mask_refs=(MASK_V1_REF,)), ADMIN, reason="bad release"
        )

    assert repository.get_active_mask("tmpl_nvinv", "erp_invoice", tenant_id=None) is None
    assert repository.activations == []


def test_activation_with_unknown_refs_is_rejected_before_any_state_change() -> None:
    service, repository = build_service()
    publish_v1(service)

    with pytest.raises(UnknownArtifactError):
        service.activate(
            ReleaseUnit(template_ref=TEMPLATE_V1_REF, mask_refs=(MaskRef(mask_id="mask_missing", version=1),)),
            ADMIN,
            reason="unknown mask",
        )

    assert repository.get_active_mask("tmpl_nvinv", "erp_invoice", tenant_id=None) is None


def test_repository_activation_is_atomic_when_one_ref_of_many_is_unknown() -> None:
    _, repository = build_service()
    repository.append_template_version(load_template("tmpl_nvinv.v1"), ChangeRecord(actor="a", reason="seed", at=0.0))
    repository.append_mask_version(load_mask("mask_nvvendor.v1"), ChangeRecord(actor="a", reason="seed", at=0.0))
    unit = ReleaseUnit(
        template_ref=TEMPLATE_V1_REF,
        mask_refs=(MASK_V1_REF, MaskRef(mask_id="mask_missing", version=1)),
    )

    with pytest.raises(UnknownReleaseRefError):
        repository.activate_release_unit(unit, ChangeRecord(actor="a", reason="partial", at=0.0))

    assert repository.get_active_mask("tmpl_nvinv", "erp_invoice", tenant_id=None) is None, (
        "a failed activation must leave NO mask activated (all-or-nothing)"
    )


def test_draft_failing_referential_validation_cannot_activate() -> None:
    service, _ = build_service()
    publish_v1(service)
    service.publish_template_version(template_v2_artifact(), ADMIN, reason="v2 layout")
    draft = draft_mask_v2_artifact()
    entries = list(draft.body.entries)
    entries[0] = entries[0].model_copy(update={"element_id": "el_ghost"})
    broken = draft.model_copy(update={"body": draft.body.model_copy(update={"entries": entries})})
    service.publish_mask_version(broken, ADMIN, reason="broken draft")

    with pytest.raises(DraftValidationError) as excinfo:
        service.activate(ReleaseUnit(template_ref=TEMPLATE_V2_REF, mask_refs=(MASK_V2_REF,)), ADMIN, reason="release")

    assert "unknown-element-id" in {violation.code for violation in excinfo.value.report.violations}


def test_v1_documents_remain_reproducible_against_pinned_versions_after_v2_activation() -> None:
    service, repository = build_service()
    publish_v1(service)
    service.activate(ReleaseUnit(template_ref=TEMPLATE_V1_REF, mask_refs=(MASK_V1_REF,)), ADMIN, reason="release v1")
    pinned_template = repository.get_template(TEMPLATE_V1_REF)
    pinned_mask = repository.get_mask(MASK_V1_REF)
    assert pinned_template is not None and pinned_mask is not None
    template_snapshot = pinned_template.model_dump(by_alias=True)
    mask_snapshot = pinned_mask.model_dump(by_alias=True)

    service.publish_template_version(template_v2_artifact(), ADMIN, reason="v2 layout")
    service.publish_mask_version(draft_mask_v2_artifact(), ADMIN, reason="migrated draft")
    service.activate(ReleaseUnit(template_ref=TEMPLATE_V2_REF, mask_refs=(MASK_V2_REF,)), ADMIN, reason="release v2")

    template_after = repository.get_template(TEMPLATE_V1_REF)
    mask_after = repository.get_mask(MASK_V1_REF)
    assert template_after is not None and mask_after is not None
    assert template_after.model_dump(by_alias=True) == template_snapshot
    assert mask_after.model_dump(by_alias=True) == mask_snapshot
    assert repository.list_template_versions("tmpl_nvinv") == (1, 2)
    assert repository.list_mask_versions("mask_nvvendor") == (1, 2)


def test_activating_a_release_unit_for_an_unknown_template_is_rejected() -> None:
    service, _ = build_service()

    with pytest.raises(UnknownArtifactError):
        service.activate(
            ReleaseUnit(template_ref=TEMPLATE_V1_REF, mask_refs=(MASK_V1_REF,)), ADMIN, reason="nothing exists"
        )
