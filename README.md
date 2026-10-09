# coffee-contracts

The events the coffee services send each other, and the only thing they share.

`coffee-aggregator` crawls shops and publishes. `coffee-cupper` consumes and
recommends. Neither reads the other's database and neither calls the other at
runtime — the whole relationship is in this repository, which is what lets each
be deployed on its own.

## The shape of it

**Events carry state, not pointers.** A `coffee.state` message holds the whole
coffee. A message that only said *"coffee X changed"* would force the consumer
to call back for the detail, and a consumer that calls the producer is coupled
to it being up — which is the thing this architecture exists to avoid.

**One subject per coffee.**

```
coffee.v1.catalogue.<site>.<external_id>     the coffee's current state
```

**The catalogue stream is compacted: one message per subject.** That makes the
stream *itself* the catalogue. A consumer that has never run, or that was off
for a week, replays it from the beginning and ends up with every coffee exactly
once and nothing twice. No backfill, no export, and the producer never learns
that a second consumer exists.

**A delisting is a state, not a deleted message.** `delisted_at` is a field.
Deleting the message would take the fact that the coffee is gone with it, and
the next replay would resurrect it.

**There is no crawl stream.** There was one, and it was dropped: `crawl_run`
in the aggregator already holds every counter, Loki already holds the log
lines, and no consumer had a use for either. An arrow into a consumer that
ignores it is worse than no arrow.

## Versioning

The version is in the subject, not the payload. A breaking change publishes
`coffee.v2.…` beside `coffee.v1.…`, both run for as long as it takes every
consumer to move, and nobody coordinates a release.

Additive change needs no new version: an unknown field is dropped on read, so a
producer can add one without waiting for its consumers. Refusing unknown fields
would make every addition a breaking change.

**What counts as breaking.** Removing a property, dropping a whole event type,
adding a `required` entry, and *any* change to what a property constrains —
its `type`, `enum`, `const`, `pattern`, `minLength`, `minimum`, its array
`items`, however deeply nested.

Both directions count. Narrowing breaks the producers already sending values
the schema now refuses; loosening breaks the consumers validating against the
schema they pinned, which is the whole point of pinning one. So making a field
nullable needs a new version too — the escape hatch is not a looser rule, it is
`VERSION`, and a new version costs little because both run side by side until
the last consumer moves.

Annotations are not part of it: `description`, `title`, `default` and
`examples` may be edited whenever. CI diffs every schema against the newest
release tag reachable from the branch and refuses all of the above unless
`VERSION` in `subjects.py` changed. A checkout that cannot see that tag fails
the build rather than skipping the check.

## Using it

```python
from coffee_contracts import CoffeeState, catalogue, check, to_json

event = CoffeeState(site="kafista", external_id="17133", observed_at=now, ...)
check(json.loads(to_json(event)))        # the producer validates; see below
nats.publish(catalogue(event.site, event.external_id), to_json(event))
```

**The producer validates before publishing.** It is the last place a bad
message can be stopped: once it is in a compacted stream, it *is* that coffee's
state until something replaces it.

`check` enforces `date-time` with the same parser `coffee_from_json` reads
with, so a timestamp it accepts is one the consumer can parse. It builds its
validator once per event type, which is what keeps validating a whole replay
in the tens of milliseconds.

The JSON Schemas under `src/coffee_contracts/schemas/` are the contract. The
Python dataclasses are a convenience for the two services that happen to be
written in Python; a consumer in another language reads the schemas and owes
this package nothing.

## Pinning

Consumers pin a tag, so a contract change never arrives unannounced:

```toml
dependencies = [
    "coffee-contracts @ git+https://github.com/Edems10/coffee-contracts@v2.1.0",
]
```

Sharing a schema is not the coupling this architecture avoids. It is consumed
at build time and versioned; a shared database or a synchronous call at runtime
would be.

## Releasing

A version that is not tagged is a version nobody can pin, and the pin above is
the whole of what a consumer installs. So a change to the contract is not done
when it merges — it is done when the tag exists and the consumers point at it:

1. Bump `version` in `pyproject.toml` and `__version__` in `__init__.py`
   together. A test fails when they disagree, because `__version__` is the
   first thing a consumer reads to find out what it got. Bump the pin in the
   snippet above too, so the README documents a tag that will exist.
2. Add the release to [`CHANGELOG.md`](CHANGELOG.md), saying what a consumer
   has to *do* about it. A tag is the whole of what a consumer installs, so
   this is the only place they can read what moved between two pins.
3. Tag the merge commit on `main`, and push the tag:

   ```bash
   git checkout main && git pull
   git tag -a v2.1.0 -m "v2.1.0" && git push origin v2.1.0
   ```

   Never tag a branch. The compatibility test diffs the schemas against the
   newest tag, so a tag off `main` would hold the contract to something that
   was never released.
4. Bump the pin in `coffee-aggregator` and `coffee-cupper` in the same pass.
   The broker mounts this working tree rather than installing it, so a
   contract that is only on `main` is one the broker provisions and no
   consumer has.

## Development

```bash
uv sync
uv run ruff check && uv run ruff format && uv run mypy && uv run pytest
```
