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


def named(path: str, name: str) -> str:
    """Return the dotted path of a property below a path ("" is the root schema).

    Args:
        path: The path of the enclosing subschema.
        name: The property, or the keyword such as ``items``, below it.

    Returns:
        ``path.name``, or just ``name`` at the root.
    """
    return f"{path}.{name}" if path else name


def is_open(node: dict[str, Any]) -> bool:
    """Return whether an object subschema accepts properties it does not name.

    Args:
        node: An object subschema.

    Returns:
        True when ``additionalProperties`` is absent or ``true``. A schema
        value, or ``false``, is not open.
    """
    return node.get("additionalProperties", True) is True


def breaking_changes(was: object, now: object, path: str = "") -> list[str]:
    """Return what makes ``now`` break somebody who validates against ``was``.

    The same rule applies to the root schema and to every object subschema
    below it, including the ``items`` of an array. An object subschema is one
    that has ``properties``. In each, three things fail: a released property
    removed, a released property that breaks by this same rule, and a property
    newly in ``required``. A property that was not there is additive, and
    breaks nobody, only when the object is open at the release and stays open
    (``is_open`` on both sides); a new property in an object that was closed,
    or has closed since, fails.

    Everything else in a subschema is compared whole with ``constraints``:
    every keyword except ``properties``, ``required`` and a walked ``items``,
    so ``additionalProperties`` going from true to false, a changed ``type``,
    ``enum``, ``pattern`` or ``minimum``, and a changed ``maxItems`` all fail.
    A subschema without ``properties`` or ``items`` is compared whole. The root
    is held to the same rule, so its own keywords (``$id``, ``type``,
    ``allOf``) are compared too, where only its ``properties`` and ``required``
    were before. An object with ``properties`` that omits ``additionalProperties``
    is read as one that says ``true``, which is what omitting it means.

    A ``properties`` map is walked as property name to subschema and never
    passed to ``constraints``, which drops annotation keywords from every
    mapping: a property named ``description`` would otherwise vanish from the
    comparison. Only ``properties`` and ``items`` are walked; a subschema under
    any other keyword is compared whole.

    Args:
        was: The subschema as released.
        now: The subschema as it is in this checkout.
        path: The dotted path of this subschema from the root, empty at the
            root, used to name each finding.

    Returns:
        One message per finding, each naming its path, empty when ``now`` is
        compatible with ``was``.
    """
    label = path or "the schema"
    if not (isinstance(was, dict) and isinstance(now, dict)):
        return [] if constraints(was) == constraints(now) else [f"{label} constrains differently"]

    walked = {"items"} if "items" in was and "items" in now else set()
    if "properties" in was:
        walked |= {"properties", "required"}
    problems = []
    defaults = {"additionalProperties": True} if "properties" in was else {}
    if constraints(
        {**defaults, **{k: v for k, v in was.items() if k not in walked}}
    ) != constraints({**defaults, **{k: v for k, v in now.items() if k not in walked}}):
        problems.append(f"{label} constrains differently")

    if "items" in walked:
        problems += breaking_changes(was["items"], now["items"], named(path, "items"))

    if "properties" in walked:
        problems += object_changes(was, now, path)
    return problems


def object_changes(was: dict[str, Any], now: dict[str, Any], path: str) -> list[str]:
    """Return what makes an object's properties break somebody validating against ``was``.

    Args:
        was: The object subschema as released, which has ``properties``.
        now: The same subschema as it is in this checkout.
        path: The dotted path of the object from the root, empty at the root.

    Returns:
        One message per removed, newly required or incompatible property, and
        per property added to an object that is not open on both sides.
    """
    problems: list[str] = []
    was_properties: dict[str, Any] = was["properties"]
    now_properties: dict[str, Any] = now.get("properties", {})
    for name, released in was_properties.items():
        if name in now_properties:
            problems += breaking_changes(released, now_properties[name], named(path, name))
        else:
            problems.append(f"{named(path, name)} removed")
    for name in sorted(set(now.get("required", [])) - set(was.get("required", []))):
        problems.append(f"{named(path, name)} newly required")
    for name in sorted(set(now_properties) - set(was_properties)):
        if not is_open(was):
            problems.append(f"{named(path, name)} added to a closed object")
        elif not is_open(now):
            problems.append(f"{named(path, name)} added to an object that is now closed")
    return problems


