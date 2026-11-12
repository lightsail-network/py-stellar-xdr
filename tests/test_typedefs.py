"""Typedefs are type aliases; their codecs live in `stellar_xdr.typedefs`."""

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

import stellar_xdr as xdr
from stellar_xdr import typedefs

from .strategies import TYPEDEFS


@pytest.mark.parametrize("name", sorted(TYPEDEFS))
@given(data=st.data())
def test_round_trip(name: str, data: st.DataObject) -> None:
    codec: Any = getattr(typedefs, name)
    value = data.draw(TYPEDEFS[name])
    encoded = codec.to_xdr_bytes(value)
    assert codec.from_xdr_bytes(encoded) == value
    assert codec.from_xdr_base64(codec.to_xdr_base64(value)) == value
    assert codec.from_json_value(codec.to_json_value(value)) == value


def test_values_are_checked_before_encoding() -> None:
    assert typedefs.SCVec.to_xdr_bytes([xdr.SCVal.Void()]) == bytes(
        [0, 0, 0, 1, 0, 0, 0, 1]
    )
    with pytest.raises(ValueError, match="uint32: -1 is out of range"):
        typedefs.Uint32.to_xdr_bytes(-1)
    with pytest.raises(TypeError, match=r"SCVec\[0\]: expected SCVal\.Any"):
        typedefs.SCVec.to_xdr_bytes([1])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="expected 32 bytes"):
        typedefs.Hash.to_xdr_bytes(xdr.Hash(b""))


def test_decoding_is_strict() -> None:
    with pytest.raises(xdr.XdrDecodeError, match="unexpected bytes after the value"):
        typedefs.Uint32.from_xdr_bytes(bytes(8))


def test_depth_is_limited() -> None:
    value: xdr.SCVal.Any = xdr.SCVal.Void()
    for _ in range(3):
        value = xdr.SCVal.Vec([value])
    with pytest.raises(xdr.XdrDepthError):
        typedefs.SCVec.to_xdr_bytes([value], max_depth=3)
    data = typedefs.SCVec.to_xdr_bytes([value])
    with pytest.raises(xdr.XdrDepthError, match="max_depth=3"):
        typedefs.SCVec.from_xdr_bytes(data, max_depth=3)


def test_repr() -> None:
    assert repr(typedefs.LedgerEntryChanges) == "<typedef LedgerEntryChanges>"
