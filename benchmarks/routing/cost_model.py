"""Illustrative provider-call cost model for the routing benchmark's "net
cost vs full analysis" metric.

Cost UNITS here are placeholders, not real provider pricing — E05 owns real
cost accounting once the extraction cascade exists. This module exists only
so `harness.py` can report a directional saving (fast path vs. full
analysis) without depending on E05's not-yet-built cascade.
"""

from __future__ import annotations

from dataclasses import dataclass

from ports.routing_store import RoutingDecision


@dataclass(frozen=True)
class CostModel:
    full_layout_call_cost: float = 1.0
    whole_document_vlm_call_cost: float = 1.0
    regional_call_cost: float = 0.1
    regional_calls_per_fast_path_document: int = 3

    @property
    def full_analysis_cost(self) -> float:
        return self.full_layout_call_cost + self.whole_document_vlm_call_cost


def cost_for_decision(decision: RoutingDecision, cost_model: CostModel) -> float:
    if decision.routed_to == "fast_path":
        return cost_model.regional_call_cost * cost_model.regional_calls_per_fast_path_document
    return cost_model.full_analysis_cost
