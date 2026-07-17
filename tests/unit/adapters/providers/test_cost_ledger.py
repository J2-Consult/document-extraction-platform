"""InMemoryCostLedger: per-tenant, per-category accounting — regional model
use mechanically separable from full analysis and OCR (criteria 1/3 feed).
"""

from __future__ import annotations

import pytest

from adapters.providers.cost_ledger import InMemoryCostLedger


def test_spend_is_recorded_per_tenant_and_per_category() -> None:
    ledger = InMemoryCostLedger()

    ledger.record("t-nordvik", "regional_model", 0.02)
    ledger.record("t-nordvik", "regional_model", 0.03)
    ledger.record("t-nordvik", "full_analysis", 0.50)
    ledger.record("t-nordvik", "ocr", 0.10)
    ledger.record("t-other", "regional_model", 0.99)

    assert ledger.spent_in_category("t-nordvik", "regional_model") == pytest.approx(0.05)
    assert ledger.spent_in_category("t-nordvik", "full_analysis") == pytest.approx(0.50)
    assert ledger.spent_in_category("t-nordvik", "ocr") == pytest.approx(0.10)
    assert ledger.spent("t-nordvik") == pytest.approx(0.65)
    assert ledger.spent("t-other") == pytest.approx(0.99)


def test_unknown_tenant_and_empty_category_read_as_zero_spend() -> None:
    ledger = InMemoryCostLedger()

    assert ledger.spent("t-nobody") == 0.0
    assert ledger.spent_in_category("t-nobody", "ocr") == 0.0


def test_negative_cost_is_rejected() -> None:
    ledger = InMemoryCostLedger()

    with pytest.raises(ValueError, match="negative"):
        ledger.record("t-nordvik", "ocr", -0.01)


def test_unknown_category_is_rejected_at_runtime() -> None:
    ledger = InMemoryCostLedger()

    with pytest.raises(ValueError, match="category"):
        ledger.record("t-nordvik", "bribes", 1.0)  # type: ignore[arg-type]
