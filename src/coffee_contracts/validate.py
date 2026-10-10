from __future__ import annotations

import json
from datetime import datetime
from functools import cache
from importlib import resources
from typing import Any

import jsonschema

from coffee_contracts.vector import vector_problem

SCHEMA_FILES = {
    "coffee.state": "coffee.state.v1.json",
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


#: ``format`` is an annotation jsonschema ignores unless it is handed a checker,
#: and its own ``date-time`` checker registers only when ``rfc3339-validator``
#: is installed, which it is not. Checking with ``datetime.fromisoformat``
#: asserts exactly what ``events._build`` parses with, so a timestamp that
#: passes here cannot be the one that kills the consumer — and a stricter
#: RFC 3339 check would refuse spellings this package's own reader accepts.
_FORMATS = jsonschema.FormatChecker()
_FORMATS.checks("date-time", raises=ValueError)(_is_date_time)


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
    if event_type == "coffee.embedding":
        problem = vector_problem(payload)
        if problem is not None:
            message = f"{event_type}: {problem}"
            raise ContractError(message)
