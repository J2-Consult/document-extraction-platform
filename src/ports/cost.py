"""Cost-accounting port (epic E05): per-tenant, per-category spend.

Categories separate regional model use from full analysis and OCR so
criteria 1/3 reports can prove the fast path is cheaper. A cap breach is
raised as `CostCapExceeded` carrying the full itemization — a job that dies
on cost dies LOUDLY with the numbers attached, never silently.

Design-deviation flag: the architect's sketch names `record(...)` and
`spent(tenant_id)`; `spent_in_category(...)` is an ADDITION so reports can
separate categories without a second port. Flagged in the PR description.

Pure interface: no I/O here, no framework imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Protocol, runtime_checkable

CostCategory = Literal["regional_model", "full_analysis", "ocr"]

# Runtime mirror of `CostCategory` for guard clauses and report iteration.
COST_CATEGORIES: tuple[CostCategory, ...] = ("regional_model", "full_analysis", "ocr")


@runtime_checkable
class CostLedger(Protocol):
    def record(self, tenant_id: str, category: CostCategory, cost: float) -> None:
        """Record one non-negative cost against a tenant and category."""
        ...

    def spent(self, tenant_id: str) -> float:
        """Total spend for a tenant across all categories."""
        ...

    def spent_in_category(self, tenant_id: str, category: CostCategory) -> float:
        """Spend for a tenant in one category (0.0 when nothing recorded)."""
        ...


class CostCapExceeded(RuntimeError):  # noqa: N818 — name is BINDING per specs/design/E05-interfaces.md
    """A per-tenant cost cap refused a call. Always itemized: the exception
    carries tenant, cap, total spend, per-category spend, and the category
    of the refused call, so the resulting job failure can surface all of it."""

    def __init__(
        self,
        *,
        tenant_id: str,
        cap: float,
        spent_total: float,
        spent_by_category: Mapping[CostCategory, float],
        attempted_category: CostCategory,
    ) -> None:
        self.tenant_id = tenant_id
        self.cap = cap
        self.spent_total = spent_total
        self.spent_by_category = dict(spent_by_category)
        self.attempted_category = attempted_category
        super().__init__(
            f"per-tenant cost cap exceeded: spent {spent_total} of cap {cap} (refused category: {attempted_category})"
        )

    def itemized(self) -> dict[str, object]:
        """Machine-readable failure items for the job record."""
        return {
            "tenant_id": self.tenant_id,
            "cap": self.cap,
            "spent_total": self.spent_total,
            "spent_by_category": dict(self.spent_by_category),
            "attempted_category": self.attempted_category,
        }
