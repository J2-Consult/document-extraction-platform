"""Concrete extraction passes (epic E05).

`native_text` is REAL (pypdf). The preprocessor/layout/OCR/detector modules
are deterministic stand-ins with real interfaces and real coordinate-space +
provenance bookkeeping — the heavy engines (raster preprocessing, OCR, layout
ML) run provider-side in production; each stub's docstring says exactly what
is stubbed. `vlm_regional` is the real provider wiring.
"""
