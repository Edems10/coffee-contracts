from __future__ import annotations

from importlib import resources


def test_the_package_ships_a_py_typed_marker() -> None:
    """Without the marker, mypy refuses to look inside an installed package.

    PEP 561 makes the marker the only thing that tells a consumer's type
    checker these annotations are real. Without it every ``CoffeeState`` field
    arrives as ``Any`` at precisely the boundary the contract exists to pin
    down, and both consumers papered over it with ``follow_untyped_imports``.
    """
    assert resources.files("coffee_contracts").joinpath("py.typed").is_file()
