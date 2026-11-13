"""Every type survives encoding and decoding, and rejects or reproduces any input.

The strategies are generated with the code, so these tests cover every struct, enum,
union and union arm.
"""

import copy
import json
import pickle
import struct
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

import stellar_xdr as xdr

from .strategies import ARMS, DISCRIMINANTS, STRATEGIES

# (what is generated, the type that decodes it, its strategy)
CASES = [(name, name, STRATEGIES[name]) for name in sorted(STRATEGIES)] + [
    (arm, union, strategy) for arm, (union, strategy) in sorted(ARMS.items())
]
IDS = [case[0] for case in CASES]


def decoder(name: str) -> Any:
    """The class, enum or union namespace that decodes a type."""
    return getattr(xdr, name)


@pytest.mark.parametrize(("name", "union", "strategy"), CASES, ids=IDS)
@given(data=st.data())
def test_round_trip(
    name: str,  # noqa: ARG001 - shown in the test id
    union: str,
    strategy: st.SearchStrategy[Any],
    data: st.DataObject,
) -> None:
    value = data.draw(strategy)
    encoded = value.to_xdr_bytes()
    decoded = decoder(union).from_xdr_bytes(encoded)
    assert decoded == value
    assert hash(decoded) == hash(value)
    assert decoded.to_xdr_bytes() == encoded
    assert decoder(union).from_xdr_base64(value.to_xdr_base64()) == value
    text = json.dumps(value.to_json_value())
    assert decoder(union).from_json_value(json.loads(text)) == value
    assert pickle.loads(pickle.dumps(value)) == value  # noqa: S301 - our own data
    assert copy.deepcopy(value) == value
    # Equality is never true across types, whatever the fields hold.
    assert value != object()
    if issubclass(type(value), bytes | int | tuple):
        # A typedef's value or an enum member: its class returns it as it is.
        assert type(value)(value) is value


@pytest.mark.parametrize(("name", "union", "strategy"), CASES, ids=IDS)
@given(data=st.data())
def test_damaged_input_is_rejected_or_reproduced(
    name: str,  # noqa: ARG001 - shown in the test id
    union: str,
    strategy: st.SearchStrategy[Any],
    data: st.DataObject,
) -> None:
    encoded = bytearray(data.draw(strategy).to_xdr_bytes())
    if encoded:
        position = data.draw(st.integers(0, len(encoded) - 1))
        encoded[position] = data.draw(st.integers(0, 255))
    cut = data.draw(st.integers(0, len(encoded) + 4))
    damaged = bytes(encoded[:cut]) + data.draw(st.binary(max_size=4))
    try:
        decoded = decoder(union).from_xdr_bytes(damaged)
    except xdr.XdrDecodeError:
        return
    # The encoding is canonical: anything accepted encodes back to the same bytes.
    assert decoded.to_xdr_bytes() == damaged


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@given(data=st.binary(max_size=64))
def test_arbitrary_bytes_are_rejected_or_reproduced(name: str, data: bytes) -> None:
    try:
        decoded = decoder(name).from_xdr_bytes(data)
    except xdr.XdrDecodeError:
        return
    assert decoded.to_xdr_bytes() == data


@pytest.mark.parametrize("union", sorted(DISCRIMINANTS))
def test_unknown_discriminant(union: str) -> None:
    # The same four bytes are valid for unions that switch on int32 and on uint32.
    unknown = next(v for v in range(2**31) if v not in DISCRIMINANTS[union])
    with pytest.raises(xdr.XdrDecodeError, match=f"unknown {union} discriminant"):
        decoder(union).from_xdr_bytes(struct.pack(">I", unknown) + bytes(64))
