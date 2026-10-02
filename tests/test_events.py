from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffee_contracts import (
    CoffeeState,
    ContractError,
    CrawlFinished,
    check,
    coffee_from_json,
    crawl_from_json,
    to_json,
)

NOW = datetime(2026, 10, 2, 5, 19, tzinfo=UTC)


def a_coffee(**overrides: object) -> CoffeeState:
    values: dict[str, object] = {
        "site": "kafista",
        "external_id": "17133",
        "observed_at": NOW,
        "name": "Ethiopia Guji",
        "origin_country": "ET",
        "flavor_notes": ["jahody", "med"],
        "price_per_kg_eur": 39.65,
    }
    values.update(overrides)
    return CoffeeState(**values)  # type: ignore[arg-type]


def test_a_coffee_survives_the_wire() -> None:
    restored = coffee_from_json(to_json(a_coffee()))

    assert restored == a_coffee()
    assert restored.observed_at == NOW


def test_a_crawl_result_survives_the_wire() -> None:
    event = CrawlFinished(
        site="kafista", started_at=NOW, finished_at=NOW, written=75, complete=True
    )

    assert crawl_from_json(to_json(event)) == event


def test_every_message_declares_its_type() -> None:
    """A consumer switches on the type, not on the subject: a subject is
    routing and a type is meaning."""
    assert json.loads(to_json(a_coffee()))["type"] == "coffee.state"
    assert json.loads(to_json(CrawlFinished("x", NOW, NOW)))["type"] == "crawl.finished"


def test_a_delisting_is_a_state_not_a_deletion() -> None:
    """The stream keeps one message per coffee, so a deleted message would take
    the fact that it was delisted with it."""
    gone = a_coffee(delisted_at=NOW)

    assert gone.is_delisted is True
    assert coffee_from_json(to_json(gone)).delisted_at == NOW


def test_a_field_this_version_never_heard_of_is_ignored() -> None:
    """A producer on a later minor version adds fields. Refusing them would
    make every additive change a breaking one."""
    payload = json.loads(to_json(a_coffee()))
    payload["cupping_table"] = {"sweetness": 8}

    restored = coffee_from_json(json.dumps(payload))

    assert restored.site == "kafista"


def test_a_valid_payload_passes_its_schema() -> None:
    check(json.loads(to_json(a_coffee())))
    check(json.loads(to_json(CrawlFinished("x", NOW, NOW))))


def test_a_payload_without_a_type_is_refused() -> None:
    with pytest.raises(ContractError, match="no 'type'"):
        check({"site": "x"})


def test_a_country_that_is_not_an_iso_code_is_refused() -> None:
    """The producer validates before publishing, because a compacted stream
    keeps a bad message as that coffee's state until something replaces it."""
    payload = json.loads(to_json(a_coffee(origin_country="Etiopie")))

    with pytest.raises(ContractError):
        check(payload)
