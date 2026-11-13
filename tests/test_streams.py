"""Values that follow each other with no framing, as in contract metadata."""

import pytest

import stellar_xdr as xdr

ENTRIES = [
    xdr.SCMetaEntry.V0(xdr.SCMetaV0("rsver", "1.80.0")),
    xdr.SCMetaEntry.V0(xdr.SCMetaV0("rssdkver", "22.0.0")),
]


def test_round_trip() -> None:
    data = xdr.encode_stream(ENTRIES)
    assert data == b"".join(e.to_xdr_bytes() for e in ENTRIES)
    assert list(xdr.decode_stream(xdr.SCMetaEntry, data)) == ENTRIES


def test_structs_and_enums() -> None:
    parts = [xdr.UInt128Parts(1, 2), xdr.UInt128Parts(3, 4)]
    assert list(xdr.decode_stream(xdr.UInt128Parts, xdr.encode_stream(parts))) == parts
    types = [xdr.SCValType.SCV_U32, xdr.SCValType.SCV_VOID]
    assert list(xdr.decode_stream(xdr.SCValType, xdr.encode_stream(types))) == types


def test_empty() -> None:
    assert xdr.encode_stream([]) == b""
    assert list(xdr.decode_stream(xdr.SCMetaEntry, b"")) == []


def test_a_truncated_value_is_an_error() -> None:
    data = xdr.encode_stream(ENTRIES)
    values = xdr.decode_stream(xdr.SCMetaEntry, data[:-4])
    assert next(values) == ENTRIES[0]
    with pytest.raises(xdr.XdrDecodeError, match="exceeds the remaining input"):
        next(values)


def test_depth_is_counted_per_value() -> None:
    value: xdr.SCVal.Any = xdr.SCVal.Void()
    for _ in range(3):
        value = xdr.SCVal.Vec([value])
    data = xdr.encode_stream([value, value], max_depth=4)
    assert list(xdr.decode_stream(xdr.SCVal, data, max_depth=4)) == [value, value]
    with pytest.raises(xdr.XdrDepthError):
        xdr.encode_stream([value], max_depth=3)
    with pytest.raises(xdr.XdrDepthError):
        list(xdr.decode_stream(xdr.SCVal, data, max_depth=3))


def test_input_must_be_bytes() -> None:
    # The error comes from the call, not from the first value.
    with pytest.raises(TypeError, match="expected bytes"):
        xdr.decode_stream(xdr.SCVal, bytearray())  # type: ignore[arg-type]


def test_the_type_must_be_one_that_decodes() -> None:
    # An arm only encodes: decoding starts from its union.
    with pytest.raises(
        TypeError,
        match=r"^expected a struct, an enum, a union or a typedef, got SCVal\.U32$",
    ):
        xdr.decode_stream(xdr.SCVal.U32, b"")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"got str$"):
        xdr.decode_stream("SCVal", b"")  # type: ignore[arg-type]


def test_typedefs() -> None:
    numbers = [xdr.SequenceNumber(1), xdr.SequenceNumber(2)]
    data = xdr.encode_stream(numbers)
    assert data == bytes([0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 2])
    decoded = list(xdr.decode_stream(xdr.SequenceNumber, data))
    assert decoded == numbers
    assert type(decoded[0]) is xdr.SequenceNumber


def test_plain_values_have_no_type_to_encode_them_by() -> None:
    with pytest.raises(TypeError, match="expected a value of an XDR type, got int"):
        xdr.encode_stream([1])  # type: ignore[list-item]
