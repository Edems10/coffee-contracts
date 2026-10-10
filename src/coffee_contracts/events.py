from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

#: The event a coffee's state is carried in. Part of the contract: a consumer
#: switches on this, not on the subject, because a subject is routing and a
#: type is meaning.
COFFEE_STATE = "coffee.state"

#: The event one coffee's embedding is carried in, switched on the same way as
#: ``COFFEE_STATE``. Its vector is checked by ``vector.vector_problem``, not by
#: the schema alone.
COFFEE_EMBEDDING = "coffee.embedding"

#: The kinds a product may be, in the order ``coffee.state.v1.json`` lists them.
#: ``other`` is the decided catch-all for a product that is none of the named
#: kinds, listed last. Absent or null means undecided, which is a different answer.
#: Part of the contract: a test holds this tuple and the schema's enum to each
#: other, and ``check`` refuses a kind outside it rather than passing it through.
PRODUCT_KINDS: tuple[str, ...] = (
    "beans",
    "capsules",
    "instant",
    "green",
    "ready_to_drink",
    "sampler",
    "kit",
    "equipment",
    "merch",
    "food",
    "service",
    "cosmetics",
    "not_a_product",
    "other_drink",
    "test",
    "other",
)


@dataclass(frozen=True, slots=True)
class CoffeeState:
    """One coffee, whole, as the catalogue last saw it.

    The event carries the state rather than a pointer to it. A consumer that
    had to call back for the detail would be synchronously coupled to the
    producer, which is the thing this architecture exists to avoid.

    Attributes:
        site: The shop's registry id.
        external_id: The shop's own id for the product.
        observed_at: When the crawl that produced this saw it.
        name: The product name as the shop prints it.
        product_kind: What the product is, from ``PRODUCT_KINDS``; None while undecided.
        product_kind_source: How the kind was decided, as a sentence.
        url: Where to buy it.
        roaster: Who roasted it, when the shop says.
        origin_country: ISO 3166 alpha-2, or None for a blend.
        origin_region: The growing region, free text.
        process_method: The processing method, as the catalogue's enum names it.
        roast_level: light .. dark, or ``"unknown"``.
        roast_profile: espresso, filter or omni, or ``"unknown"``.
        variety: Cultivars, as the shop lists them.
        arabica_pct: The arabica share the shop states, 0 to 100; None when it says nothing.
        robusta_pct: The robusta share the shop states, 0 to 100; None when it says nothing.
        altitude_min_m: The lower end of the stated altitude.
        flavor_notes: Cup notes, as the shop wrote them.
        tasting_text: The shop's prose description of the cup.
        sca_score: The cupping score, when published.
        weight_g: The net weight the price buys.
        price: The price of that package.
        currency: The ISO code the shop prices in.
        price_per_kg_eur: The comparable price.
        available: Whether the shop says it is in stock.
        delisted_at: When the shop stopped listing it; None while it is sold.
        first_seen_at: When this catalogue first saw it, not its release date; None if unrecorded.
    """

    site: str
    external_id: str
    observed_at: datetime
    name: str | None = None
    product_kind: str | None = None
    product_kind_source: str | None = None
    url: str | None = None
    roaster: str | None = None
    origin_country: str | None = None
    origin_region: str | None = None
    process_method: str | None = None
    roast_level: str | None = None
    roast_profile: str | None = None
    variety: list[str] = field(default_factory=list)
    arabica_pct: int | None = None
    robusta_pct: int | None = None
    altitude_min_m: int | None = None
    flavor_notes: list[str] = field(default_factory=list)
    tasting_text: str | None = None
    sca_score: float | None = None
    weight_g: int | None = None
    price: float | None = None
    currency: str | None = None
    price_per_kg_eur: float | None = None
    available: bool | None = None
    delisted_at: datetime | None = None
    first_seen_at: datetime | None = None

    @property
    def key(self) -> str:
        """The catalogue-wide identifier of this coffee.

        Returns:
            ``site/external_id``.
        """
        return f"{self.site}/{self.external_id}"

    @property
    def is_delisted(self) -> bool:
        """Whether the shop has stopped selling this.

        A delisting is a state, not a deleted message, so that it survives the
        stream's per-subject compaction like every other fact about the coffee.

        Returns:
            True once the catalogue recorded it as gone.
        """
        return self.delisted_at is not None


def to_json(event: CoffeeState) -> bytes:
    """Serialise an event for the wire.

    Args:
        event: The event.

    Returns:
        Compact UTF-8 JSON, with datetimes as ISO 8601.
    """
    payload = asdict(event)
    payload["type"] = COFFEE_STATE
    return json.dumps(payload, default=_encode, separators=(",", ":")).encode()


def coffee_from_json(raw: bytes | str) -> CoffeeState:
    """Read a coffee state off the wire.

    Unknown keys are dropped rather than raising: a producer on a later minor
    version of the contract adds fields, and a consumer that refused them would
    make every additive change a breaking one.

    Args:
        raw: The message body.

    Returns:
        The event.
    """
    return _build(CoffeeState, json.loads(raw))


def _encode(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    message = f"{type(value).__name__} is not part of the contract"
    raise TypeError(message)


def _build(cls: type[CoffeeState], payload: dict[str, Any]) -> CoffeeState:
    fields = {f.name for f in cls.__dataclass_fields__.values()}
    known = {k: v for k, v in payload.items() if k in fields}
    for name in ("observed_at", "delisted_at", "first_seen_at"):
        if isinstance(known.get(name), str):
            known[name] = datetime.fromisoformat(known[name])
    return cls(**known)