#: Every edit the old top-level-``type`` comparison waved through, each as the
#: property this contract ships today and the version that breaks somebody.
#: ``process_method``, ``origin_country``, ``name`` and ``variety`` are real
#: properties of ``coffee.state.v2.json``; the sub-object is not yet, which is
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


def shape(
    properties: dict[str, Any], required: tuple[str, ...] = (), additional: bool = True
) -> dict[str, Any]:
    """Build an object subschema, open unless ``additional`` is false."""
    return {
        "type": "object",
        "required": list(required),
        "additionalProperties": additional,
        "properties": properties,
    }


#: ``price_history`` as it is released, the array of open objects that
#: #56 first needed a property added to.
POINT = {
    "on": {"type": "string", "format": "date"},
    "price_per_kg_eur_cents": {"type": ["integer", "null"], "description": "per kilogram"},
    "available": {"type": ["boolean", "null"]},
}
POINT_REQUIRED = ("on", "price_per_kg_eur_cents", "available")


def history(items: dict[str, Any]) -> dict[str, Any]:
    """Build a root schema whose only property is the array ``price_history``."""
    return shape({"price_history": {"type": "array", "maxItems": 50, "items": items}})


def deep(inner: dict[str, Any]) -> dict[str, Any]:
    """Build a root schema holding ``outer.inner`` two objects down."""
    return shape({"outer": shape({"inner": inner})})


#: Edits the nested rule permits, each as (was, now).
NESTED_ADDITIVE = [
    (
        "a new optional property in an open nested object",
        history(shape(POINT, POINT_REQUIRED)),
        history(
            shape({**POINT, "price_minor": {"type": ["integer", "null"]}}, POINT_REQUIRED),
        ),
    ),
    (
        "a new optional property two levels deep",
        deep(shape({"a": {"type": "string"}})),
        deep(shape({"a": {"type": "string"}, "b": {"type": ["string", "null"]}})),
    ),
    (
        "additionalProperties spelled true where it was absent",
        {"type": "object", "properties": {"a": {"type": "string"}}},
        shape({"a": {"type": "string"}}, ()),
    ),
    (
        "a new top-level property",
        shape({"a": {"type": "string"}}),
        shape({"a": {"type": "string"}, "b": {"type": "string"}}),
    ),
    (
        "a description edited on a nested property",
        history(shape(POINT, POINT_REQUIRED)),
        history(
            shape(
                {
                    **POINT,
                    "price_per_kg_eur_cents": {"type": ["integer", "null"], "description": "x"},
                },
                POINT_REQUIRED,
            )
        ),
    ),
    (
        "a nested type listed in another order",
        history(shape(POINT, POINT_REQUIRED)),
        history(shape({**POINT, "available": {"type": ["null", "boolean"]}}, POINT_REQUIRED)),
    ),
    (
        "a description edited on a nested property named description",
        deep(shape({"description": {"type": "string", "description": "old"}})),
        deep(shape({"description": {"type": "string", "description": "new"}})),
    ),
]

