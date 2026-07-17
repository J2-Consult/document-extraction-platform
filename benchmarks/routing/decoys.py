"""Decoy generator: PDFs with IDENTICAL page geometry to the Nordvik invoice
fixtures but MOVED LABELS, for E04's candidate-routing benchmark corpus.

Reuses `fixtures/pdfs/generate_pdfs.py`'s constants and low-level PDF
assembly functions programmatically — never edits `fixtures/`.

The trick: fpv1 excludes text CONTENT from the fingerprint, but NOT text
LENGTH — a line's bbox width is `len(text) * font_size * CHAR_WIDTH_FACTOR`
(`fixtures/fpv1.py`'s documented nominal-width heuristic), so swapping in a
label of a *different* length at the same position would itself change the
quantized bbox and break the candidate hit we're trying to prove. The fix:
only swap label texts WITHIN a length-equal group. Of the 11 field-row
labels (`generate_pdfs.invoice_field_rows()`), two groups have more than one
member — `{"Due date:", "Customer:", "Currency:", "Approved:"}` (9 chars
each) and `{"Invoice date:", "Total amount:"}` (13 chars each) — everything
else is a length-unique singleton and stays put. Cyclically rotating each
group internally (never by a shift that's a no-op for that group's size)
leaves every line's bbox byte-identical to the real invoice (same
fingerprint => guaranteed candidate hit) while making 6 of the 11 labels
wrong for their position (guaranteed rejection by the verifier's
`label_anchors` check, which requires ALL anchors to match).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

_FIXTURES_PDFS_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdfs"
if str(_FIXTURES_PDFS_DIR) not in sys.path:
    sys.path.insert(0, str(_FIXTURES_PDFS_DIR))

import generate_pdfs as generate_pdfs  # type: ignore[import-not-found]  # noqa: E402  (fixtures/pdfs/generate_pdfs.py)

DEFAULT_ROTATIONS: tuple[int, ...] = (1, 2, 3)


def _rotated_labels_by_element_id(rotate_by: int) -> dict[str, str]:
    """Rotate each length-equal group of field labels internally. Groups of
    size 1 (no same-length peer) are left untouched — swapping them would
    change their bbox width and break fingerprint parity."""
    rows = generate_pdfs.invoice_field_rows()
    groups: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for element_id, label in rows:
        groups[len(label)].append((element_id, label))

    rotated: dict[str, str] = {}
    for members in groups.values():
        labels = [label for _, label in members]
        shift = rotate_by % len(labels)
        if shift == 0 and len(labels) > 1:
            shift = 1  # never a no-op rotation when a real swap is possible
        rotated_labels = labels[shift:] + labels[:shift]
        for (element_id, _), new_label in zip(members, rotated_labels, strict=True):
            rotated[element_id] = new_label
    return rotated


def decoy_invoice_text_ops(data: generate_pdfs.InvoiceData, rotate_by: int) -> list[generate_pdfs.TextOp]:
    """The real invoice's `TextOp` stream (table/footer/value positions
    untouched), with field-label texts rotated within their length-equal
    group (see module docstring).

    Built by post-processing `generate_pdfs.invoice_text_ops`'s own output
    rather than reimplementing its layout, so any future change to that
    module's geometry stays in sync automatically. The 11 field-row label
    ops are exactly the first 11 ops at `x == LABEL_X` in draw order (every
    field row is emitted before the table/footer, which also happen to sit
    at `x == LABEL_X` for their leftmost column/footer text) — the trailing
    assertion catches any future drift in that assumption loudly instead of
    silently mis-rotating the wrong ops.
    """
    rows = generate_pdfs.invoice_field_rows()
    rotated_by_element_id = _rotated_labels_by_element_id(rotate_by)
    rotated_labels_in_row_order = [rotated_by_element_id[element_id] for element_id, _ in rows]

    real_ops = generate_pdfs.invoice_text_ops(data)
    rotated_ops: list[generate_pdfs.TextOp] = []
    label_index = 0
    for op in real_ops:
        if op.x == generate_pdfs.LABEL_X and label_index < len(rotated_labels_in_row_order):
            rotated_ops.append(generate_pdfs.TextOp(op.x, op.y, op.font_size, rotated_labels_in_row_order[label_index]))
            label_index += 1
        else:
            rotated_ops.append(op)
    if label_index != len(rotated_labels_in_row_order):
        raise AssertionError(
            f"expected to rotate exactly {len(rotated_labels_in_row_order)} label ops, rotated {label_index} "
            "— fixtures/pdfs/generate_pdfs.py's field-row layout may have changed"
        )
    return rotated_ops


def render_decoy_invoice_pdf(data: generate_pdfs.InvoiceData, rotate_by: int) -> bytes:
    content = generate_pdfs._content_stream(decoy_invoice_text_ops(data, rotate_by))
    pdf_bytes: bytes = generate_pdfs._assemble_pdf([(generate_pdfs.PAGE_WIDTH, generate_pdfs.PAGE_HEIGHT, content)])
    return pdf_bytes


def generate_decoy_corpus(rotations: tuple[int, ...] = DEFAULT_ROTATIONS) -> dict[str, bytes]:
    """`{decoy_name: pdf_bytes}` for every (base invoice, rotation) pair."""
    bases = {"nv20260042": generate_pdfs.NV_20260042, "nv20260043": generate_pdfs.NV_20260043}
    out: dict[str, bytes] = {}
    for base_name, data in bases.items():
        for rotate_by in rotations:
            out[f"decoy_{base_name}_rot{rotate_by}"] = render_decoy_invoice_pdf(data, rotate_by)
    return out
