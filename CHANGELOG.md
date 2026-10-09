# Changelog

Consumers pin a tag, so the only way to find out what a bump costs is to read
it here. Each entry says what a consumer has to do, not what the diff touched.

The version here is the *distribution's*. The wire version lives in `VERSION`
in `subjects.py` and moves only when a subject changes — it has been `v1`
throughout.

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
