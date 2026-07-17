"""Provider wrappers and cost accounting (epic E05).

`guarded.GuardedProvider` is the ONLY sanctioned path to an external model:
timeout, circuit breaker, rate limit, per-tenant cost cap, response schema
validation, component-version stamping. `cost_ledger.InMemoryCostLedger` is
the in-process `CostLedger` implementation.
"""
