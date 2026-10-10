from __future__ import annotations

from coffee_contracts.events import (
    COFFEE_EMBEDDING,
    COFFEE_STATE,
    CoffeeState,
    coffee_from_json,
    to_json,
)
from coffee_contracts.streams import CATALOGUE, EMBEDDINGS, STREAMS, Stream
from coffee_contracts.subjects import VERSION, SubjectError, catalogue, embedding
from coffee_contracts.validate import ContractError, check, schema

__version__ = "2.2.0"

__all__ = [
    "CATALOGUE",
    "COFFEE_EMBEDDING",
    "COFFEE_STATE",
    "EMBEDDINGS",
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
    "embedding",
    "schema",
    "to_json",
]
