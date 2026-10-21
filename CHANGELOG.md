# Changelog

Consumers pin a tag, so the only way to find out what a bump costs is to read
it here. Each entry says what a consumer has to do, not what the diff touched.

The version here is the *distribution's*. The wire version lives in `VERSION`
in `subjects.py` and moves only when a subject changes — it was `v1`
until 3.0.0 and is `v2` from there.

## 3.2.4 (untagged)

Wire version `v2`, unchanged. A price point gains three optional fields and the
rule for when a point starts changes. Nothing that was valid at `v3.2.0` is
refused now, and a consumer that does not read `price_history` has nothing to do.

- **New fields on a point.** `PricePoint` gains `price_minor`, `currency` and
  `weight_g`, after `available`, each defaulting to None. They mean what the
  `CoffeeState` fields of the same names mean, on the point's first day: the
  shop's own price of the package as a count of the minor unit of `currency`,
  its ISO 4217 code, and the net weight that price buys. None, null and absent
  all mean unknown. In the schema they are optional properties of the open
  `price_history.items` object, with `required` unchanged
  (`on`, `price_per_kg_eur_cents`, `available`) and no `pattern` or `minimum`,
  like the top-level fields of the same names.
- **The point rule.** A point now starts on a day when the shop's own price
  (`price_minor`, `currency`), weight (`weight_g`) or availability differs from
  the day before. A change in `price_per_kg_eur_cents` alone no longer starts
  one. A CZK price is converted at each day's ČNB rate, so the euro-per-kilogram
  figure moves almost daily while the shop's price stands still, and a point per
  move would fill the 50-point cap with a coffee whose shelf price never changed.
- **What the EUR/kg figure on a point is.** It is the figure on the point's
  first day (`on`). It may stand across the whole life of the point while the
  real converted figure drifts, so it is not what the coffee cost in euros on
  a later day inside that point; the shop's price is `price_minor` and
  `currency`.
- **What `check` accepts and refuses.** Two consecutive points are a repeat,
  refused with "a point is a change, not a day", only when every value they carry
  is equal: `price_per_kg_eur_cents`, `available`, `price_minor`, `currency` and
  `weight_g`, an absent key counting as null. So `check` now accepts consecutive
  points equal in euro-per-kilogram when the shop's price, weight or currency
  differs, and refuses nothing it accepted at `v3.2.0`: a series of three-key
  points reads and validates as before, with the new fields None. Each point's
  `price_minor` must be a JSON integer, as its `price_per_kg_eur_cents` already
  is, so `2450.0` is refused by `check` and by `coffee_from_json`. Dates still
  ascend strictly, the last point is still not after `observed_at`, and a series
  is still at most `MAX_PRICE_HISTORY` (50) points.
