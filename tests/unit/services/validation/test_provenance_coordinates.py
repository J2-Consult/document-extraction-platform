"""E06 validator extensions: coordinate-space resolution, page-range, and
transform-well-formedness checks (src/services/validation/checks/
coordinate_space_resolution.py, page_range.py, transform_well_formed.py).

Mirrors tests/unit/services/validation/test_invariants.py's idiom (E01, not
edited here): construct a bundle by mutating a *parsed, valid* fixture
artifact via `model_copy(update=...)`, which bypasses Pydantic field
validation the same way an in-process caller assembling a bundle from partial
data could, then assert the InvariantValidator rejects it with the itemized
path + code + message the epic requires.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.artifacts.content import ContentArtifact, Observation, UnmappedContent
from services.validation.bundle import ArtifactBundle
from services.validation.validator import default_validator

LoadFixtureArtifact = Callable[[str], dict[str, Any]]


def _load_content(fixture_name: str, load_fixture_artifact: LoadFixtureArtifact) -> ContentArtifact:
    return ContentArtifact.model_validate(load_fixture_artifact(fixture_name))


def _with_observation(content: ContentArtifact, index: int, **field_updates: object) -> ContentArtifact:
    observations = list(content.body.observations)
    observations[index] = observations[index].model_copy(update=field_updates)
    return content.model_copy(update={"body": content.body.model_copy(update={"observations": observations})})


def _with_unmapped_note(content: ContentArtifact, index: int, **field_updates: object) -> ContentArtifact:
    notes = list(content.body.unmapped_content)
    notes[index] = notes[index].model_copy(update=field_updates)
    return content.model_copy(update={"body": content.body.model_copy(update={"unmapped_content": notes})})


def _codes(content: ContentArtifact) -> set[str]:
    report = default_validator().validate(ArtifactBundle(content=content))
    return {violation.code for violation in report.violations}


def _violation(content: ContentArtifact, code: str) -> Any:
    report = default_validator().validate(ArtifactBundle(content=content))
    matches = [v for v in report.violations if v.code == code]
    assert matches, f"expected a violation with code {code!r}, got {[v.code for v in report.violations]}"
    return matches[0]


# --- fixture sweep: criterion 9 baseline at unit granularity ----------------


def test_all_three_content_fixtures_resolve_every_coordinate_space(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    for fixture_name in ("content_nv20260042.v1", "content_nv20260043.v1", "content_mbr001.v1"):
        content = _load_content(fixture_name, load_fixture_artifact)
        known_ids = {space.id for space in content.body.coordinate_spaces}

        for observation in content.body.observations:
            assert observation.provenance.working.coordinate_space in known_ids
        for note in content.body.unmapped_content:
            assert note.provenance.working.coordinate_space in known_ids

        report = default_validator().validate(ArtifactBundle(content=content))
        assert report.ok, f"{fixture_name}: unexpected violations {report.violations}"


# --- unknown-coordinate-space -------------------------------------------


def test_observation_citing_an_unknown_coordinate_space_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    observation = content.body.observations[0]
    mutated_provenance = observation.provenance.model_copy(
        update={"working": observation.provenance.working.model_copy(update={"coordinate_space": "page-99"})}
    )
    mutated = _with_observation(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "unknown-coordinate-space")
    assert violation.path == "/body/observations/0/provenance/working/coordinate_space"


def test_unmapped_content_citing_an_unknown_coordinate_space_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    note = content.body.unmapped_content[0]
    mutated_provenance = note.provenance.model_copy(
        update={"working": note.provenance.working.model_copy(update={"coordinate_space": "page-99"})}
    )
    mutated = _with_unmapped_note(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "unknown-coordinate-space")
    assert violation.path == "/body/unmapped_content/0/provenance/working/coordinate_space"


# --- page-out-of-range -----------------------------------------------------


def test_observation_provenance_page_past_the_document_page_count_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    assert content.body.source.page_count == 1
    observation = content.body.observations[0]
    mutated_provenance = observation.provenance.model_copy(
        update={"source": observation.provenance.source.model_copy(update={"page": 2})}
    )
    mutated = _with_observation(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "page-out-of-range")
    assert violation.path == "/body/observations/0/provenance/source/page"


def test_unmapped_content_provenance_page_below_one_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    note = content.body.unmapped_content[0]
    mutated_provenance = note.provenance.model_copy(
        update={"source": note.provenance.source.model_copy(update={"page": 0})}
    )
    mutated = _with_unmapped_note(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "page-out-of-range")
    assert violation.path == "/body/unmapped_content/0/provenance/source/page"


def test_mixed_page_document_accepts_provenance_on_either_recorded_page(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_mbr001.v1", load_fixture_artifact)
    assert content.body.source.page_count == 2
    pages_cited = {observation.provenance.source.page for observation in content.body.observations}
    assert pages_cited == {1, 2}
    assert "page-out-of-range" not in _codes(content)


# --- malformed-transform -----------------------------------------------


def test_observation_transform_to_source_with_wrong_length_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    observation = content.body.observations[0]
    mutated_provenance = observation.provenance.model_copy(update={"transform_to_source": [1.0, 0.0, 0.0, 1.0, 0.0]})
    mutated = _with_observation(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "malformed-transform")
    assert violation.path == "/body/observations/0/provenance/transform_to_source"


def test_observation_transform_to_source_with_a_non_finite_component_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    observation = content.body.observations[0]
    mutated_provenance = observation.provenance.model_copy(
        update={"transform_to_source": [1.0, 0.0, 0.0, 1.0, 0.0, float("nan")]}
    )
    mutated = _with_observation(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "malformed-transform")
    assert violation.path == "/body/observations/0/provenance/transform_to_source"


def test_unmapped_content_transform_to_source_with_infinite_component_is_rejected(
    load_fixture_artifact: LoadFixtureArtifact,
) -> None:
    content = _load_content("content_nv20260042.v1", load_fixture_artifact)
    note = content.body.unmapped_content[0]
    mutated_provenance = note.provenance.model_copy(
        update={"transform_to_source": [1.0, 0.0, 0.0, 1.0, 0.0, float("inf")]}
    )
    mutated = _with_unmapped_note(content, 0, provenance=mutated_provenance)

    violation = _violation(mutated, "malformed-transform")
    assert violation.path == "/body/unmapped_content/0/provenance/transform_to_source"


# --- checks silently pass with no content artifact under validation --------


def test_new_checks_are_silent_when_bundle_has_no_content() -> None:
    assert default_validator().validate(ArtifactBundle()).ok is True


# --- import-time sanity: Observation/UnmappedContent still typed as expected


def test_content_model_shapes_unchanged_by_this_epic() -> None:
    assert Observation.model_fields.keys() >= {"element_id", "value", "state", "confidence", "provenance"}
    assert UnmappedContent.model_fields.keys() >= {"note_id", "text", "provenance"}
