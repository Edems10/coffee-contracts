from __future__ import annotations

import re

#: The contract version, carried in every subject rather than in the payload.
#: A breaking change publishes `coffee.v2.…` beside `coffee.v1.…`, both streams
#: run for as long as it takes every consumer to move, and nobody coordinates a
#: release.
VERSION = "v1"

#: One subject per coffee, carrying that coffee's whole current state. The
#: stream keeps one message per subject, which makes the stream itself the
#: catalogue: a consumer that has never run, or that was switched off for a
#: week, replays it from the start and ends up with every coffee exactly once.
#: A coffee that stops being sold is not a deleted message but a state with
#: `delisted_at` set, so that fact survives the compaction too.
CATALOGUE_PREFIX = f"coffee.{VERSION}.catalogue"

#: Everything a stream subscribes to.
CATALOGUE_WILDCARD = f"{CATALOGUE_PREFIX}.>"

#: NATS splits subjects on dots and treats `*` and `>` as wildcards, so a site
#: id or a product id carrying any of them would silently widen a subscription.
_UNSAFE = re.compile(r"[.*> \t\n]")


class SubjectError(ValueError):
    """Raised when a token cannot be put in a subject without changing it."""


def _token(value: str, *, field: str) -> str:
    if not value:
        message = f"{field} is empty"
        raise SubjectError(message)
    if _UNSAFE.search(value):
        message = f"{field} {value!r} contains a character NATS reads as structure"
        raise SubjectError(message)
    return value


def catalogue(site: str, external_id: str) -> str:
    """Return the subject one coffee's state is published on.

    Args:
        site: The shop's registry id.
        external_id: The shop's own id for the product.

    Returns:
        The subject.

    Raises:
        SubjectError: When either token would change the subject's shape.
    """
    shop = _token(site, field="site")
    product = _token(external_id, field="external_id")
    return f"{CATALOGUE_PREFIX}.{shop}.{product}"
