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


def test_a_point_is_six_json_native_values() -> None:
    """Each point is written as a date string, two integers, a boolean, a string
    and an integer, with no text for the reader to parse. A field the producer
    left unset is written as null."""
    payload = json.loads(to_json(a_coffee(price_history=a_series()[:1])))

    assert payload["price_history"] == [
        {
            "on": "2026-08-01",
            "price_per_kg_eur_cents": 2450,
            "available": True,
            "price_minor": None,
            "currency": None,
            "weight_g": None,
        }
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


def a_priced_series() -> list[PricePoint]:
    """Two points for a coffee whose shop raised its price while EUR/kg stood still.

    Returns:
        Two ``PricePoint`` values, 24900 then 26900 CZK for 250 g, both carrying
        3965 euro cents per kilogram.
    """
    return [
        PricePoint(
            on=date(2026, 9, 1),
            price_per_kg_eur_cents=3965,
            available=True,
            price_minor=24900,
            currency="CZK",
            weight_g=250,
        ),
        PricePoint(
            on=date(2026, 9, 20),
            price_per_kg_eur_cents=3965,
            available=True,
            price_minor=26900,
            currency="CZK",
            weight_g=250,
        ),
    ]


def a_payload_with(points: list[dict[str, object]]) -> dict[str, object]:
    """Build a ``coffee.state`` payload whose ``price_history`` is the given raw points.

    Args:
        points: The ``price_history`` elements as JSON, written by the caller so a test
            can spell keys and values the dataclass would not allow.

    Returns:
        The decoded wire payload of ``a_coffee()`` with ``price_history`` replaced.
    """
    payload: dict[str, object] = json.loads(to_json(a_coffee()))
    payload["price_history"] = points
    return payload


def v320_series(count: int) -> list[dict[str, object]]:
    """Build the series ``a_long_series`` made at v3.2.0, as the three-key JSON it was.

    Args:
        count: How many points, one per day from 1 January 2026, each price one euro
            above the last.

    Returns:
        The points as raw dicts holding only ``on``, ``price_per_kg_eur_cents`` and
        ``available``.
    """
    first = date(2026, 1, 1).toordinal()
    return [
        {
            "on": date.fromordinal(first + day).isoformat(),
            "price_per_kg_eur_cents": (day + 1) * 100,
            "available": True,
        }
        for day in range(count)
    ]


def test_the_shop_price_weight_and_currency_survive_the_wire_with_their_types() -> None:
    coffee = a_coffee(price_history=a_priced_series())

    check(json.loads(to_json(coffee)))
    restored = coffee_from_json(to_json(coffee))

    assert restored == coffee
    first = restored.price_history[0]
    assert type(first.price_minor) is int
    assert first.price_minor == 24900
    assert type(first.currency) is str
    assert first.currency == "CZK"
    assert type(first.weight_g) is int
    assert first.weight_g == 250


def test_a_point_that_leaves_the_new_fields_unset_reads_them_as_none() -> None:
    restored = coffee_from_json(to_json(a_coffee(price_history=a_series())))

    assert [
        (point.price_minor, point.currency, point.weight_g) for point in restored.price_history
    ] == [(None, None, None)] * 3


@pytest.mark.parametrize("count", [0, 3, MAX_PRICE_HISTORY])
def test_a_series_valid_at_v3_2_0_still_passes_and_reads_back_with_none(count: int) -> None:
    """Counter-example that must not change: the series ``a_series`` and
    ``a_long_series`` built at v3.2.0, written with only that version's three keys."""
    points: list[dict[str, object]] = (
        [
            {"on": "2026-08-01", "price_per_kg_eur_cents": 2450, "available": True},
            {"on": "2026-09-10", "price_per_kg_eur_cents": 2600, "available": True},
            {"on": "2026-10-01", "price_per_kg_eur_cents": None, "available": False},
        ]
        if count == 3
        else v320_series(count)
    )
    payload = a_payload_with(points)

    check(payload)
    restored = coffee_from_json(json.dumps(payload))

    assert len(restored.price_history) == count
    assert all(
        (point.price_minor, point.currency, point.weight_g) == (None, None, None)
        for point in restored.price_history
    )
    assert [point.price_per_kg_eur_cents for point in restored.price_history] == [
        point["price_per_kg_eur_cents"] for point in points
    ]


def test_a_v3_2_0_series_where_only_the_eur_per_kg_changes_still_passes() -> None:
    """At v3.2.0 a change in the euro price alone started a point. ``check`` still
    accepts it: the absent shop fields are null on both sides, but the euro price
    differs, so the points are not identical."""
    payload = a_payload_with(
        [
            {"on": "2026-09-01", "price_per_kg_eur_cents": 3965, "available": True},
            {"on": "2026-09-02", "price_per_kg_eur_cents": 3971, "available": True},
        ]
    )

    check(payload)

    assert [
        p.price_per_kg_eur_cents for p in coffee_from_json(json.dumps(payload)).price_history
    ] == [
        3965,
        3971,
    ]


@pytest.mark.parametrize(
    ("second", "changed"),
    [
        ({"price_minor": 26900}, "price_minor"),
        ({"weight_g": 500}, "weight_g"),
        ({"currency": "EUR"}, "currency"),
    ],
)
def test_a_point_that_differs_only_in_the_shop_price_weight_or_currency_is_accepted(
    second: dict[str, object], changed: str
) -> None:
    first_point: dict[str, object] = {
        "on": "2026-09-01",
        "price_per_kg_eur_cents": 3965,
        "available": True,
        "price_minor": 24900,
        "currency": "CZK",
        "weight_g": 250,
    }
    second_point = {**first_point, "on": "2026-09-20", **second}
    assert first_point[changed] != second_point[changed]

    check(a_payload_with([first_point, second_point]))


def test_two_points_equal_in_all_five_values_are_refused() -> None:
    point: dict[str, object] = {
        "price_per_kg_eur_cents": 3965,
        "available": True,
        "price_minor": 24900,
        "currency": "CZK",
        "weight_g": 250,
    }
    payload = a_payload_with(
        [{"on": "2026-09-01", **point}, {"on": "2026-09-20", **point}],
    )

    with pytest.raises(ContractError, match="a point is a change, not a day"):
        check(payload)


def test_an_absent_new_key_counts_as_null_when_comparing_points() -> None:
    payload = a_payload_with(
        [
            {"on": "2026-09-01", "price_per_kg_eur_cents": 3965, "available": True},
            {
                "on": "2026-09-20",
                "price_per_kg_eur_cents": 3965,
                "available": True,
                "price_minor": None,
                "currency": None,
                "weight_g": None,
            },
        ]
    )

    with pytest.raises(ContractError, match="a point is a change, not a day"):
        check(payload)


@pytest.mark.parametrize("spelled", ["2450.0", "24.5"])
def test_a_float_spelling_of_price_minor_inside_a_point_is_refused(spelled: str) -> None:
    raw = to_json(a_coffee(price_history=a_priced_series()[:1])).decode()
    float_raw = raw.replace('"price_minor":24900', f'"price_minor":{spelled}')
    assert float_raw != raw

    with pytest.raises(ContractError):
        check(json.loads(float_raw))
    with pytest.raises(ValueError, match="whole number of minor units"):
        coffee_from_json(float_raw)


def test_a_string_price_minor_inside_a_point_is_refused_by_check() -> None:
    payload = a_payload_with(
        [
            {
                "on": "2026-09-01",
                "price_per_kg_eur_cents": 3965,
                "available": True,
                "price_minor": "2450",
            }
        ]
    )

    with pytest.raises(ContractError):
        check(payload)


def test_the_item_still_requires_only_the_three_v3_2_0_keys() -> None:
    items = schema("coffee.state")["properties"]["price_history"]["items"]

    assert items["required"] == ["on", "price_per_kg_eur_cents", "available"]
    assert items["additionalProperties"] is True
