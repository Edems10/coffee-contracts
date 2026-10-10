from __future__ import annotations

import pytest

from coffee_contracts import (
    CATALOGUE,
    EMBEDDINGS,
    STREAMS,
    SubjectError,
    catalogue,
    embedding,
)


def test_one_subject_per_coffee() -> None:
    assert catalogue("kafista", "17133") == "coffee.v1.catalogue.kafista.17133"


def test_the_catalogue_stream_captures_every_coffee() -> None:
    assert catalogue("kafista", "17133").startswith(CATALOGUE.subjects[0][:-1])


def test_the_catalogue_stream_is_compacted() -> None:
    """The stream is the catalogue, so it keeps one message per coffee: a
    consumer that replays it from the start sees each coffee exactly once."""
    assert CATALOGUE.max_msgs_per_subject == 1


@pytest.mark.parametrize("bad", ["a.b", "a>b", "a*b", "a b", ""])
def test_a_token_that_would_change_the_subject_is_refused(bad: str) -> None:
    """NATS reads dots and wildcards as structure, so an id carrying one would
    silently widen somebody's subscription."""
    with pytest.raises(SubjectError):
        catalogue(bad, "1")
    with pytest.raises(SubjectError):
        catalogue("demo", bad)


def test_one_embedding_subject_per_coffee() -> None:
    assert embedding("kafista", "17133") == "coffee.v1.embedding.kafista.17133"


def test_the_embedding_subject_round_trips_to_its_coffee() -> None:
    """A consumer joins a vector to its coffee on the same site and id, so the
    subject has to give those two tokens back unchanged."""
    _, _, _, site, external_id = embedding("kafista", "17133").split(".")

    assert (site, external_id) == ("kafista", "17133")


def test_the_embedding_stream_captures_embeddings_and_not_coffee_state() -> None:
    subject = embedding("kafista", "17133")

    assert subject.startswith(EMBEDDINGS.subjects[0][:-1])
    assert not subject.startswith(CATALOGUE.subjects[0][:-1])


def test_the_embedding_stream_is_compacted() -> None:
    """Replaying it once must give each coffee's current vector and nothing twice."""
    assert EMBEDDINGS.max_msgs_per_subject == 1


def test_the_embedding_stream_is_declared_beside_the_catalogue() -> None:
    assert EMBEDDINGS in STREAMS
    assert CATALOGUE in STREAMS
    assert len({stream.name for stream in STREAMS}) == len(STREAMS)


@pytest.mark.parametrize("bad", ["a.b", "a>b", "a*b", "a b", ""])
def test_a_token_that_would_change_the_embedding_subject_is_refused(bad: str) -> None:
    with pytest.raises(SubjectError):
        embedding(bad, "1")
    with pytest.raises(SubjectError):
        embedding("demo", bad)
