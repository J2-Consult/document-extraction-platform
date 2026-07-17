"""The deterministic hash-based fake embedder: no model calls, no new deps."""

from __future__ import annotations

from ports.vectorindex import Embedder


def test_hash_embedder_satisfies_the_embedder_protocol() -> None:
    from adapters.vectorindex.in_memory import HashEmbedder

    embedder: Embedder = HashEmbedder(dimensions=8)
    assert isinstance(embedder, Embedder)


def test_same_text_embeds_to_the_identical_vector() -> None:
    from adapters.vectorindex.in_memory import HashEmbedder

    embedder = HashEmbedder(dimensions=8)
    assert embedder.embed("bearing inspection") == embedder.embed("bearing inspection")


def test_different_texts_embed_to_different_vectors() -> None:
    from adapters.vectorindex.in_memory import HashEmbedder

    embedder = HashEmbedder(dimensions=8)
    assert embedder.embed("bearing inspection") != embedder.embed("corrective actions")


def test_vector_has_the_configured_dimension_and_plain_floats() -> None:
    from adapters.vectorindex.in_memory import HashEmbedder

    vector = HashEmbedder(dimensions=16).embed("x")
    assert len(vector) == 16
    assert all(isinstance(component, float) for component in vector)
    assert all(0.0 <= component <= 1.0 for component in vector)
