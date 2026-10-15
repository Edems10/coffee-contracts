# Changelog

Consumers pin a tag, so the only way to find out what a bump costs is to read
it here. Each entry says what a consumer has to do, not what the diff touched.

The version here is the *distribution's*. The wire version lives in `VERSION`
in `subjects.py` and moves only when a subject changes — it was `v1`
until 3.0.0 and is `v2` from there.

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
