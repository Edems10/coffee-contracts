from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, NoReturn

import jsonschema
import pytest

import coffee_contracts
from coffee_contracts.events import CoffeeState
from coffee_contracts.subjects import VERSION
from coffee_contracts.validate import SCHEMA_FILES

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "src" / "coffee_contracts" / "schemas"

#: The same directory as ``SCHEMA_DIR``, spelled the way git addresses it.
SCHEMA_PATH = "src/coffee_contracts/schemas"

#: Every git invocation below runs from here, because a pathspec is
#: resolved against the working directory rather than the repository root.
REPO_ROOT = SCHEMA_DIR.parents[2]

#: ``type`` is the discriminator the serialiser writes; it is not a field of
#: either dataclass, so every comparison below ignores it.
DISCRIMINATOR = "type"

CLASSES = {"coffee.state": CoffeeState}


def load(path: Path) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return parsed


#: Keywords that describe a property rather than constrain it. Editing one
#: cannot make a payload that used to validate stop validating, so they are
#: dropped before two releases of the same property are compared.
ANNOTATIONS = frozenset(
    {
        "$comment",
        "default",
        "deprecated",
        "description",
        "examples",
        "readOnly",
        "title",
        "writeOnly",
    }
)

#: Keywords JSON spells as a list but whose meaning is a set, so reordering one
#: changes nothing: ``["string", "null"]`` and ``["null", "string"]`` are the
#: same property, and ``"string"`` is the same again.
UNORDERED = frozenset({"enum", "required", "type"})


def constraints(node: object) -> object:
    """Return everything in a subschema that a payload has to satisfy.

    This replaces a comparison of a property's top-level ``type``, which saw
    none of the edits that actually break people: an ``enum`` or ``const``
    added to a free-text field, a ``pattern`` tightened, a ``minLength`` or
    ``minimum`` appearing, an array's ``items`` retyped, or a sub-object closed
    with ``additionalProperties: false``. Comparing the whole subschema catches
    all of them and anything else a future keyword invents, because the rule is
    expressed as "nothing that constrains a payload may differ" rather than as
    a list of keywords someone has to remember to extend.

    Args:
        node: A subschema, or any value nested inside one.

    Returns:
        The same structure with annotations dropped and set-like keywords
        sorted, so two releases compare equal exactly when they demand the
        same thing of a payload.
    """
    if isinstance(node, dict):
        kept: dict[str, object] = {
            k: constraints(v) for k, v in node.items() if k not in ANNOTATIONS
        }
        for key in UNORDERED & kept.keys():
            # A property may legitimately be *named* ``type`` — this contract
            # has one — in which case the value is a subschema, not a set of
            # type names, and must be left exactly as it is.
            value = [kept[key]] if isinstance(kept[key], str) else kept[key]
            if isinstance(value, list):
                kept[key] = sorted(value, key=lambda item: json.dumps(item, sort_keys=True))
        return dict(sorted(kept.items()))
    if isinstance(node, list):
        return [constraints(item) for item in node]
    return node


#: Every edit the old top-level-``type`` comparison waved through, each as the
#: property this contract ships today and the version that breaks somebody.
#: ``process_method``, ``origin_country``, ``name`` and ``variety`` are real
#: properties of ``coffee.state.v1.json``; the sub-object is not yet, which is
#: why its case is latent rather than hypothetical.
BREAKING_EDITS = [
    (
        "an enum added to a free-text field",
        {"type": ["string", "null"]},
        {"type": ["string", "null"], "enum": ["washed", "natural", "honey"]},
    ),
    (
        "a const pinned on a free-text field",
        {"type": ["string", "null"]},
        {"type": ["string", "null"], "const": "washed"},
    ),
    (
        "a pattern tightened",
        {"type": ["string", "null"], "pattern": "^[A-Z]{2}$"},
        {"type": ["string", "null"], "pattern": "^(CZ|SK)$"},
    ),
    (
        "a minLength added",
        {"type": ["string", "null"]},
        {"type": ["string", "null"], "minLength": 1},
    ),
    (
        "a minimum added",
        {"type": ["number", "null"]},
        {"type": ["number", "null"], "minimum": 0},
    ),
    (
        "an array's items retyped",
        {"type": "array", "items": {"type": "string"}},
        {"type": "array", "items": {"type": "integer"}},
    ),
    (
        "a sub-object closed to unknown fields",
        {"type": "object", "additionalProperties": True},
        {"type": "object", "additionalProperties": False},
    ),
    (
        "a field made nullable",
        {"type": "string"},
        {"type": ["string", "null"]},
    ),
]

