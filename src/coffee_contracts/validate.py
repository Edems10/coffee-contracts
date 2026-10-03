from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

import jsonschema

SCHEMA_FILES = {
    "coffee.state": "coffee.state.v1.json",
}


class ContractError(ValueError):
    """Raised when a payload does not match the contract it claims to be."""


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


def check(payload: dict[str, Any]) -> None:
    """Fail if a payload does not match its own declared type.

    The producer validates before publishing, which is the only place a bad
    message can still be stopped: once it is in a compacted stream it is the
    state of that coffee until something replaces it.

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
        jsonschema.validate(payload, schema(event_type))
    except jsonschema.ValidationError as error:
        message = f"{event_type}: {error.message}"
        raise ContractError(message) from error
