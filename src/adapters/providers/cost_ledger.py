"""`CostLedger` adapter: in-memory per-tenant, per-category accounting.

Keeps regional model use, full analysis, and OCR spend mechanically separate
so criteria 1/3 reports can compare fast-path vs full-analysis cost. Guards
its inputs at runtime (category vocabulary, non-negative cost) because
callers include provider-response-derived numbers — untrusted until checked.

A durable (Postgres) implementation is a later epic's adapter behind the
same port; nothing here is process-shared.
"""

from __future__ import annotations

from collections import defaultdict

from ports.cost import COST_CATEGORIES, CostCategory


class InMemoryCostLedger:
    def __init__(self) -> None:
        self._spend: dict[str, dict[CostCategory, float]] = defaultdict(lambda: defaultdict(float))

    def record(self, tenant_id: str, category: CostCategory, cost: float) -> None:
        if not tenant_id:
            raise ValueError("tenant_id must be non-empty")
        if category not in COST_CATEGORIES:
            raise ValueError(f"unknown cost category: {category!r}")
        if cost < 0:
            raise ValueError("cost must not be negative")
        self._spend[tenant_id][category] += cost

    def spent(self, tenant_id: str) -> float:
        return sum(self._spend.get(tenant_id, {}).values())

    def spent_in_category(self, tenant_id: str, category: CostCategory) -> float:
        return self._spend.get(tenant_id, {}).get(category, 0.0)

    def spent_by_category(self, tenant_id: str) -> dict[CostCategory, float]:
        """Non-zero categories only — the itemization a cost-cap failure carries."""
        return {category: cost for category, cost in self._spend.get(tenant_id, {}).items() if cost > 0}