#: Edits the rule deliberately permits. Annotations constrain nothing, and a
#: reordered ``type`` is the same property spelled differently.
HARMLESS_EDITS = [
    (
        "a description rewritten",
        {"type": "string", "description": "the shop's name for it"},
        {"type": "string", "description": "the product name as the shop prints it"},
    ),
    (
        "a type listed in another order",
        {"type": ["string", "null"]},
        {"type": ["null", "string"]},
    ),
    (
        "a type spelled as a bare string",
        {"type": ["string"]},
        {"type": "string"},
    ),
]


@pytest.mark.parametrize(("edit", "was", "now"), BREAKING_EDITS, ids=[e[0] for e in BREAKING_EDITS])
def test_a_tightened_or_loosened_property_is_a_change(
    edit: str, was: dict[str, Any], now: dict[str, Any]
) -> None:
    """Each of these validates the same top-level ``type`` and breaks somebody."""
    assert constraints(was) != constraints(now), edit


@pytest.mark.parametrize(("edit", "was", "now"), HARMLESS_EDITS, ids=[e[0] for e in HARMLESS_EDITS])
def test_an_annotation_or_a_respelling_is_not_a_change(
    edit: str, was: dict[str, Any], now: dict[str, Any]
) -> None:
    """Refusing these would make the check a nuisance nobody trusts."""
    assert constraints(was) == constraints(now), edit


# --- the schema and the dataclass are one contract, not two -------------------


@pytest.mark.parametrize(("event_type", "cls"), CLASSES.items())
def test_every_field_is_in_the_schema(event_type: str, cls: type) -> None:
    """A field added to the dataclass and forgotten in the schema validates as nothing."""
    schema = load(SCHEMA_DIR / SCHEMA_FILES[event_type])
    assert {f.name for f in fields(cls)} == set(schema["properties"]) - {DISCRIMINATOR}


@pytest.mark.parametrize(("event_type", "cls"), CLASSES.items())
def test_required_means_the_same_on_both_sides(event_type: str, cls: type) -> None:
    """A field the schema demands but the dataclass defaults is one nobody has to send."""
    schema = load(SCHEMA_DIR / SCHEMA_FILES[event_type])
    without_default = {
        f.name for f in fields(cls) if f.default is MISSING and f.default_factory is MISSING
    }
    assert without_default == set(schema["required"]) - {DISCRIMINATOR}


@pytest.mark.parametrize("event_type", SCHEMA_FILES)
def test_every_schema_is_itself_a_valid_schema(event_type: str) -> None:
    """`check` builds its validator once and keeps it, which is what makes a
    replay affordable — but it also means nothing re-reads the schema against
    the metaschema at run time any more. A misspelled keyword would otherwise
    validate nothing, quietly, in every producer."""
    jsonschema.Draft202012Validator.check_schema(load(SCHEMA_DIR / SCHEMA_FILES[event_type]))


@pytest.mark.parametrize("event_type", SCHEMA_FILES)
def test_unknown_properties_stay_allowed(event_type: str) -> None:
    """A newer producer's extra field must still validate against this schema.

    ``additionalProperties: false`` would make every additive change breaking
    for everyone running the older contract, which is the opposite of what the
    version-in-the-subject scheme is for.
    """
    assert load(SCHEMA_DIR / SCHEMA_FILES[event_type]).get("additionalProperties") is True


