from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from coffee_contracts import (
    MAX_PRICE_HISTORY,
    CoffeeState,
    ContractError,
    PricePoint,
    check,
    coffee_from_json,
    to_json,
)
from coffee_contracts.validate import schema

NOW = datetime(2026, 10, 2, 5, 19, tzinfo=UTC)


def a_coffee(**overrides: object) -> CoffeeState:
    values: dict[str, object] = {
        "site": "kafista",
        "external_id": "17133",
        "observed_at": NOW,
        "name": "Ethiopia Guji",
        "price_per_kg_eur_cents": 3965,
    }
    values.update(overrides)
    return CoffeeState(**values)  # type: ignore[arg-type]


def a_series() -> list[PricePoint]:
    return [
        PricePoint(on=date(2026, 8, 1), price_per_kg_eur_cents=2450, available=True),
        PricePoint(on=date(2026, 9, 10), price_per_kg_eur_cents=2600, available=True),
        PricePoint(on=date(2026, 10, 1), price_per_kg_eur_cents=None, available=False),
    ]


def a_long_series(count: int) -> list[PricePoint]:
    """One change per day from 1 January 2026, each price one euro above the last."""
    first = date(2026, 1, 1).toordinal()
    return [
        PricePoint(
            on=date.fromordinal(first + day),
            price_per_kg_eur_cents=(day + 1) * 100,
            available=True,
        )
        for day in range(count)
    ]


def test_a_price_history_survives_the_wire_with_its_types() -> None:
    """Equality of the whole state, and the exact types of the new fields: an
    integer must come back as an int and a date as a date."""
    coffee = a_coffee(price_history=a_series())

    check(json.loads(to_json(coffee)))
    restored = coffee_from_json(to_json(coffee))

    assert restored == coffee
    assert restored.price_history == a_series()
    first = restored.price_history[0]
    assert type(first.on) is date
    assert type(first.price_per_kg_eur_cents) is int
    assert first.price_per_kg_eur_cents == 2450


def test_a_point_is_three_json_native_values() -> None:
    """Each point is written as a date string, an integer and a boolean, with no
    text for the reader to parse."""
    payload = json.loads(to_json(a_coffee(price_history=a_series()[:1])))

    assert payload["price_history"] == [
        {"on": "2026-08-01", "price_per_kg_eur_cents": 2450, "available": True}
    ]


def test_an_empty_price_history_round_trips() -> None:
    """Every existing producer sends an empty series, so it must read back empty."""
    coffee = a_coffee()

    check(json.loads(to_json(coffee)))

    assert coffee_from_json(to_json(coffee)).price_history == []


def test_a_message_without_price_history_reads_as_an_empty_list() -> None:
    """Counter-example that must not change: a state written before this field
    existed has no ``price_history`` key at all. It must still validate and
    must read back as an empty list, not raise."""
    raw = """{
        "type": "coffee.state",
        "site": "kafista",
        "external_id": "17133",
        "observed_at": "2026-10-02T05:19:00+00:00",
        "name": "Ethiopia Guji",
        "origin_country": "ET",
        "flavor_notes": ["jahody", "med"],
        "price_per_kg_eur_cents": 3965,
        "images": []
    }"""

    check(json.loads(raw))
    restored = coffee_from_json(raw)

    assert restored.price_history == []


def test_a_valid_series_passes_the_check() -> None:
    check(json.loads(to_json(a_coffee(price_history=a_series()))))


def test_a_series_as_long_as_the_cap_passes() -> None:
    check(json.loads(to_json(a_coffee(price_history=a_long_series(MAX_PRICE_HISTORY)))))


def test_a_series_longer_than_the_cap_is_refused() -> None:
    with pytest.raises(ContractError, match="is too long"):
        check(json.loads(to_json(a_coffee(price_history=a_long_series(MAX_PRICE_HISTORY + 1)))))


def test_the_schema_cap_is_the_exported_constant() -> None:
    """The cap is stated twice, once for the reader of the constant and once in
    the schema consumers validate against. They must be the same number."""
    cap = schema("coffee.state")["properties"]["price_history"]["maxItems"]

    assert cap == MAX_PRICE_HISTORY == 50


@pytest.mark.parametrize(
    "points",
    [
        [
            {"on": "2026-10-01", "price_per_kg_eur_cents": 2450, "available": True},
            {"on": "2026-09-01", "price_per_kg_eur_cents": 2600, "available": True},
        ],
        [
            {"on": "2026-09-01", "price_per_kg_eur_cents": 2450, "available": True},
            {"on": "2026-09-01", "price_per_kg_eur_cents": 2600, "available": True},
        ],
        [
            {"on": "2026-09-01", "price_per_kg_eur_cents": 2450, "available": True},
            {"on": "2026-09-05", "price_per_kg_eur_cents": 2450, "available": True},
        ],
        [{"on": "2026-10-03", "price_per_kg_eur_cents": 2450, "available": True}],
    ],
    ids=["out of order", "same date twice", "repeated price", "after observed_at"],
)
def test_a_malformed_series_is_refused(points: list[dict[str, object]]) -> None:
    payload = json.loads(to_json(a_coffee()))
    payload["price_history"] = points

    with pytest.raises(ContractError):
        check(payload)


@pytest.mark.parametrize(
    "point",
    [
        {"on": "2026-13-01", "price_per_kg_eur_cents": 2450, "available": True},
        {"on": "yesterday", "price_per_kg_eur_cents": 2450, "available": True},
        {"on": "2026-09-01", "price_per_kg_eur_cents": "2450", "available": True},
        {"on": "2026-09-01", "price_per_kg_eur_cents": "24.50", "available": True},
        {"on": "2026-09-01", "price_per_kg_eur_cents": 2450, "available": "yes"},
        {"on": "2026-09-01", "price_per_kg_eur_cents": 2450},
    ],
)
def test_a_malformed_point_is_refused(point: dict[str, object]) -> None:
    """Each point's shape is the schema's business: a bad date, a string where
    the integer belongs, a wrong availability, or a missing key."""
    payload = json.loads(to_json(a_coffee()))
    payload["price_history"] = [point]

    with pytest.raises(ContractError):
        check(payload)


def test_a_float_spelling_of_cents_inside_a_point_is_refused_by_check() -> None:
    """The top-level money fields refuse ``2450.0``, because JSON Schema's
    ``integer`` admits it. A point must refuse it too, or a float would reach a
    consumer through the one field the top-level check does not walk."""
    raw = to_json(a_coffee(price_history=a_series()[:1])).decode()
    payload = json.loads(
        raw.replace('"price_per_kg_eur_cents":2450', '"price_per_kg_eur_cents":2450.0')
    )

    with pytest.raises(ContractError, match="whole number of cents"):
        check(payload)


def test_a_float_spelling_of_cents_inside_a_point_is_refused_by_the_reader() -> None:
    """The reader refuses the same float as ``check`` does, so an unchecked
    message cannot hand a consumer a float price either."""
    raw = to_json(a_coffee(price_history=a_series()[:1])).decode()
    spelled = raw.replace('"price_per_kg_eur_cents":2450', '"price_per_kg_eur_cents":2450.0')

    with pytest.raises(ValueError, match="whole number of cents"):
        coffee_from_json(spelled)


def test_a_price_history_that_is_not_a_list_is_refused() -> None:
    payload = json.loads(to_json(a_coffee()))
    payload["price_history"] = {"on": "2026-09-01"}

    with pytest.raises(ContractError):
        check(payload)
