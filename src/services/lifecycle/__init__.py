"""Lifecycle application services (epic E08): template lineage consumption,
draft-mask migration, release-unit activation, effective-mask
materialization (ADR 20), consultant worklist, and the held first-document
policy.

Constructor injection only; every persistent effect goes through the
`ports.lifecycle.LifecycleRepository` port as an append with actor identity.
"""

from __future__ import annotations
