from __future__ import annotations

import itertools
import json
from datetime import date, datetime
from functools import cache
from importlib import resources
from typing import Any

import jsonschema

from coffee_contracts.events import MONEY_FIELDS
from coffee_contracts.vector import vector_problem

SCHEMA_FILES = {
    "coffee.state": "coffee.state.v2.json",
    "coffee.embedding": "coffee.embedding.v1.json",
}


class ContractError(ValueError):
    """Raised when a payload does not match the contract it claims to be."""


def _is_date_time(value: object) -> bool:
    """Whether a ``date-time`` is one the other side will be able to read back.

    Args:
        value: The instance the schema annotated ``format: date-time``.

    Returns:
        True, including for a non-string: what type a property may be is the
        ``type`` keyword's business, and ``delisted_at`` is legitimately null.

    Raises:
        ValueError: When a string is not a timestamp, which the registration
            below turns into an ordinary validation failure.
    """
    if not isinstance(value, str):
        return True
    datetime.fromisoformat(value)
    return True


def _is_date(value: object) -> bool:
    """Whether a ``date`` is one the other side will be able to read back.

    Args:
        value: The instance the schema annotated ``format: date``.

    Returns:
        True, including for a non-string, for the same reason as ``_is_date_time``.

    Raises:
        ValueError: When a string is not a calendar date, which the registration
            below turns into an ordinary validation failure.
    """
    if not isinstance(value, str):
        return True
    date.fromisoformat(value)
    return True


#: ``format`` is an annotation jsonschema ignores unless it is handed a checker,
#: and its own ``date-time`` checker registers only when ``rfc3339-validator``
#: is installed, which it is not. Checking with ``datetime.fromisoformat``
#: asserts exactly what ``events._build`` parses with, so a timestamp that
#: passes here cannot be the one that kills the consumer — and a stricter
#: RFC 3339 check would refuse spellings this package's own reader accepts.
_FORMATS = jsonschema.FormatChecker()
_FORMATS.checks("date-time", raises=ValueError)(_is_date_time)
_FORMATS.checks("date", raises=ValueError)(_is_date)


@cache
def schema(event_type: str) -> dict[str, Any]:
    """Return the JSON Schema for one event type.

    Args:
        event_type: The ``type`` field of the payload.

    Returns:
        The parsed schema.

    Raises:
        ContractError: When no such event type is in this contract version.
    """
    try:
        name = SCHEMA_FILES[event_type]
    except KeyError as error:
        message = f"no schema for event type {event_type!r}"
        raise ContractError(message) from error
    text = resources.files("coffee_contracts.schemas").joinpath(name).read_text("utf-8")
    loaded: dict[str, Any] = json.loads(text)
    return loaded


@cache
def _validator(event_type: str) -> jsonschema.Draft202012Validator:
    """Return the validator for one event type, built once and kept.

    ``jsonschema.validate()`` rebuilds the validator and re-runs full metaschema
    validation on every single call. For a schema that never changes, that
    measured 2108 us an event against 40 us here: four seconds of a catalogue
    replay spent re-deciding that a static file is a valid schema. That the
    schemas really are valid is settled in the test suite instead, where it
    costs nothing at run time.

    Args:
        event_type: The ``type`` field of the payload.

    Returns:
        A Draft 2020-12 validator for the event type's schema, checking formats
        with ``_FORMATS``.

    Raises:
        ContractError: When no such event type is in this contract version.
    """
    return jsonschema.Draft202012Validator(schema(event_type), format_checker=_FORMATS)


def check(payload: dict[str, Any]) -> None:
    """Fail if a payload does not match its own declared type.

    The producer validates before publishing, which is the only place a bad
    message can still be stopped: once it is in a compacted stream it is the
    state of that coffee until something replaces it, and every replay hands
    it to every consumer again.

    An embedding's vector is checked by ``vector.vector_problem`` once the schema
    has passed. The decoded length of a base64 string is the one rule no schema
    keyword carries here, and ``vector_problem`` reads the ``dimension``,
    ``dtype`` and ``vector`` keys that the schema guarantees.

    A ``coffee.state`` money field must be a JSON integer, and a float spelling
    of a whole number is refused here too. The schema cannot say so: JSON
    Schema's ``integer`` is a mathematical integer, so ``2450.0`` satisfies it,
    and the reader would then hand the consumer a float.

    Args:
        payload: The decoded message body.

    Raises:
        ContractError: When the payload has no type, or does not match it.
    """
    event_type = payload.get("type")
    if not isinstance(event_type, str):
        message = "payload has no 'type'"
        raise ContractError(message)
    try:
        _validator(event_type).validate(payload)
    except jsonschema.ValidationError as error:
        message = f"{event_type}: {error.message}"
        raise ContractError(message) from error
    if event_type == "coffee.state":
        for name in MONEY_FIELDS:
            value = payload.get(name)
            if value is not None and type(value) is not int:
                message = (
                    f"{event_type}: {name} must be a whole number of minor units, got {value!r}"
                )
                raise ContractError(message)
    if event_type == "coffee.embedding":
        problem = vector_problem(payload)
        if problem is not None:
            message = f"{event_type}: {problem}"
            raise ContractError(message)
    if event_type == "coffee.state":
        problem = price_history_problem(payload)
        if problem is not None:
            message = f"{event_type}: {problem}"
            raise ContractError(message)


def price_history_problem(payload: dict[str, Any]) -> str | None:
    """Say why a coffee's price history is not the series the contract describes.

    The schema checks each point's shape and the length cap. The schema cannot
    refuse a float spelling of a whole number, because JSON Schema's ``integer``
    admits ``2450.0``, so each point's ``price_per_kg_eur_cents`` is held to
    ``int`` here, as the top-level money fields are. The rules between points
    need the whole series at once: the dates ascend strictly, no two consecutive
    points carry the same price and availability, since a point is a change, and
    the last point is not after ``observed_at``. Run this only on a payload the
    schema has already passed.

    Args:
        payload: The decoded ``coffee.state`` body, with ``observed_at`` and
            ``price_history`` as the schema shaped them.

    Returns:
        None when the series is well formed or absent. Otherwise one sentence
        naming the first fault found.
    """
    series: list[dict[str, Any]] = payload.get("price_history", [])
    for index, point in enumerate(series):
        cents = point["price_per_kg_eur_cents"]
        if cents is not None and type(cents) is not int:
            return (
                f"price_history[{index}] price_per_kg_eur_cents must be a whole number "
                f"of cents, got {cents!r}"
            )
    for before, after in itertools.pairwise(series):
        if date.fromisoformat(after["on"]) <= date.fromisoformat(before["on"]):
            return f"price_history is not in date order at {after['on']}"
        if _same_price(before, after):
            return f"price_history repeats {after['on']}: a point is a change, not a day"
    if series:
        last = date.fromisoformat(series[-1]["on"])
        if last > datetime.fromisoformat(payload["observed_at"]).date():
            return "price_history runs past observed_at"
    return None


def _same_price(before: dict[str, Any], after: dict[str, Any]) -> bool:
    """Whether two points carry the same price and availability.

    Args:
        before: The earlier point, as the schema shaped it, with integer cents.
        after: The later point, as the schema shaped it, with integer cents.

    Returns:
        True when the availability is equal and the cents are equal. Two nulls
        are equal.
    """
    same_price = before["price_per_kg_eur_cents"] == after["price_per_kg_eur_cents"]
    return bool(same_price and before["available"] == after["available"])
