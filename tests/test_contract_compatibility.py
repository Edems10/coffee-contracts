from __future__ import annotations

import json
import re
import subprocess
import tomllib
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

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


def type_of(prop: dict[str, Any]) -> frozenset[str]:
    """Return a property's declared JSON types as a set.

    ``"string"`` and ``["string", "null"]`` are both legal spellings, so they
    are normalised before being compared across versions.

    Args:
        prop: One entry of a schema's ``properties``.

    Returns:
        The declared types, empty when the property declares none.
    """
    declared = prop.get("type")
    if declared is None:
        return frozenset()
    if isinstance(declared, str):
        return frozenset({declared})
    return frozenset(declared)


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


def released_tag() -> str | None:
    """Return the newest version tag, or None when the history has none.

    Returns:
        The tag name, or None when this checkout has no tags — which in CI
        means the fetch was shallow, and the test says so rather than passing.
    """
    found = subprocess.run(
        ["git", "tag", "--sort=-v:refname"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    tags = [line for line in found.stdout.splitlines() if line.startswith("v")]
    return tags[0] if tags else None


def released_schema(tag: str, name: str) -> dict[str, Any] | None:
    """Return a schema as it was at a tag, or None when it did not exist yet.

    Args:
        tag: The tag to read from.
        name: The schema's file name.

    Returns:
        The parsed schema, or None when the tag predates the file — a brand new
        event type is additive and breaks nobody.
    """
    shown = subprocess.run(  # noqa: S603
        ["git", "show", f"{tag}:{SCHEMA_PATH}/{name}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if shown.returncode != 0:
        return None
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
        pytest.fail(f"cannot list the schemas at {tag}: {listed.stderr.strip()}")
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
        pytest.skip("no version tag in this checkout; CI must fetch tags")
    if released_wire_version(tag) != VERSION:
        # A new wire version runs beside the old one on its own subject, so the
        # old consumers keep their event types however this contract is edited.
        return
    gone = released_files(tag) - set(SCHEMA_FILES.values())
    assert not gone, f"{sorted(gone)} dropped from the contract since {tag}"


@pytest.mark.parametrize("event_type", SCHEMA_FILES)
def test_the_schema_is_still_compatible_with_the_released_one(event_type: str) -> None:
    """Catch the three edits that quietly break a consumer that cannot be redeployed.

    Removing a property, retyping one, or demanding a new one are all invisible
    to ruff, mypy and every other test here: they pass green and fail in a
    consumer's process. A change that genuinely needs one of them is a new
    major version published on its own subject, which is what ``VERSION`` in
    ``subjects.py`` exists for.
    """
    tag = released_tag()
    if tag is None:
        pytest.skip("no version tag in this checkout; CI must fetch tags")
    was = released_schema(tag, SCHEMA_FILES[event_type])
    if was is None:
        return
    now = load(SCHEMA_DIR / SCHEMA_FILES[event_type])

    gone = set(was["properties"]) - set(now["properties"])
    assert not gone, f"{event_type}: {sorted(gone)} removed since {tag}"

    retyped = {
        name
        for name, prop in was["properties"].items()
        if type_of(now["properties"][name]) != type_of(prop)
    }
    assert not retyped, f"{event_type}: {sorted(retyped)} changed type since {tag}"

    newly_required = set(now["required"]) - set(was["required"])
    assert not newly_required, f"{event_type}: {sorted(newly_required)} newly required since {tag}"


def test_the_advertised_version_matches_the_distribution() -> None:
    """`__version__` is exported API, and it is the first thing a consumer reads
    to find out whether a class it depends on still exists. It was 1.0.0 against
    a pyproject saying 2.0.0 for exactly one commit, which is one too many."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    assert coffee_contracts.__version__ == pyproject["project"]["version"]
