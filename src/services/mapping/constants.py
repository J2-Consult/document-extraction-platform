"""Default confidence thresholds for the mapping pipeline (E09).

The ONE place mapping defaults live — thresholds are always explicit
constructor parameters on the pipeline (no magic numbers inside steps);
these constants are only what a composition root passes when it has no
better-calibrated value.

Rationale: extraction's own gate (services/extraction/confidence.py) routes
a region to `review` below its review threshold, and the fixture corpus's
canonical "smudged total" is calibrated 0.61 — a value the recognizer read
but cannot be trusted into a record. 0.75 keeps a healthy margin above that
while sitting below the corpus's clean-value calibration (0.9+), so
fixture-derived tests exercise both sides of the boundary without contrived
numbers.
"""

from __future__ import annotations

# Calibrated confidence at or above which an observation may enter a record.
DEFAULT_CONFIDENCE_THRESHOLD = 0.75

# Stamped into every MappingResult.component_versions — bump on any change to
# the pipeline's observable mapping behavior.
MAPPING_PIPELINE_VERSION = "e09-1.0.0"
