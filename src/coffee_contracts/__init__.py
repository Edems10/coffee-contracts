from __future__ import annotations

from coffee_contracts.events import (
    COFFEE_STATE,
    CoffeeState,
    coffee_from_json,
    to_json,
)
from coffee_contracts.streams import CATALOGUE, STREAMS, Stream
from coffee_contracts.subjects import VERSION, SubjectError, catalogue
from coffee_contracts.validate import ContractError, check, schema

__version__ = "1.0.0"

__all__ = [
    "CATALOGUE",
    "COFFEE_STATE",
    "STREAMS",
    "VERSION",
    "CoffeeState",
    "ContractError",
    "Stream",
    "SubjectError",
    "__version__",
    "catalogue",
    "check",
    "coffee_from_json",
    "schema",
    "to_json",
]
