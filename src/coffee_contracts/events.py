from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

#: The event a coffee's state is carried in. Part of the contract: a consumer
#: switches on this, not on the subject, because a subject is routing and a
#: type is meaning.
COFFEE_STATE = "coffee.state"

#: The event one coffee's embedding is carried in, switched on the same way as
#: ``COFFEE_STATE``. Its vector is checked by ``vector.vector_problem``, not by
#: the schema alone.
COFFEE_EMBEDDING = "coffee.embedding"

#: The ``CoffeeState`` fields that carry money. Each is a whole count of a minor
#: unit, so the reader and ``validate.check`` both hold them to ``int``: a JSON
#: ``2450.0`` is refused rather than read as a float.
MONEY_FIELDS: tuple[str, ...] = ("price_minor", "price_per_kg_eur_cents")

#: The kinds a product may be, in the order ``coffee.state.v2.json`` lists them.
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

#: The brewing methods a coffee may be listed as suiting, in the order
#: ``coffee.state.v2.json`` lists them. A method outside the vocabulary is left out
#: by the producer, never guessed, and a grind is not a method. Part of the contract:
#: a test holds this tuple and the schema's enum to each other, and ``check`` refuses
#: a method outside it rather than passing it through.
BREWING_METHODS: tuple[str, ...] = (
    "espresso",
    "moka",
    "filter",
    "french_press",
    "aeropress",
    "turkish",
    "automatic",
    "cold_brew",
)

#: The most points a coffee's ``price_history`` carries. Enforced by
#: ``coffee.state.v1.json`` as ``maxItems``, so a producer that sends more is
#: refused by ``check`` rather than trimmed on its behalf.
MAX_PRICE_HISTORY = 50


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One change in a coffee's price, not one day of it.

    A point is emitted only where ``(price_per_kg_eur_cents, available)`` differs from
    the day before, so a coffee priced the same for a year is one point. The
    last point of a series holds until the coffee's ``observed_at``, which is
    what tells a price that has not moved since a date apart from a crawl that
    stopped on that date.

    Attributes:
        on: The first day these values held.
        price_per_kg_eur_cents: The comparable price per kilogram from that day, in euro
            cents, as ``CoffeeState.price_per_kg_eur_cents`` counts it; None when unpriced.
        available: Whether the shop said it was in stock that day; None when it said nothing.
    """

    on: date
    price_per_kg_eur_cents: int | None
    available: bool | None


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
        altitude_min_m: The lower end of the stated altitude, in metres. ``altitude_max_m`` is
            the upper end.
        flavor_notes: Cup notes, as the shop wrote them.
        tasting_text: The shop's prose description of the cup.
        sca_score: The cupping score, when published.
        weight_g: The net weight the price buys.
        price_minor: The price of that package, as a count of the minor unit of
            ``currency``: 34900 is 349.00 when ``currency`` is CZK. None when unpriced.
        currency: The ISO 4217 code of the currency ``price_minor`` is counted in.
        price_per_kg_eur_cents: The comparable price per kilogram, in euro cents:
            2450 is 24.50 EUR per kilogram. None when the shop gives no comparable price.
        available: Whether the shop says it is in stock.
        delisted_at: When the shop stopped listing it; None while it is sold.
        first_seen_at: When this catalogue first saw it, not its release date; None if unrecorded.
        decaf: True if the shop says decaf, False if caffeinated, None if it said nothing.
        images: The shop's own picture URLs, in the order the page lists them; empty
            when it published none.
        price_history: The price changes, oldest first, one ``PricePoint`` per change.
            Capped at ``MAX_PRICE_HISTORY`` points, oldest dropped first. The cap
            loses no fact about when the coffee started, which ``first_seen_at`` keeps.
            Empty when the producer recorded no series.
        pack_group_key: Opaque, compared for equality only: two listings of one shop share
            it when they are the same coffee in different pack sizes. Not a key across
            shops. None when the producer could not derive one.
        description: The shop's own prose about the coffee, with text the shop repeats across
            many of its coffees (nutrition tables, FAQs, packaging) already removed by the
            producer. It is the shop's text, not ours. None, not an empty string, when there
            is none.
        origin_farm: The farm, as the shop names it, free text. None, not an empty string,
            when it names none.
        origin_producer: The producer, as the shop names it, free text. None, not an empty
            string, when it names none.
        origin_washing_station: The washing station, as the shop names it, free text. None,
            not an empty string, when it names none.
        altitude_max_m: The upper end of the stated altitude in metres. Equal to
            ``altitude_min_m`` when the shop states a single height. None when the shop
            states none. Not checked against ``altitude_min_m`` or for sign.
        body: The body the shop states, on a 0 to 5 scale. A producer that reads a score
            stated on another scale rescales it before sending, so the contract carries no
            scale. 0 is a stated score, the lowest. None when the shop states none.
            ``3.0`` passes ``check`` as an integer and is read back as a float.
        acidity: The acidity the shop states, on the same 0 to 5 scale as ``body``. None
            when the shop states none.
        sweetness: The sweetness the shop states, on the same 0 to 5 scale as ``body``.
            None when the shop states none.
        bitterness: The bitterness the shop states, on the same 0 to 5 scale as ``body``.
            None when the shop states none.
        brewing_methods: The methods the shop says the coffee suits, from
            ``BREWING_METHODS``. Each appears at most once and the order carries no
            meaning. Empty when the shop names none; a producer sends ``[]``, never None,
            because ``check`` refuses null.
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
    price_minor: int | None = None
    currency: str | None = None
    price_per_kg_eur_cents: int | None = None
    available: bool | None = None
    delisted_at: datetime | None = None
    first_seen_at: datetime | None = None
    decaf: bool | None = None
    images: list[str] = field(default_factory=list)
    price_history: list[PricePoint] = field(default_factory=list)
    pack_group_key: str | None = None
    description: str | None = None
    origin_farm: str | None = None
    origin_producer: str | None = None
    origin_washing_station: str | None = None
    altitude_max_m: int | None = None
    body: int | None = None
    acidity: int | None = None
    sweetness: int | None = None
    bitterness: int | None = None
    brewing_methods: list[str] = field(default_factory=list)

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
    make every additive change a breaking one. The money fields in
    ``MONEY_FIELDS`` must be whole numbers, and are refused otherwise, because a
    fractional or float-spelled price read as-is would be a price nobody sent.

    Args:
        raw: The message body.

    Returns:
        The event, with each money field an ``int`` or None.

    Raises:
        ValueError: When a money field is not an integer, such as ``2450.0`` or
            ``24.5``, or when a timestamp cannot be parsed.
    """
    return _build(CoffeeState, json.loads(raw))


