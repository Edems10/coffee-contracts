from __future__ import annotations

import pytest

from coffee_contracts import CATALOGUE, SubjectError, catalogue


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
