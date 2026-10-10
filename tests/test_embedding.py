from __future__ import annotations

import base64
import struct
from typing import Any

import pytest

from coffee_contracts import COFFEE_EMBEDDING, ContractError, check
from coffee_contracts.validate import schema

MODEL = "intfloat/multilingual-e5-base"
DIMENSION = 768
WIRE_BYTES = DIMENSION * 4


def base64_of(count: int) -> str:
    """Return base64 of ``count`` little-endian float32 values, as a producer writes them."""
    raw = struct.pack(f"<{count}f", *([0.5] * count))
    return base64.b64encode(raw).decode("ascii")


def an_embedding(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": COFFEE_EMBEDDING,
        "site": "kafista",
        "external_id": "17133",
        "model": MODEL,
        "dimension": DIMENSION,
        "dtype": "float32",
        "vector": base64_of(DIMENSION),
    }
    payload.update(overrides)
    return payload


def test_a_well_formed_embedding_validates() -> None:
    check(an_embedding())


def test_the_vector_decodes_to_3072_bytes() -> None:
    """The size the issue promises: 768 float32 values, nothing padded or sent as JSON."""
    assert len(base64.b64decode(an_embedding()["vector"])) == WIRE_BYTES


@pytest.mark.parametrize("count", [0, 1, 767, 769, 1024])
def test_a_vector_of_the_wrong_length_is_refused(count: int) -> None:
    """A vector whose decoded length disagrees with the stated dimension is one a
    consumer would read as the wrong numbers, so the producer must not send it."""
    payload = an_embedding(vector=base64_of(count))

    with pytest.raises(ContractError, match=f"decodes to {count * 4} bytes"):
        check(payload)


def test_a_truncated_vector_that_still_decodes_is_refused() -> None:
    """Dropping the last four characters leaves valid base64 that decodes to
    3069 bytes: the failure a shape-only check would wave through."""
    truncated = an_embedding()["vector"][:-4]
    base64.b64decode(truncated, validate=True)  # the premise: it does decode

    with pytest.raises(ContractError, match="decodes to 3069 bytes"):
        check(an_embedding(vector=truncated))


@pytest.mark.parametrize("vector", ["not base64!", "vektoré", "AAAA\nAAAA"])
def test_a_vector_that_is_not_base64_is_refused(vector: str) -> None:
    with pytest.raises(ContractError, match="vector is not base64"):
        check(an_embedding(vector=vector))


def test_a_dimension_other_than_the_model_produces_is_refused() -> None:
    """A different model is a contract change, so the schema refuses a payload that
    claims one rather than letting it through on a shape check."""
    payload = an_embedding(dimension=1024, vector=base64_of(1024))

    with pytest.raises(ContractError, match="768"):
        check(payload)


def test_a_different_model_is_refused() -> None:
    """Vectors from two models are not comparable: a swap that keeps the dimension
    must not be read as the same contract, so the schema pins the name."""
    with pytest.raises(ContractError, match="intfloat/multilingual-e5-base"):
        check(an_embedding(model="intfloat/multilingual-e5-large"))


def test_an_embedding_without_its_model_is_refused() -> None:
    payload = an_embedding()
    del payload["model"]

    with pytest.raises(ContractError, match="'model' is a required property"):
        check(payload)


def test_a_dtype_other_than_float32_is_refused() -> None:
    with pytest.raises(ContractError, match="float32"):
        check(an_embedding(dtype="float64"))


def test_an_embedding_without_its_vector_is_refused() -> None:
    payload = an_embedding()
    del payload["vector"]

    with pytest.raises(ContractError, match="'vector' is a required property"):
        check(payload)


def test_a_field_this_version_never_heard_of_is_allowed() -> None:
    """Same rule as ``coffee.state``: a later producer's extra field must still validate."""
    check(an_embedding(norm="l2"))


def test_the_schema_states_the_model_dimension_and_dtype() -> None:
    """These are what the compatibility suite compares: a const change is a
    constraint change, and the description is not."""
    properties = schema(COFFEE_EMBEDDING)["properties"]

    assert properties["model"]["const"] == MODEL
    assert properties["dimension"]["const"] == DIMENSION
    assert properties["dtype"]["const"] == "float32"


def test_the_schema_names_the_model() -> None:
    assert "intfloat/multilingual-e5-base" in schema(COFFEE_EMBEDDING)["description"]
