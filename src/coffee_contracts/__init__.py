from __future__ import annotations

from coffee_contracts.events import (
    COFFEE_EMBEDDING,
    COFFEE_STATE,
    MAX_PRICE_HISTORY,
    PRODUCT_KINDS,
    CoffeeState,
    PricePoint,
    coffee_from_json,
    to_json,
)
from coffee_contracts.streams import CATALOGUE, EMBEDDINGS, STREAMS, Stream
from coffee_contracts.subjects import VERSION, SubjectError, catalogue, embedding
from coffee_contracts.validate import ContractError, check, schema

__version__ = "3.0.1"

__all__ = [
    "CATALOGUE",
    "COFFEE_EMBEDDING",
    "COFFEE_STATE",
    "EMBEDDINGS",
    "MAX_PRICE_HISTORY",
    "PRODUCT_KINDS",
    "STREAMS",
    "VERSION",
    "CoffeeState",
    "ContractError",
    "PricePoint",
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
