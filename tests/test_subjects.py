from __future__ import annotations

import pytest

from coffee_contracts import CATALOGUE, CRAWL, SubjectError, catalogue, crawl


def test_one_subject_per_coffee() -> None:
    assert catalogue("kafista", "17133") == "coffee.v1.catalogue.kafista.17133"


def test_the_catalogue_stream_captures_every_coffee() -> None:
    assert catalogue("kafista", "17133").startswith(CATALOGUE.subjects[0][:-1])
    assert crawl("kafista").startswith(CRAWL.subjects[0][:-1])


def test_the_catalogue_stream_is_compacted_and_the_crawl_log_is_not() -> None:
    """The stream is the catalogue, so it keeps one message per coffee. Two
    runs of one shop are two facts, so that stream keeps both."""
    assert CATALOGUE.max_msgs_per_subject == 1
    assert CRAWL.max_msgs_per_subject == 0
    assert CRAWL.max_age_seconds > 0


@pytest.mark.parametrize("bad", ["a.b", "a>b", "a*b", "a b", ""])
def test_a_token_that_would_change_the_subject_is_refused(bad: str) -> None:
    """NATS reads dots and wildcards as structure, so an id carrying one would
    silently widen somebody's subscription."""
    with pytest.raises(SubjectError):
        catalogue(bad, "1")
    with pytest.raises(SubjectError):
        catalogue("demo", bad)
