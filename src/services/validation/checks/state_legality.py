"""`state == "present" <=> value is not null` (FIXTURES-SPEC.md, content body).

`Observation.value`/`.state` are independently-typed fields (see content.py)
so this cross-field rule cannot be expressed by either field's own type — it
is exactly the kind of invariant JSON Schema's `if/then` can encode but a
model_validator would over-eagerly enforce (see content.py's docstring on why
this rule intentionally isn't a Pydantic validator).
"""

from __future__ import annotations

from domain.artifacts.errors import InvariantViolation
from services.validation.bundle import ArtifactBundle

CODE = "state-value-conflict"


class StateLegalityCheck:
    def check(self, bundle: ArtifactBundle) -> list[InvariantViolation]:
        if bundle.content is None:
            return []
        violations: list[InvariantViolation] = []
        for index, observation in enumerate(bundle.content.body.observations):
            is_present = observation.state == "present"
            has_value = observation.value is not None
            if is_present != has_value:
                violations.append(
                    InvariantViolation(
                        path=f"/body/observations/{index}/value",
                        code=CODE,
                        message=f"state '{observation.state}' is inconsistent with value presence",
                    )
                )
        return violations