def _encode(value: object) -> str:
    """Return the wire text of a value the ``json`` module cannot write itself.

    Datetimes and dates are ISO 8601, so ``date`` is written the way ``datetime``
    already is.

    Args:
        value: The object ``json.dumps`` could not serialise.

    Returns:
        The string that goes on the wire in its place.

    Raises:
        TypeError: When the value is not one the contract carries.
    """
    if isinstance(value, datetime | date):
        return value.isoformat()
    message = f"{type(value).__name__} is not part of the contract"
    raise TypeError(message)


def _build(cls: type[CoffeeState], payload: dict[str, Any]) -> CoffeeState:
    fields = {f.name for f in cls.__dataclass_fields__.values()}
    known = {k: v for k, v in payload.items() if k in fields}
    for name in ("observed_at", "delisted_at", "first_seen_at"):
        if isinstance(known.get(name), str):
            known[name] = datetime.fromisoformat(known[name])
    for name in MONEY_FIELDS:
        value = known.get(name)
        if value is not None and type(value) is not int:
            message = f"{name} must be a whole number of minor units, got {value!r}"
            raise ValueError(message)
    if "price_history" in known:
        known["price_history"] = [_point(item) for item in known["price_history"]]
    return cls(**known)


def _point(payload: dict[str, Any]) -> PricePoint:
    """Build one ``PricePoint`` off the wire, refusing a float price as ``_build`` does.

    Args:
        payload: One element of ``price_history``, as the JSON decoded it.

    Returns:
        The point, with ``on`` as a ``date``.

    Raises:
        ValueError: When ``price_per_kg_eur_cents`` is not a whole number, or the
            date cannot be parsed.
    """
    cents = payload["price_per_kg_eur_cents"]
    if cents is not None and type(cents) is not int:
        message = f"price_per_kg_eur_cents must be a whole number of cents, got {cents!r}"
        raise ValueError(message)
    return PricePoint(
        on=date.fromisoformat(payload["on"]),
        price_per_kg_eur_cents=cents,
        available=payload["available"],
    )
