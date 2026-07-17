"""Context orchestrator (epic E10): the LLM trust boundary.

Allow-listed retrieval dispatch (`dispatcher`), token-budgeted context
assembly with refuse-and-refine (`context`), delimited data-block prompt
assembly (`prompt`), and generic-client/itemized-server errors with id-only
operation logging (`errors`). No DB driver, no adapter imports — the world
is visible only through `ports.retrieval` (enforced by an architecture test).
"""
