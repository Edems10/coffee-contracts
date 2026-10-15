from __future__ import annotations

from dataclasses import dataclass

from coffee_contracts.subjects import (
    CATALOGUE_WILDCARD,
    EMBEDDING_WILDCARD,
    VERSION,
)


@dataclass(frozen=True, slots=True)
class Stream:
    """How a stream must be configured for the consumers to be able to trust it.

    Attributes:
        name: The stream's name on the broker.
        subjects: What it captures.
        max_msgs_per_subject: 0 for "keep everything"; 1 compacts the stream to
            the last message of each subject.
        max_age_seconds: 0 for "keep forever".
        description: Why it is shaped this way.
    """

    name: str
    subjects: tuple[str, ...]
    max_msgs_per_subject: int = 0
    max_age_seconds: int = 0
    description: str = ""


def _versioned(name: str) -> str:
    """Return a stream name carrying the current wire version.

    Args:
        name: The stream's name without a version, in upper case.

    Returns:
        The name with the wire version appended, as ``CATALOGUE_V2``.
    """
    return f"{name}_{VERSION.upper()}"


#: The catalogue as a compacted log. One subject per coffee and one message per
#: subject means the stream *is* the catalogue: a consumer that has never run,
#: or that was switched off for a week, replays it from the start and ends up
#: with every coffee exactly once and nothing twice. This is what lets a second
#: service be added later without the producer knowing or a backfill being run.
#:
#: The name carries the wire version because a stream is created and looked up
#: by name: a new wire version reusing the name would rewrite the running
#: stream's subjects in place instead of standing a second stream up beside it,
#: and standing one beside it is what lets the old generation keep serving while
#: consumers move. That is what went wrong in 3.0.0, which moved ``VERSION`` to
#: ``v2`` and left both stream names behind, so provisioning that contract
#: converted the live v1 streams rather than adding the v2 pair. The name is
#: derived from ``VERSION`` rather than spelled out for the same reason: a
#: literal is exactly what stood still.
CATALOGUE = Stream(
    name=_versioned("CATALOGUE"),
    subjects=(CATALOGUE_WILDCARD,),
    max_msgs_per_subject=1,
    description="Current state of every coffee, one message per coffee.",
)

#: Every coffee's embedding, one vector per coffee. Replaying the stream once
#: yields each current vector exactly once: a re-embedding replaces the previous
#: vector rather than joining it, so no consumer ever holds two for one coffee.
#: Its name carries the wire version for the reason the catalogue's does: a
#: stream is looked up by name, so a reused name converts the running stream
#: instead of adding one beside it.
EMBEDDINGS = Stream(
    name=_versioned("EMBEDDINGS"),
    subjects=(EMBEDDING_WILDCARD,),
    max_msgs_per_subject=1,
    description="Current embedding of every coffee, one vector per coffee.",
)

STREAMS = (CATALOGUE, EMBEDDINGS)
