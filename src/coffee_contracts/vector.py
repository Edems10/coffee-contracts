from __future__ import annotations

import base64
from typing import Any

#: Bytes per element for each dtype the contract names. Adding one is a
#: contract change, so its entry lands together with the schema that states it.
_ITEMSIZE: dict[str, int] = {"float32": 4}


def vector_problem(payload: dict[str, Any]) -> str | None:
    """Say why an embedding's vector is not the size its payload states.

    A schema can say that ``vector`` is a string but not how many bytes that
    string decodes to, and a truncated base64 string still decodes cleanly. The
    decoded length is the check that stops a consumer reading a short vector as
    if it were whole.

    Args:
        payload: An embedding payload that has already passed its schema, so
            ``dimension``, ``dtype`` and ``vector`` are present and well typed.

    Returns:
        None when the vector decodes to exactly ``dimension`` elements of
        ``dtype``, otherwise the reason it does not.
    """
    try:
        # Strict, because the default discards characters outside the alphabet
        # and every value after one would then be read from the wrong bytes.
        raw = base64.b64decode(payload["vector"], validate=True)
    except ValueError:
        return "vector is not base64"
    expected = payload["dimension"] * _ITEMSIZE[payload["dtype"]]
    if len(raw) != expected:
        return (
            f"vector decodes to {len(raw)} bytes, but dimension {payload['dimension']} "
            f"of {payload['dtype']} is {expected}"
        )
    return None
