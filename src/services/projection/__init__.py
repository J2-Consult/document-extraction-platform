"""E07 projection service: derive relational projection rows from immutable artifacts.

`decode` turns artifact JSON into typed rows via the E01 models; `writer`
replaces whole scopes through a `ProjectionSink` so re-runs always converge.
"""

from services.projection.decode import decode_document_values, decode_mask_entries
from services.projection.rows import (
    DocumentValuesScope,
    ExtractedValueRow,
    MaskEntriesScope,
    MaskEntryRow,
)
from services.projection.writer import ProjectionSink, ProjectionWriter

__all__ = [
    "DocumentValuesScope",
    "ExtractedValueRow",
    "MaskEntriesScope",
    "MaskEntryRow",
    "ProjectionSink",
    "ProjectionWriter",
    "decode_document_values",
    "decode_mask_entries",
]