# --- nothing may break a consumer still on the released contract --------------


def unavailable(reason: str) -> NoReturn:
    """Stop a compatibility check that cannot see the released contract.

    A skip exits 0, so the suite went green while checking nothing — the exact
    failure ``fetch-depth: 0`` was added to prevent, and one a shallow checkout
    reintroduces silently. In CI that is a failure. Locally a working tree can
    honestly have no tags, and a loud skip is enough.

    Args:
        reason: What could not be read.
    """
    if os.environ.get("CI"):
        pytest.fail(f"{reason}; CI must check against the released contract")
    pytest.skip(reason)


def released_tag() -> str | None:
    """Return the newest release tag reachable from this checkout.

    ``git tag --sort=-v:refname`` was wrong twice. Without ``versionsort.suffix``
    it sorts ``v3.0.0-rc.1`` *above* ``v3.0.0``, so the first release candidate
    would quietly become the baseline every later change is held to; and it
    lists every tag in the repository, including ones on no branch at all.
    ``git describe`` walks this history instead, and ``--exclude`` drops
    pre-releases, whose SemVer spelling always carries a hyphen.

    Returns:
        The tag name, or None when no release tag is reachable.
    """
    found = subprocess.run(
        [  # noqa: S607
            "git",
            "describe",
            "--tags",
            "--abbrev=0",
            "--match",
            "v[0-9]*",
            "--exclude",
            "*-*",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if found.returncode != 0:
        return None
    return found.stdout.strip() or None


def released_schema(tag: str, name: str) -> dict[str, Any] | None:
    """Return a schema as it was at a tag, or None when it did not exist yet.

    Whether the file was there is settled by the tag's own tree listing, not by
    a non-zero exit: ``git show`` fails the same way for a path that never
    existed and for a tag this checkout cannot read, and treating both as
    "nothing to compare" passed the test in the second case.

    Args:
        tag: The tag to read from.
        name: The schema's file name.

    Returns:
        The parsed schema, or None when the tag predates the file — a brand new
        event type is additive and breaks nobody.
    """
    if name not in released_files(tag):
        return None
    shown = subprocess.run(  # noqa: S603
        ["git", "show", f"{tag}:{SCHEMA_PATH}/{name}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if shown.returncode != 0:
        unavailable(f"cannot read {name} at {tag}: {shown.stderr.strip()}")
    parsed: dict[str, Any] = json.loads(shown.stdout)
    return parsed


def released_files(tag: str) -> frozenset[str]:
    """Return the schema file names the contract shipped at a tag.

    The compatibility test below iterates the *current* ``SCHEMA_FILES``, so a
    deleted event type stops being checked rather than failing. Reading the
    tag's own listing is the only way to notice something that is no longer
    there.

    Args:
        tag: The tag to list.

    Returns:
        The base names of the JSON schemas present at that tag.
    """
    listed = subprocess.run(  # noqa: S603
        ["git", "ls-tree", "-r", "--name-only", tag, "--", SCHEMA_PATH],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if listed.returncode != 0:
        unavailable(f"cannot list the schemas at {tag}: {listed.stderr.strip()}")
    return frozenset(
        line.rsplit("/", 1)[-1] for line in listed.stdout.splitlines() if line.endswith(".json")
    )


def released_wire_version(tag: str) -> str | None:
    """Return the wire ``VERSION`` as it was at a tag.

    Args:
        tag: The tag to read from.

    Returns:
        The version string, or None when the tag predates ``subjects.py``.
    """
    shown = subprocess.run(  # noqa: S603
        ["git", "show", f"{tag}:src/coffee_contracts/subjects.py"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if shown.returncode != 0:
        return None
    found = re.search(r'^VERSION = "([^"]+)"', shown.stdout, re.MULTILINE)
    return found.group(1) if found else None


def test_no_event_type_disappears_from_the_contract() -> None:
    """A deleted schema is a consumer switching on a type that stops arriving.

    The per-property test below parametrises over the *current* ``SCHEMA_FILES``,
    so deleting an entry removes the check along with the contract. That is
    exactly what happened to ``crawl.finished.v1.json``, and the suite stayed
    green. Dropping an event type is a major change like any other, so it is
    refused until the wire ``VERSION`` in ``subjects.py`` says so.
    """
    tag = released_tag()
    if tag is None:
        unavailable("no release tag is reachable from this checkout")
    if released_wire_version(tag) != VERSION:
        # A new wire version runs beside the old one on its own subject, so the
        # old consumers keep their event types however this contract is edited.
        return
    gone = released_files(tag) - set(SCHEMA_FILES.values())
    assert not gone, f"{sorted(gone)} dropped from the contract since {tag}"


@pytest.mark.parametrize("event_type", SCHEMA_FILES)
def test_the_schema_is_still_compatible_with_the_released_one(event_type: str) -> None:
    """Catch the edits that quietly break somebody who cannot be redeployed.

    Removing a property, demanding a new one, or changing what one constrains
    are all invisible to ruff, mypy and every other test here: they pass green
    and fail in another process. A change that genuinely needs one of them is a
    new wire version published on its own subject, which is what ``VERSION`` in
    ``subjects.py`` exists for.

    **The rule: what a property constrains is frozen in both directions.**
    Narrowing breaks the producers already sending values the schema now
    refuses. Loosening breaks the consumers validating against the schema they
    pinned — a shop with a three-letter country code is not something a
    consumer compiled against ``^[A-Z]{2}$`` can suddenly be handed. Neither
    side is cheaper than the other here, and both are free to fix the honest
    way, because a new version runs beside the old one until the last consumer
    moves. So this compares the whole subschema, and making a field nullable
    needs a version bump too. Annotations are not part of it: ``description``,
    ``title``, ``default`` and ``examples`` may be edited at any time.
    """
    tag = released_tag()
    if tag is None:
        unavailable("no release tag is reachable from this checkout")
    was = released_schema(tag, SCHEMA_FILES[event_type])
    if was is None:
        return
    now = load(SCHEMA_DIR / SCHEMA_FILES[event_type])

    gone = set(was["properties"]) - set(now["properties"])
    assert not gone, f"{event_type}: {sorted(gone)} removed since {tag}"

    changed = {
        name
        for name, prop in was["properties"].items()
        if constraints(now["properties"][name]) != constraints(prop)
    }
    assert not changed, (
        f"{event_type}: {sorted(changed)} constrains a payload differently than at {tag}"
    )

    newly_required = set(now["required"]) - set(was["required"])
    assert not newly_required, f"{event_type}: {sorted(newly_required)} newly required since {tag}"


def test_a_baseline_that_cannot_be_read_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """A checkout that cannot see the released contract must not go green.

    ``git show`` exits non-zero both for a path that never existed and for a
    tag this checkout has no objects for, and reading the second as "nothing to
    compare yet" let the whole check pass while comparing nothing.
    """
    monkeypatch.setenv("CI", "1")
    with pytest.raises(pytest.fail.Exception):
        released_schema("v0.0.0-no-such-tag", next(iter(SCHEMA_FILES.values())))


def test_an_event_type_the_tag_predates_is_additive() -> None:
    """A schema added since the release breaks nobody, so there is nothing to diff."""
    tag = released_tag()
    if tag is None:
        unavailable("no release tag is reachable from this checkout")
    assert released_schema(tag, "not.a.real.event.v1.json") is None


def test_the_advertised_version_matches_the_distribution() -> None:
    """`__version__` is exported API, and it is the first thing a consumer reads
    to find out whether a class it depends on still exists. It was 1.0.0 against
    a pyproject saying 2.0.0 for exactly one commit, which is one too many."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    assert coffee_contracts.__version__ == pyproject["project"]["version"]
