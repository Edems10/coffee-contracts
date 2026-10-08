from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffee_contracts import (
    CoffeeState,
    ContractError,
    check,
    coffee_from_json,
    to_json,
)
from coffee_contracts.validate import _validator

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


def test_every_message_declares_its_type() -> None:
    """A consumer switches on the type, not on the subject: a subject is
    routing and a type is meaning."""
    assert json.loads(to_json(a_coffee()))["type"] == "coffee.state"


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


def test_a_payload_without_a_type_is_refused() -> None:
    with pytest.raises(ContractError, match="no 'type'"):
        check({"site": "x"})


def test_a_country_that_is_not_an_iso_code_is_refused() -> None:
    """The producer validates before publishing, because a compacted stream
    keeps a bad message as that coffee's state until something replaces it."""
    payload = json.loads(to_json(a_coffee(origin_country="Etiopie")))

    with pytest.raises(ContractError):
        check(payload)


def test_a_timestamp_the_consumer_cannot_parse_is_refused() -> None:
    """`format` is an annotation jsonschema ignores unless it is handed a
    checker, so this one used to validate clean and then kill the reader. In a
    compacted stream it would have been that coffee's state until the next
    crawl replaced it, and every replay would have delivered it again."""
    payload = json.loads(to_json(a_coffee()))
    payload["observed_at"] = "not a date at all"

    with pytest.raises(ContractError, match="date-time"):
        check(payload)


@pytest.mark.parametrize("stamp", ["not a date at all", "2026-13-02T05:19:00Z", "", "05:19"])
def test_check_refuses_exactly_what_the_reader_cannot_parse(stamp: str) -> None:
    """The format check parses with `datetime.fromisoformat`, which is what
    `coffee_from_json` parses with. Holding the two to the same rule is the
    point: anything `check` passes, the other side can read."""
    payload = json.loads(to_json(a_coffee()))
    payload["observed_at"] = stamp

    with pytest.raises(ContractError):
        check(payload)
    # And the half that proves the two rules are the same rule: the reader
    # really does fall over on every string the check just refused.
    with pytest.raises(ValueError):  # noqa: PT011 — datetime's message is CPython's
        coffee_from_json(json.dumps(payload))


@pytest.mark.parametrize("stamp", ["2026-10-02T05:19:00+00:00", "2026-10-02T05:19:00Z"])
def test_both_spellings_of_an_instant_survive_the_check(stamp: str) -> None:
    """`to_json` writes the offset form and a producer in another language
    writes the `Z` form. They are the same instant, and a stricter check than
    the reader's would refuse a message the reader handles fine."""
    payload = json.loads(to_json(a_coffee()))
    payload["observed_at"] = stamp

    check(payload)

    assert coffee_from_json(json.dumps(payload)).observed_at == NOW


def test_what_to_json_writes_is_what_check_accepts() -> None:
    """The producer serialises and then validates, so the two have to agree on
    every field the serialiser emits, timestamps included."""
    payload = json.loads(to_json(a_coffee(delisted_at=NOW)))

    check(payload)

    assert payload["observed_at"] == "2026-10-02T05:19:00+00:00"


def test_a_null_delisted_at_is_not_a_malformed_timestamp() -> None:
    """`delisted_at` is null for every coffee still on sale. A format check
    that read a non-string as a bad date would refuse the whole catalogue."""
    check(json.loads(to_json(a_coffee(delisted_at=None))))


def test_the_validator_is_built_once_per_event_type() -> None:
    """`jsonschema.validate()` rebuilt the validator and re-ran full metaschema
    validation on every call, on a schema that never changes: 2.1 ms an event,
    four seconds across a replay of the catalogue."""
    assert _validator("coffee.state") is _validator("coffee.state")


def test_an_event_type_this_contract_does_not_have_is_refused() -> None:
    """The cached validator must not swallow the unknown-type error that the
    schema lookup raises."""
    with pytest.raises(ContractError, match="no schema for event type"):
        check({"type": "coffee.crawl"})
