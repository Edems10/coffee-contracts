from __future__ import annotations

from dataclasses import dataclass

from coffee_contracts.subjects import CATALOGUE_WILDCARD


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


#: The catalogue as a compacted log. One subject per coffee and one message per
#: subject means the stream *is* the catalogue: a consumer that has never run,
#: or that was switched off for a week, replays it from the start and ends up
#: with every coffee exactly once and nothing twice. This is what lets a second
#: service be added later without the producer knowing or a backfill being run.
CATALOGUE = Stream(
    name="CATALOGUE",
    subjects=(CATALOGUE_WILDCARD,),
    max_msgs_per_subject=1,
    description="Current state of every coffee, one message per coffee.",
)

STREAMS = (CATALOGUE,)