#: Edits the nested rule refuses, each as (was, now).
NESTED_BREAKING = [
    (
        "a new nested property also made required",
        history(shape(POINT, POINT_REQUIRED)),
        history(
            shape(
                {**POINT, "price_minor": {"type": ["integer", "null"]}},
                (*POINT_REQUIRED, "price_minor"),
            )
        ),
    ),
    (
        "a nested object closing to unknown fields",
        history(shape(POINT, POINT_REQUIRED)),
        history(shape(POINT, POINT_REQUIRED, additional=False)),
    ),
    (
        "a nested property's type narrowing",
        history(shape(POINT, POINT_REQUIRED)),
        history(shape({**POINT, "available": {"type": "boolean"}}, POINT_REQUIRED)),
    ),
    (
        "a nested property's enum narrowing",
        deep(shape({"kind": {"type": "string", "enum": ["a", "b"]}})),
        deep(shape({"kind": {"type": "string", "enum": ["a"]}})),
    ),
    (
        "a nested property removed",
        history(shape(POINT, POINT_REQUIRED)),
        history(shape({k: v for k, v in POINT.items() if k != "available"}, POINT_REQUIRED[:2])),
    ),
    (
        "a nested property named description retyped",
        deep(shape({"description": {"type": "string"}})),
        deep(shape({"description": {"type": "integer"}})),
    ),
    (
        "a new property in a nested object closed at the tag",
        deep(shape({"a": {"type": "string"}}, additional=False)),
        deep(
            shape(
                {"a": {"type": "string"}, "b": {"type": "string"}},
                additional=False,
            )
        ),
    ),
    (
        "a new property in a nested object open at the tag but closed now",
        deep(shape({"a": {"type": "string"}})),
        deep(
            shape(
                {"a": {"type": "string"}, "b": {"type": "string"}},
                additional=False,
            )
        ),
    ),
    (
        "an array's maxItems lowered beside open items",
        history(shape(POINT, POINT_REQUIRED)),
        {
            **history(shape(POINT, POINT_REQUIRED)),
            "properties": {
                "price_history": {
                    "type": "array",
                    "maxItems": 10,
                    "items": shape(POINT, POINT_REQUIRED),
                }
            },
        },
    ),
    (
        "an object that omitted additionalProperties closing",
        {"type": "object", "properties": {"a": {"type": "string"}}},
        shape({"a": {"type": "string"}}, (), additional=False),
    ),
    (
        "a top-level property removed",
        shape({"a": {"type": "string"}, "b": {"type": "string"}}),
        shape({"a": {"type": "string"}}),
    ),
    (
        "a top-level property retyped",
        shape({"a": {"type": ["integer", "null"]}}),
        shape({"a": {"type": "integer"}}),
    ),
]


@pytest.mark.parametrize(
    ("edit", "was", "now"), NESTED_ADDITIVE, ids=[e[0] for e in NESTED_ADDITIVE]
)
def test_an_additive_edit_at_any_depth_is_compatible(
    edit: str, was: dict[str, Any], now: dict[str, Any]
) -> None:
    """A property nothing required, in an object that stayed open, breaks nobody."""
    assert breaking_changes(was, now) == [], edit


@pytest.mark.parametrize(
    ("edit", "was", "now"), NESTED_BREAKING, ids=[e[0] for e in NESTED_BREAKING]
)
def test_a_breaking_edit_at_any_depth_is_refused(
    edit: str, was: dict[str, Any], now: dict[str, Any]
) -> None:
    """Each of these breaks a consumer or a producer however deep it sits."""
    assert breaking_changes(was, now), edit


def test_a_nested_finding_names_its_path() -> None:
    """The message says which property, because a bare "price_history" is no help."""
    was = history(shape(POINT, POINT_REQUIRED))
    now = history(
        shape(
            {**POINT, "price_minor": {"type": ["integer", "null"]}},
            (*POINT_REQUIRED, "price_minor"),
        )
    )
    assert breaking_changes(was, now) == ["price_history.items.price_minor newly required"]


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

    **The rule, at the top level and again inside every object, the ``items``
    of an array included: what a released property constrains is frozen in both
    directions, and the set of properties may only grow.** Narrowing breaks the
    producers already sending values the schema now refuses. Loosening breaks
    the consumers validating against the schema they pinned: a shop with a
    three-letter country code is not something a consumer compiled against
    ``^[A-Z]{2}$`` can suddenly be handed. Neither side is cheaper than the
    other here, and both are free to fix the honest way, because a new version
    runs beside the old one until the last consumer moves. So this compares the
    whole subschema of each released property, and making a field nullable
    needs a version bump too.

    Inside an object, a released property may not be removed or constrain
    differently, and no property may become required. A new property that is
    not required is additive, but only in an object that was open at the tag
    (``additionalProperties`` absent or true) and is still open: consumers
    keep the fields they know and ignore the rest. Closing an object, or adding
    a property to one that is closed, is breaking. Annotations are not part of
    any of it: ``description``, ``title``, ``default`` and ``examples`` may be
    edited at any time. See ``breaking_changes``.
    """
    tag = released_tag()
    if tag is None:
        unavailable("no release tag is reachable from this checkout")
    was = released_schema(tag, SCHEMA_FILES[event_type])
    if was is None:
        return
    now = load(SCHEMA_DIR / SCHEMA_FILES[event_type])

    problems = breaking_changes(was, now)
    assert not problems, f"{event_type}: " + "; ".join(f"{p} since {tag}" for p in problems)


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
