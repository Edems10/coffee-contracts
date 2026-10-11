from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from coffee_contracts import (
    PRODUCT_KINDS,
    CoffeeState,
    ContractError,
    check,
    coffee_from_json,
    to_json,
)
from coffee_contracts.validate import _validator, schema

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


def test_the_product_kinds_are_the_schema_enum() -> None:
    """The exported vocabulary and the schema's enum are one list, in one order."""
    enum = schema("coffee.state")["properties"]["product_kind"]["enum"]

    assert list(PRODUCT_KINDS) == [kind for kind in enum if kind is not None]


def test_a_product_kind_and_species_split_survive_the_wire() -> None:
    coffee = a_coffee(
        product_kind="beans",
        product_kind_source="the page says Káva v zrnech",
        arabica_pct=70,
        robusta_pct=30,
    )

    check(json.loads(to_json(coffee)))

    assert coffee_from_json(to_json(coffee)) == coffee


@pytest.mark.parametrize("kind", ["paper_cup", "Beans", "coffee", ""])
def test_a_product_kind_outside_the_vocabulary_is_refused(kind: str) -> None:
    """An unknown kind fails here, because a consumer filtering on it would
    otherwise drop the rows it does not recognise without saying so."""
    payload = json.loads(to_json(a_coffee(product_kind=kind)))

    with pytest.raises(ContractError, match="is not one of"):
        check(payload)


def test_an_undecided_product_is_not_refused_when_its_fields_are_absent() -> None:
    """Absent is what an older producer sends; it must validate, and it must
    not be read as beans. The reader decides that, not the schema."""
    payload = json.loads(to_json(a_coffee()))
    for key in ("product_kind", "product_kind_source", "arabica_pct", "robusta_pct"):
        del payload[key]

    check(payload)


@pytest.mark.parametrize("share", [0, 100, None])
def test_a_species_share_is_a_whole_percentage_or_nothing(share: int | None) -> None:
    check(json.loads(to_json(a_coffee(arabica_pct=share, robusta_pct=share))))


@pytest.mark.parametrize("share", [-1, 101, 50.5, "50"])
def test_a_species_share_outside_a_whole_percentage_is_refused(share: object) -> None:
    payload = json.loads(to_json(a_coffee(arabica_pct=share)))

    with pytest.raises(ContractError):
        check(payload)


def test_other_is_a_decided_kind_and_passes_validation() -> None:
    """`other` is the escape for a product the producer has judged to be none of
    the named kinds. It is accepted, unlike a string the vocabulary never named."""
    check(json.loads(to_json(a_coffee(product_kind="other"))))


def test_a_first_seen_at_survives_the_wire_as_a_datetime() -> None:
    """The reader parses it the way it parses observed_at. Without that the
    field would come back as a string its own dataclass type forbids."""
    first_seen = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
    coffee = a_coffee(first_seen_at=first_seen)

    check(json.loads(to_json(coffee)))

    restored = coffee_from_json(to_json(coffee))
    assert restored == coffee
    assert restored.first_seen_at == first_seen


def test_a_payload_without_first_seen_at_is_still_valid() -> None:
    """An older producer does not send the field, and that must not be refused."""
    payload = json.loads(to_json(a_coffee()))
    del payload["first_seen_at"]

    check(payload)

    assert coffee_from_json(json.dumps(payload)).first_seen_at is None


def test_a_first_seen_at_of_the_wrong_type_is_refused() -> None:
    payload = json.loads(to_json(a_coffee()))
    payload["first_seen_at"] = 20260901

    with pytest.raises(ContractError):
        check(payload)


@pytest.mark.parametrize("stamp", ["yesterday", "2026-13-01T00:00:00Z"])
def test_a_first_seen_at_the_reader_cannot_parse_is_refused(stamp: str) -> None:
    payload = json.loads(to_json(a_coffee()))
    payload["first_seen_at"] = stamp

    with pytest.raises(ContractError, match="date-time"):
        check(payload)


@pytest.mark.parametrize("value", [True, False, None])
def test_decaf_keeps_all_three_answers_across_the_wire(value: bool | None) -> None:
    """True, False and None are three different answers. False must come back
    as False: a reader that took it for absent would lose the caffeinated
    coffees a caffeinated-only filter is asking for."""
    coffee = a_coffee(decaf=value)

    check(json.loads(to_json(coffee)))

    assert json.loads(to_json(coffee))["decaf"] is value
    assert coffee_from_json(to_json(coffee)).decaf is value


def test_a_payload_without_decaf_is_still_valid() -> None:
    """An older producer does not send the field, and absence must not be refused
    or read as a statement about caffeine."""
    payload = json.loads(to_json(a_coffee()))
    del payload["decaf"]

    check(payload)

    assert coffee_from_json(json.dumps(payload)).decaf is None


@pytest.mark.parametrize("value", ["yes", "false", 1, 0])
def test_a_decaf_that_is_not_a_boolean_is_refused(value: object) -> None:
    payload = json.loads(to_json(a_coffee()))
    payload["decaf"] = value

    with pytest.raises(ContractError):
        check(payload)
