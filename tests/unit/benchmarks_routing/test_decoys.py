"""Unit tests for `benchmarks/routing/decoys.py`: decoys must fingerprint
identically to the real invoice (guaranteed candidate hit) while every
anchored label is wrong for its position (guaranteed verification
rejection) — the two properties criterion 2 depends on.
"""

from __future__ import annotations

from adapters.fingerprint import fpv
from adapters.fingerprint.born_digital import BornDigitalFingerprintExtractor
from benchmarks.routing import decoys
from domain.artifacts.canonical import JsonCanonicalSerializer


def test_generate_decoy_corpus_produces_one_pdf_per_base_and_rotation() -> None:
    corpus = decoys.generate_decoy_corpus()
    assert len(corpus) == 2 * len(decoys.DEFAULT_ROTATIONS)
    assert all(isinstance(pdf_bytes, bytes) and pdf_bytes.startswith(b"%PDF-1.4") for pdf_bytes in corpus.values())


def test_decoy_fingerprint_equals_the_real_invoices_fingerprint_guaranteed_candidate_hit() -> None:
    extractor = BornDigitalFingerprintExtractor()
    serializer = JsonCanonicalSerializer()

    real_bytes = decoys.generate_pdfs.render_invoice_pdf(decoys.generate_pdfs.NV_20260042)
    real_key = fpv.fingerprint_key(extractor.extract(real_bytes), serializer)

    for rotate_by in decoys.DEFAULT_ROTATIONS:
        decoy_bytes = decoys.render_decoy_invoice_pdf(decoys.generate_pdfs.NV_20260042, rotate_by)
        decoy_key = fpv.fingerprint_key(extractor.extract(decoy_bytes), serializer)
        assert decoy_key == real_key, f"rotate_by={rotate_by} broke fingerprint parity"


def test_decoy_labels_differ_from_their_real_positions_for_every_rotation() -> None:
    """Not every label can move (singletons would change bbox width and
    break fingerprint parity — see decoys.py's module docstring), but every
    `DEFAULT_ROTATIONS` value must move at least the two same-length groups
    (6 of the 11 rows), which is already enough to fail verification's
    `label_anchors` check (threshold: ALL anchors must match)."""
    real_ops = decoys.generate_pdfs.invoice_text_ops(decoys.generate_pdfs.NV_20260042)
    row_count = len(decoys.generate_pdfs.invoice_field_rows())
    real_labels_in_order = [op.text for op in real_ops if op.x == decoys.generate_pdfs.LABEL_X][:row_count]

    for rotate_by in decoys.DEFAULT_ROTATIONS:
        decoy_ops = decoys.decoy_invoice_text_ops(decoys.generate_pdfs.NV_20260042, rotate_by)
        decoy_labels_in_order = [op.text for op in decoy_ops if op.x == decoys.generate_pdfs.LABEL_X][:row_count]

        assert len(decoy_labels_in_order) == len(real_labels_in_order)
        pairs = zip(real_labels_in_order, decoy_labels_in_order, strict=True)
        mismatches = sum(1 for real, decoy in pairs if real != decoy)
        assert mismatches >= 6, f"rotate_by={rotate_by} only moved {mismatches} labels"