- **Who could observe it.** The only producer, `coffee-aggregator`, sends
  `price_history: []` today (`jsonb_build_array()` in `sinks/outbox.py` on its
  `main`; coffee-web#226), so no series on the wire has the old rule's shape or
  the new one's. A consumer has to do nothing unless it reads the series; one
  that decodes points keeping only the fields it knows ignores the new keys.

## 3.2.3 (untagged)

Wire version `v2`, unchanged. Nothing in the package and nothing on the wire
changed: this edits `tests/test_contract_compatibility.py` only, so a consumer
has nothing to do.

The compatibility check against the last release now applies one rule at every
depth instead of at the top level only. Inside any object, including the
`items` of an array such as `price_history`:

- a released property may not be removed or constrain a payload differently,
  and no property may become required;
- a new property that is not required is additive, but only in an object that
  was open at the tag (`additionalProperties` absent or `true`) and is still
  open;
- everything else in the object stays frozen: closing it, retyping `items`, a
  changed `type`, `enum`, `pattern`, `minimum` or `maxItems`.

The root schema is held to the same rule, so its own keywords (`$id`, `type`,
`allOf`) are now compared as well, where only its `properties` and `required`
were before. An object that omits `additionalProperties` is read as one that
says `true`.

Until now the whole `price_history` subschema was compared as one value, so
adding an optional property to its items failed the check as a change to
`price_history`, although no consumer that keeps the fields it knows could
notice it. A failure now names its path, for example
`price_history.items.price_minor newly required`.

## 3.2.2 (untagged)

Wire version `v2`, unchanged. This adds five optional fields to `coffee.state`
and changes nothing that already exists, so a consumer that does not read them
can take them without touching code.

- `body`, `acidity`, `sweetness` and `bitterness` are the shop's stated
  intensity of each, as a whole number from 0 to 5, **always on that scale**. A
  producer that reads a score stated on another scale rescales it before
  sending, so there is no scale field and a consumer never has to ask which one
  it got. `0` is a stated score, the lowest, and is not "none"; a missing field
  and a `null` one mean the shop states no score. A consumer that treats `0` as
  falsy will drop real scores.
- `brewing_methods` is the list of methods the shop says the coffee suits, from
  a closed vocabulary exported as `BREWING_METHODS`: `espresso`, `moka`,
  `filter`, `french_press`, `aeropress`, `turkish`, `automatic`, `cold_brew`.
  The list is closed: **`check` refuses a method outside it**, so a producer
  leaves out what it cannot map instead of guessing, and a grind is not a
  method. Each method appears at most once (`uniqueItems`), so `check` also
  refuses a repeat, and the order carries no meaning. An empty list, or a
  missing field, means the shop names none; `CoffeeState` reads it back as `[]`.

**`check` refuses a score outside 0 to 5, or one that is not a whole number**
(`2.5`, `"3"`, `true`). Like `altitude_max_m`, a score of `3.0` passes `check` as
JSON Schema's `integer` and `coffee_from_json` reads it back as the float `3.0`.
A producer sends `[]`, never `null`, for `brewing_methods`: `check` refuses
`null`, although `coffee_from_json` would read it as `None`. Neither the
dataclass nor `coffee_from_json` validates any of this, as they do not validate
`product_kind` or `arabica_pct`: only `check` does, so a producer must call it
before publishing. The constraints on
`brewing_methods` can be added only now, before it is first tagged; after a
tag, narrowing them would need a new wire version.

**A coffee that has not been republished keeps the message it was published
with.** The stream keeps one message per coffee, so until the producer
publishes that coffee again, its message has none of the five fields.

This is untagged. No `v3.2.2` tag will be cut, so do not look for one. The
release pull request sets the number and cuts the tag.

**What a consumer has to do:** nothing to its code, unless it wants the fields.
Treat absent and `null` alike for the scores, read `0` as a score and not as
missing, and treat an absent `brewing_methods` like `[]`. Do not expect a method
outside the closed list: `check` refuses it, so it never arrives. Three
consumers read `CoffeeState` as a whole, and one does not:

- `coffee-aggregator`: its outbox selects every `CoffeeState` field as a column
  of its `coffee` table (`STATE_FIELDS`, `_EXPRESSION_FOR` in
  `sinks/outbox.py`), and `tests/test_outbox.py::test_every_state_expression_reads_a_column_the_coffee_table_has`
  fails on the pin move until each of the five names has a column or an
  `_EXPRESSION_FOR` entry. `brewing_methods` also goes in `_LIST_FIELDS`, so a
  null column reads back as `[]`.
- `coffee-api` (`tests/test_contract_fields.py`) and `coffee-cupper`
  (`tests/test_migrate.py`) compare `dataclasses.fields(CoffeeState)` with their
  stored columns, and fail that check until they store the five names or name
  them as not stored.
- `coffee-broker` is unaffected: it takes streams and subjects from the
  contract and never reads `CoffeeState`.

## 3.2.1 (untagged)

Wire version `v2`, unchanged. This adds five optional fields to `coffee.state`
and changes nothing that already exists, so a consumer that does not read them
can take them without touching code.

- `description` is the shop's own prose about the coffee, with text the shop
  repeats across many of its coffees (nutrition tables, FAQs, packaging) already
  removed by the producer. It is the shop's text, not ours.
- `origin_farm`, `origin_producer` and `origin_washing_station` are the farm,
  the producer and the washing station, each as the shop names it, free text.
- `altitude_max_m` is the upper end of the stated altitude in metres, beside
  the existing `altitude_min_m`. It equals `altitude_min_m` when the shop states
  a single height.

Every one is a string (the altitude an integer) or `null`, with no further
constraint. A missing field and a `null` one mean the same thing: the shop
stated none, or the producer could not extract it. A producer sends `null`, not
an empty string, for "none", but the contract does not refuse `""`, so a
consumer that displays these should treat an empty string like `null`.

**The contract does not check the altitude.** It does not enforce
`altitude_min_m <= altitude_max_m` and does not require either to be positive,
so a consumer that draws a range must not assume the order. Like
`altitude_min_m`, `altitude_max_m` accepts `2000.0` as an integer, as JSON
Schema's `integer` does. No `minimum`, `minLength` or `maxLength` was added,
because a constraint on a released property is frozen by the compatibility test.

**A coffee that has not been republished keeps the message it was published
with.** The stream keeps one message per coffee, so until the producer
publishes that coffee again, its message has none of the five fields.

This is untagged. No `v3.2.1` tag will be cut, so do not look for one. The
release pull request sets the number and cuts the tag.

**What a consumer has to do:** nothing to its code, unless it wants the fields,
and then treat absent and `null` alike. A consumer that checks the contract's
fields against what it stores fails that check on the pin move until it stores
the five or names them as not stored. Today that is `coffee-api`
(`tests/test_contract_fields.py`) and `coffee-cupper` (`tests/test_migrate.py`),
which compare `dataclasses.fields(CoffeeState)` with their stored columns.

## 3.2.0 (2026-10-20)

**This release is the untagged `3.1.1` and `3.1.2` below, read together.**
`v3.2.0` is the first tag a consumer can pin that carries `pack_group_key`. No
`v3.1.1` or `v3.1.2` tag exists and none will be cut.

Wire version `v2`, unchanged: no subject, stream or existing property moved.
`3.1.1` changed nothing on the wire, and `3.1.2` added one optional field to
`coffee.state`.

### What changed

- **`coffee.state` carries an optional `pack_group_key`.** It marks two listings
  of one shop as the same coffee in different pack sizes: they share the value
  exactly when the producer judges them so. It is opaque and compared for
  equality only, it is not a key across shops, and it has to be percent-encoded
  before it goes in a URL. Absent and `null` mean the same thing, no key; the
  empty string is refused. A coffee the producer has not republished yet has no
  `pack_group_key` in its message. The `3.1.2` entry below has the detail.
- **Repository housekeeping from `3.1.1`**: the session wiring is tracked so it
  reaches every worktree. Nothing in the package changed.

### Why a minor and not a major

Nobody was reading anything that changed. `coffee-api`, `coffee-aggregator`
and `coffee-cupper` are pinned to `v3.1.0` on their `main`, and `coffee-broker`
requires `coffee-contracts>=3.1.0` against a sibling checkout. `required` on
`coffee.state` did not change and the new property is optional and nullable, so
a message without it still validates and a consumer that never reads it behaves
as it did at `v3.1.0` at runtime. The compatibility test against `v3.1.0`
passes. An additive optional field breaks nobody pinned there, and a major is
worth little spent on a change nobody could observe.

**What a consumer has to do:** nothing to its code, unless it wants the field
or checks the contract's fields against what it stores. A consumer that does
the second fails that check on the pin move until it stores `pack_group_key` or
names it as not stored. Today that is `coffee-api`
(`tests/test_contract_fields.py`) and `coffee-cupper` (`tests/test_migrate.py`),
which compare `dataclasses.fields(CoffeeState)` with their stored columns and
mention `pack_group_key` nowhere yet. To read the field, pin `v3.2.0`, treat
absent and `null` alike, and percent-encode the value before it goes in a URL.

The entries for `3.1.2` and `3.1.1` below stay untagged. They are the record of
each pull request, and this release does not replace them.

## 3.1.2 (untagged)

Wire version `v2`, unchanged. This adds one optional field to `coffee.state`
and changes nothing that already exists, so a consumer that does not read it
can take it without touching code.

- `pack_group_key` lets a consumer tell that two listings are the same coffee
  from the same shop in a different pack size: they carry the same value
  exactly when the producer judges them so. It is a string, at least one
  character, or `null`. Its use is to leave a coffee's other pack sizes out of
  a "similar coffees" section.

**It is opaque.** Compare it for equality and nothing else: never parse it,
order it or rely on its shape. It is not a key for the same coffee across
shops, and two shops' listings of one coffee carry different values. A key for
that is a later, separate field.

Today a value looks like `<site>/<folded name>`, optionally followed by
`~espresso` or `~filter`, for example `fathers/uganda zebigi~espresso`, and the
longest seen is about 132 characters. That is an illustration, not a promise.
It contains spaces, `/`, `~` and non-ASCII characters, so percent-encode it
whenever it goes in a URL.

A missing `pack_group_key` and a `null` one mean the same thing: the producer
could not derive a key. The empty string is refused, because under equality it
would make every keyless coffee in a shop the same coffee. The rule that
produced the key is not on the wire.

**A coffee that has not been republished keeps the message it was published
with.** The stream keeps one message per coffee, so until the producer
publishes that coffee again, its message has no `pack_group_key`.

This is untagged. No `v3.1.2` tag will be cut, so do not look for one. The
release pull request sets the number and cuts the tag.

**What a consumer has to do:** nothing, unless it wants the field. A consumer
that reads it treats absent and `null` alike, and percent-encodes the value
before it goes in a URL.

## 3.1.1 (untagged)

Nothing in the contract changed. This is repository housekeeping: the session
wiring that Claude Code uses in this checkout is now committed, so it reaches
every git worktree. Before, a worktree had only tracked files, so an agent
working in one got no SessionStart hook and none of the team's learnings.

- `.trail/` is tracked: the SessionStart hook (`hook.cjs`), its README, and a
  `.gitignore` that keeps per-machine state out of git.
- `.claude/settings.json` is tracked and registers that hook.
- `.gitignore` no longer ignores all of `.claude/`. It ignores
  `.claude/settings.local.json` and `.claude/worktrees/`.

The wire version is still `v2`, and no subject, schema or payload moved.

**What a consumer has to do:** nothing. This is untagged. No `v3.1.1` tag will be
cut, so do not look for one. The release pull request decides the next number
and cuts the tag.

## 3.1.0 (2026-10-15)

**This release is the untagged `3.0.1` and `3.0.2` below, read together.** It is
the first tag a consumer can pin that names the v2 streams correctly.

Nothing on the wire has changed since 3.0.0: `VERSION` is still `v2`, and every
subject, schema and payload is what 3.0.0 shipped.

### What changed

- **The streams are `CATALOGUE_V2` and `EMBEDDINGS_V2`**, derived from `VERSION`
  rather than written out, so a future wire version carries its stream names
  with it. A consumer binds by `CATALOGUE.name` and so follows this without
  touching code.
- **The side-by-side migration path 3.0.0 described is not available in this
  deployment.** There is one producer, pinned to one contract version. A
  coordinated cutover replaced it: `coffee-broker` provisions the v2 streams,
  then `coffee-api` moves, then `coffee-cupper`, then `coffee-aggregator` last
  because it is the producer, and `coffee-web` follows the API.

### Why a minor and not a major

Nothing is pinned to `v3.0.0`. `coffee-api` and `coffee-aggregator` are on
`v2.5.0`, `coffee-cupper` on `v2.4.0`. No consumer could ever have observed the
stream name 3.0.0 shipped, so renaming it breaks nothing anybody could see. A
major is the loudest thing a version can say and it is worth very little spent
on a change nobody could observe.

### `v3.0.0` is a tag nobody should pin

It is the only tagged release that names the v2 streams `CATALOGUE` and
`EMBEDDINGS`, so a consumer pinning it provisions a broker that converts the
running v1 streams in place rather than standing new ones beside them. Someone
reading the tag list a year from now will see `v3.0.0` looking like the v2
release with nothing to warn them. This is that warning.

The `3.0.1` entry below says a consumer already pinned to `v3.0.0` has nothing
to do. That was written before the stream-name defect was known, and this
release supersedes it: there is something to do, and it is to pin `v3.1.0`.

**What a consumer has to do:** pin `v3.1.0`. If it is moving from a 2.x pin,
everything 3.0.0's "What breaks" section says still applies — the money fields
renamed and retyped, the wire version at `v2` — and that is the real work. This
release does not change it.

The entries for `3.0.1` and `3.0.2` below stay untagged. They are the record of
each pull request, and this release does not replace them.

## 3.0.2 (untagged)

**The streams are now named `CATALOGUE_V2` and `EMBEDDINGS_V2`.** 3.0.0 moved
the wire version to `v2` and versioned the subjects, but left both stream names
exactly where they were — so the contract described the live v1 streams under
their own names while asking for v2 subjects. `coffee-broker` creates and looks
a stream up by name, so provisioning that contract did not stand the v2 streams
up beside the v1 pair: it converted the running pair in place, and from that
moment every v1 publish by `coffee-aggregator` would have failed its ack until
the aggregator itself moved.

The name is now derived from `VERSION` rather than spelled out, because a
literal is precisely what stood still while the subjects moved. A future wire
version carries its stream names with it.

Nothing on the wire changed: `VERSION` is still `v2`, and every subject, schema
and payload is what 3.0.0 shipped. The streams' compaction, retention and
descriptions are unchanged too, so the v2 pair is provisioned with the same
configuration as the v1 pair it now sits beside.

**What a consumer has to do:** nothing beyond moving its pin. `coffee-api` and
`coffee-cupper` already bind with `CATALOGUE.name`, so the new name reaches them
with the release that carries it. **What the broker does:** creates two streams
beside the v1 pair instead of rewriting them, which is what lets v1 keep serving
through the cutover.

Untagged, per the release rule: the release that follows sets the number
consumers pin.

## 3.0.1 (untagged)

A correction to the 3.0.0 notes. Nothing on the wire changed and nothing in the
package changed: the wire version is still `v2`, every subject and every schema
is what 3.0.0 shipped, and a consumer already pinned to `v3.0.0` has nothing to
do.

**The side-by-side migration path is not available in this deployment.** The
"Migrating" section of 3.0.0 says `coffee.v1.…` and `coffee.v2.…` can both run
until the last consumer has moved. That is true of the subjects and false of
this project, because there is one producer and a package is pinned to one
version: `coffee-aggregator` builds its subjects from the contract it has
installed, so it publishes `v1` or `v2` and never both. Running both would mean
two contract versions in one virtualenv. The sentence describes a path for
consumers operated independently of one another; these are four services on one
box behind one crawl.

**What replaced it was a coordinated cutover**, in this order: `coffee-broker`
provisions the v2 streams, then `coffee-api` moves, then `coffee-cupper`, then
`coffee-aggregator` last because it is the producer. `coffee-web` follows the
API.

**What that costs.** Between the first step and the last the v2 stream is empty
and nothing consumes v1 any more. The catalogue stream is compacted, so one
crawl after the aggregator moves restores it in full, and the site serves stored
rows throughout. The cost is staleness for one crawl cycle, not an outage.

A future wire version is migrated the same way, by a coordinated cutover;
dual-publishing is not something `coffee-aggregator` is expected to learn.

The 3.0.0 entry is left exactly as it was written, because a tagged release's
notes are a record of what was said at the time.

## 3.0.0 (2026-10-12)

**Breaking: every consumer has to change its code.** This release is the
untagged `2.5.1` and `2.5.2` below, read together. The money fields are renamed
and retyped, and the wire version moves to `v2`. Consumers pin `v3.0.0` only
once they have moved.

### What breaks

- Money is an integer count of the currency's minor unit, not a float in
  currency units. The two fields are renamed, and the old names are removed
  rather than deprecated:
  - `price` (float) is now `price_minor` (int). `349.00` Kč or EUR is `34900`.
    Null when unpriced.
  - `price_per_kg_eur` (float) is now `price_per_kg_eur_cents` (int), in euro
    cents per kilogram. `24.50` EUR/kg is `2450`. Null when there is no
    comparable price.
  - A consumer that still reads `price` finds no such field and fails loudly.
    It does not render a price a hundred times too large.
  - A money value that is not a whole number is refused. `check` refuses `24.5`
    and `2450.0`, and the reader raises on them.
- The wire version is `v2`. Subjects are `coffee.v2.catalogue.…` and
  `coffee.v2.embedding.…`, and the schema is `coffee.state.v2.json`.

### Migrating

`coffee.v1.…` and `coffee.v2.…` are separate subjects, so both streams can run
until every consumer has moved. A producer pinned to `2.5.x` keeps publishing
`v1`, and a producer on `3.0.0` publishes `v2`. A consumer subscribes to one
stream or the other, so it moves to `v2` and the renamed fields when it is
ready. Nothing is re-published across the two streams.

### What is added

- `price_history` is the coffee's price changes, oldest first. Each point is a
  `PricePoint`, `{on, price_per_kg_eur_cents, available}`, with one point per
  change rather than one per day. It is optional: a missing field and an empty
  list mean the same thing. It is the first nested type in the contract.
- `MAX_PRICE_HISTORY` is `50`. A producer trims the oldest points before it
  sends, and `check` refuses a longer series.
- The Python package exports `PricePoint` and `MAX_PRICE_HISTORY`.

### Who has to move

Each is its own pull request in its own repository:

- coffee-aggregator writes both money fields and publishes to `v2`.
- coffee-api stores both money fields and subscribes to `v2`.
- coffee-web renders both money fields.
- coffee-cupper reads both money fields for retrieval and subscribes to `v2`.

The entries for `2.5.1` and `2.5.2` below stay untagged. They are the record of
each pull request, and this release does not replace them.

## 2.5.2 (untagged)

Wire version `v2`, unchanged. This adds one optional field to `coffee.state`
and changes nothing that already exists, so a consumer that does not read it
can take it without touching code.

- `price_history` is the coffee's price changes, oldest first: one point per
  change, where a point is `{on, price_per_kg_eur_cents, available}`. `on` is a
  date string, `price_per_kg_eur_cents` an integer or null, and `available` a
  boolean or null. It is the first nested type in the contract. A float spelling
  of a whole number, such as `2450.0`, is refused at the point as it is at the
  top level. The series is capped at 50 points, and a producer trims the oldest
  before sending: a longer series is refused by `check`. `first_seen_at` still
  says when the coffee appeared.
- The Python package exports `PricePoint` and `MAX_PRICE_HISTORY`.

A missing `price_history` and an empty one mean the same thing: the producer has
not recorded a series. Untagged, per the release rule: the release that tags
this sets the semantic version.

## 2.5.1 (untagged)

**Breaking wire change: the wire version moves to `v2`.** Subjects are now
`coffee.v2.catalogue.…` and `coffee.v2.embedding.…`, and `coffee.v1.…` is no
longer published by this contract. Consumers that stay on `2.5.0` keep reading
`v1` and nothing they subscribe to is removed. Nothing is re-published for them.
The schema is `coffee.state.v2.json`, and `coffee.embedding.v1.json` is
unchanged.

`VERSION` is one value for the whole contract, so `coffee.embedding` moves to
`coffee.v2.embedding` as well, though its schema and content did not change.
Consumers of embeddings re-subscribe for that alone.

This is untagged. No `v2.5.1` tag will be cut, so do not look for one. The
release pull request decides the distribution number (`3.0.0` is expected)
and cuts the tag.

Money is an integer count of a minor unit, and the float fields are gone.
Renamed, not retyped, so an unmoved consumer fails on the missing field rather
than reading a cents value as euros:

- `price` (float) is now `price_minor` (int): a count of the minor unit of
  `currency`, so `34900` is 349.00 CZK or EUR. Null when unpriced.
- `price_per_kg_eur` (float) is now `price_per_kg_eur_cents` (int): euro cents
  per kilogram, so `2450` is 24.50 EUR/kg. Null when there is no comparable price.

A money field that is not a whole number is refused. `check` refuses `24.5` and
`2450.0`, and the reader raises on them rather than truncating or returning a
float.

Consumers that must move to `v2` and to the new fields before this is released:

- coffee-aggregator writes both fields and publishes to `v2`.
- coffee-api stores both fields and subscribes to `v2`.
- coffee-web renders both fields.
- coffee-cupper reads both fields for retrieval and subscribes to `v2`.

## 2.5.0

Wire version `v1`, unchanged. This adds one optional field to `coffee.state`
and changes nothing that already exists, so a consumer that does not read it
can bump its pin without touching code. A consumer that wants it has to read
the field below.

This tags the two untagged patches before it. `2.4.1` changed CI only, and
`2.4.2` added the field. No `v2.4.1` or `v2.4.2` tag will be cut, so `v2.5.0`
is the first tag that carries either.

- `images` is the shop's own picture URLs, in the order the page lists them. It
  is a list of strings, and an empty list when the shop published none. It is
  the shop's URLs, not copies: nothing here downloads or re-serves a picture.

A missing `images` and an empty one mean the same thing: the producer has not
recorded any.

## 2.4.2 (untagged)

Wire version `v1`, unchanged. This adds one optional field to `coffee.state`
and changes nothing that already exists, so a consumer that does not read it
can take it without touching code.

- `images` is the shop's own picture URLs, in the order the page lists them. It
  is a list of strings, and an empty list when the shop published none. It is
  the shop's URLs, not copies: nothing here downloads or re-serves a picture.

A missing `images` and an empty one mean the same thing: the producer has not
recorded any. Untagged, per the release rule: the release that tags this sets
the semantic version.

## 2.4.1

Wire version `v1`, unchanged, and the package code is unchanged. Nothing for a consumer
to do.

This changes CI only. A pull request now fails unless it moves `version`, adds its entry
here, and makes the version greater than the one on `main`, so every merged change has a
number and a line.

## 2.4.0

Wire version `v1`, unchanged. This adds two optional fields to `coffee.state`
and changes nothing that already exists, so a consumer that reads neither can
take it without touching code. A consumer that wants them has to do the steps
below.

- `first_seen_at` is when this catalogue first saw the coffee, not when the
  roaster released it. It is a date-time string.
- `decaf` is whether the shop says the coffee is decaffeinated. It is `true`,
  `false`, or `null` when the shop said nothing.

Both are optional and nullable, and `required` is unchanged. A missing field
and a `null` one mean the same thing: the producer has not recorded it.

**Absence is not false.** To select caffeinated coffee, filter for `false`.
Filtering for "not `true`" also selects every coffee whose shop said nothing.

**`first_seen_at` is not new coffee.** Adding a shop gives its whole catalogue
the same value at once, and a shop that changes its product ids makes every row
look new. A new-arrivals view built on it has to cap a shop's first crawl or
leave that shop out.

**A coffee that does not change keeps the message it was published with.** The
stream keeps one message per coffee, so until the producer publishes that coffee
again, its message has neither field.

## 2.3.0

Wire version `v1`, unchanged. This adds four optional fields to `coffee.state`
and changes nothing that already exists, so a consumer that reads none of them
can take it without touching code. A consumer that wants them has to do the
steps below.

- `product_kind` is an enum of 16 values: 15 named kinds, `beans`, `capsules`,
  `instant`, `green`, `ready_to_drink`, `sampler`, `kit`, `equipment`, `merch`,
  `food`, `service`, `cosmetics`, `not_a_product`, `other_drink` and `test`,
  plus `other`. The same list is exported as `PRODUCT_KINDS`, in the schema's
  order.
- `product_kind_source` is a free string that says how the kind was decided.
- `arabica_pct` and `robusta_pct` are integers from 0 to 100: the species split
  the shop states.

All four are optional and nullable, and `required` is unchanged. `check`
refuses a kind outside the list and a percentage outside 0 to 100.

**A missing `product_kind` is not `beans`.** Absent and `null` both mean the
producer has not decided. A consumer that reads an undecided product as coffee
goes back to embedding paper cups the first time a shop it has not seen before
sells one, which is the bug coffee-cupper#26 exists to fix. Absence is not an
assertion of coffee, and an undecided product is not beans.

**Why `product_kind` is an enum and `product_kind_source` is not.** A kind means
something only against an agreed vocabulary, so a value outside it fails
validation rather than passing through as an unknown string. A vocabulary change
shows up as a validation failure, not as quietly dropped rows. The embedding
schema pins its `model` for the same reason. The source is free text because it
records how the decision was made, and that is a sentence.

**Undecided and `other` are different answers.** Absent or `null` means the
producer has not decided yet. `other` means it has decided, and the product is
none of the named kinds. Both are "not one of the named kinds" to a filter, but
only `other` is a decision. Treating them the same throws away the distinction
the field exists to carry.

The list is frozen for `v1`. Adding a named kind later changes what the
property constrains, so it needs a new wire version, as any other edit to an
enum does. `other` exists so that the first product nobody named does not cost
one. It is a known value, not a free string: an unknown string is still
refused. Promoting a product from `other` to its own kind later is a wire
change, and nothing is blocked while it waits.

- `to_json` writes `null` for a field the producer has not decided, as it does
  for every optional field. The schema accepts absent and `null` alike.
- `arabica_pct` and `robusta_pct` are the shop's own statement. `null` means the
  shop said nothing; `0` asserts that the coffee has none of that species.
- `is_blend` is not part of this release. The aggregator still stores it wrongly
  for some blends (coffee-aggregator#84), and a field known to be wrong is worse
  than no field.
- A consumer that uses none of the four can ignore them all. One that uses the
  kind alone can ignore `product_kind_source` and both percentages.

## 2.2.0

Wire version `v1`, unchanged. This release adds an event type and changes
nothing that already exists, so a consumer that neither reads embeddings nor
provisions its streams from `STREAMS` can take it without touching code. Any
other consumer has to do the steps below.

- New event `coffee.embedding` on the subject
  `coffee.v1.embedding.<site>.<external_id>`, carried in the new stream
  `EMBEDDINGS`. The stream keeps one message per coffee: a new vector replaces
  the old one, so replaying it once yields every current vector exactly once.
- The vector is 768 `float32` values from `intfloat/multilingual-e5-base`, sent
  as standard base64 of their raw little-endian bytes. The schema pins `model`,
  `dimension` and `dtype` as `const`, on purpose: a vector only means something
  relative to the model that produced it. Moving to a different model, even
  another 768-dimension one, is a **breaking change**, not a configuration
  tweak. It is a new wire version, never an edit to this schema, and the
  `const` makes a swap a visible failure at validation rather than a silent
  mix of incomparable vectors.
- A schema cannot say how many bytes a base64 string decodes to, so a consumer
  must check that the decoded vector is `dimension` times the dtype's size in
  bytes. `check()` does this for `coffee.embedding` payloads; a consumer that
  reads `vector` without it gets no guarantee that the vector is whole.
- `STREAMS` now holds two streams. Anything that creates every entry of
  `STREAMS` also creates `EMBEDDINGS`; anything that names `CATALOGUE` directly
  is unaffected.
- New exports: `COFFEE_EMBEDDING`, `EMBEDDINGS` and `embedding`. Nothing
  exported in 2.1.0 was removed or renamed.
- `coffee.state`, its schema, the catalogue subject and `catalogue()` are
  unchanged.

## 2.1.0

Wire version `v1`, unchanged. Nothing in the schemas moved; a consumer can take
this release without reading further.

- The package ships a PEP 561 `py.typed` marker, so a consumer's type checker
  reads the annotations instead of treating every `CoffeeState` field as `Any`.
  Both Python consumers can drop their `follow_untyped_imports` override for
  `coffee_contracts` once they pin this release.
- The compatibility check compares whole subschemas rather than a property's
  top-level `type`, so an `enum`, `const`, `pattern`, `minLength`, `minimum` or
  retyped `items` can no longer be added to a released property unnoticed.
- Deleting an event type is refused while the wire version stays the same. It
  was not before: `crawl.finished.v1.json` went in 2.0.0 and the suite stayed
  green.
- A checkout that cannot read the release tag fails under CI instead of
  skipping. A skip exits 0, which is the same as having no check.

## 2.0.0

Wire version `v1`, unchanged — but this release removes an event type, so a
consumer switching on it has to be changed before taking it.

- `crawl.finished` is gone, schema and dataclass. `crawl_run` in the aggregator
  already held every counter and no consumer read the event.
- `check` enforces `date-time` with the same parser `coffee_from_json` uses, so
  a timestamp it accepts is one the consumer can parse.
- `check` builds its validator once per event type, which is what makes
  validating a whole replay affordable.
- CI diffs every schema against the newest release tag reachable from the
  branch and refuses a breaking edit unless `VERSION` changed.

## 1.0.0

The first contract: `coffee.state` and `crawl.finished`, their JSON Schemas,
the `coffee.v1.…` subjects and the stream definitions.
