"""`RoutingDecision` re-export.

DEVIATION from the architect draft's module layout (flagged): the type
itself is defined in `ports/routing_store.py`, not here. `RoutingDecisionStore
.append(decision)` needs the concrete shape in its own signature, and ports
may not import from services (hexagonal dependency direction runs
services -> ports, never the reverse) — so the model has to live on the
ports side. This module exists so callers can still
`from services.routing.decisions import RoutingDecision` per the architect's
listed layout.
"""

from __future__ import annotations

from ports.routing_store import RoutedTo, RoutingDecision

__all__ = ["RoutedTo", "RoutingDecision"]
