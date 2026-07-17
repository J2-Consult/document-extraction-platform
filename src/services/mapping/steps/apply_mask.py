"""Step 2 — ApplyMask: semantic decoding through the ONE selected mask.

Applies each entry's `enum_map` to the observed text ("Yes" -> true) and
sorts observations into decoded values and the absence buckets DecideOutcome
reasons over. Contextual meaning enters HERE and only here — from the mask,
never from template or content.
"""

from __future__ import annotations

from services.mapping.steps.shapes import (
    ContractIssue,
    DecodedValue,
    MaskApplication,
    ResolvedEntry,
    ResolvedRefs,
)

ENUM_MAP_MISS_CODE = "enum-map-miss"


class ApplyMask:
    def apply(self, refs: ResolvedRefs) -> MaskApplication:
        decoded: list[DecodedValue] = []
        unreadable: list[ResolvedEntry] = []
        blank: list[ResolvedEntry] = []
        issues: list[ContractIssue] = []
        for resolved in refs.entries:
            observation = resolved.observation
            if observation is None or observation.state in ("empty", "not_applicable", "not_found"):
                blank.append(resolved)
                continue
            if observation.state == "unreadable":
                unreadable.append(resolved)
                continue
            self._decode(resolved, decoded, issues)
        return MaskApplication(
            decoded=tuple(decoded), unreadable=tuple(unreadable), blank=tuple(blank), issues=tuple(issues)
        )

    def _decode(self, resolved: ResolvedEntry, decoded: list[DecodedValue], issues: list[ContractIssue]) -> None:
        entry, observation = resolved.entry, resolved.observation
        assert observation is not None and observation.value is not None  # state == "present"
        if entry.enum_map is None:
            decoded.append(DecodedValue(entry=entry, observation=observation, value=observation.value))
            return
        mapped = entry.enum_map.get(observation.value)
        if mapped is None:
            issues.append(
                ContractIssue(
                    element_id=entry.element_id,
                    field=entry.target.field,
                    code=ENUM_MAP_MISS_CODE,
                    message=f"observed text for element '{entry.element_id}' has no enum_map mapping",
                )
            )
            return
        decoded.append(DecodedValue(entry=entry, observation=observation, value=mapped))
