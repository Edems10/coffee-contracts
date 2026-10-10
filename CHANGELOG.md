# Changelog

Consumers pin a tag, so the only way to find out what a bump costs is to read
it here. Each entry says what a consumer has to do, not what the diff touched.

The version here is the *distribution's*. The wire version lives in `VERSION`
in `subjects.py` and moves only when a subject changes — it has been `v1`
throughout.

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
