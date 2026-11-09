"""Decoding is strict: anything but the canonical encoding of a value is rejected."""

import struct

import pytest

import stellar_xdr as xdr


def u32(*values: int) -> bytes:
    return b"".join(struct.pack(">I", v) for v in values)


SYMBOL = xdr.SCValType.SCV_SYMBOL
VEC = xdr.SCValType.SCV_VEC
BOOL = xdr.SCValType.SCV_BOOL


def test_decode_a_value() -> None:
    assert xdr.SCVal.from_xdr_bytes(u32(SYMBOL, 2) + b"ab\0\0") == xdr.SCVal.Symbol(
        "ab"
    )
    assert xdr.SCVal.from_xdr_base64("AAAABQAAAAAAAAAB") == xdr.SCVal.U64(1)
    assert xdr.SCVal.from_xdr_base64(b"AAAABQAAAAAAAAAB") == xdr.SCVal.U64(1)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (u32(BOOL, 2), "invalid bool 2 at offset 4"),
        (u32(VEC, 2), "invalid optional flag 2 at offset 4"),
        (u32(SYMBOL, 2) + b"ab\0\1", "non-zero padding at offset 10"),
        (u32(SYMBOL, 33) + bytes(36), "length 33 exceeds the maximum 32 at offset 4"),
        (u32(SYMBOL, 8) + bytes(4), "length 8 exceeds the remaining input at offset 4"),
        (u32(SYMBOL, 2) + b"ab", "unexpected end of input at offset 8"),
        (
            u32(VEC, 1, 1000),
            "array length 1000 exceeds the remaining input at offset 8",
        ),
        (u32(BOOL), "unexpected end of input at offset 4"),
        (u32(BOOL, 1, 0), "4 unexpected bytes after the value at offset 8"),
        (u32(99), "unknown SCVal discriminant 99 at offset 0"),
        (b"", "unexpected end of input at offset 0"),
    ],
)
def test_invalid_encodings_are_rejected(data: bytes, message: str) -> None:
    with pytest.raises(xdr.XdrDecodeError, match=f"^{message}$"):
        xdr.SCVal.from_xdr_bytes(data)


def test_arrays_have_a_maximum() -> None:
    # A claim predicate combines at most two predicates.
    and_ = xdr.ClaimPredicateType.CLAIM_PREDICATE_AND
    unconditional = xdr.ClaimPredicateType.CLAIM_PREDICATE_UNCONDITIONAL
    data = u32(and_, 3, unconditional, unconditional, unconditional)
    with pytest.raises(
        xdr.XdrDecodeError, match="array length 3 exceeds the maximum 2"
    ):
        xdr.ClaimPredicate.from_xdr_bytes(data)


def test_enums_reject_unknown_values() -> None:
    assert xdr.SCValType.from_xdr_bytes(u32(3)) is xdr.SCValType.SCV_U32
    assert xdr.SCValType.from_xdr_base64("AAAAAw==") is xdr.SCValType.SCV_U32
    with pytest.raises(
        xdr.XdrDecodeError, match=r"^unknown SCValType value 99 at offset 0$"
    ):
        xdr.SCValType.from_xdr_bytes(u32(99))


def test_enums_encode() -> None:
    assert xdr.SCValType.SCV_U32.to_xdr_bytes() == u32(3)
    assert xdr.SCValType.SCV_U32.to_xdr_base64() == "AAAAAw=="


def test_structs_decode() -> None:
    assert xdr.UInt128Parts.from_xdr_bytes(bytes(15) + b"\1") == xdr.UInt128Parts(0, 1)
    assert xdr.UInt128Parts.from_xdr_base64("A" * 21 + "Q==") == xdr.UInt128Parts(0, 1)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("AAAAAR==", "not canonical"),
        ("AAAAAQ", "Incorrect padding"),
        ("AAAA AAE=", "Only base64 data"),
        ("AAAAAQ==\n", "Excess data after padding|Only base64 data"),
        ("AAAAÀ===", "non-ASCII character"),
    ],
)
def test_base64_must_be_canonical(text: str, message: str) -> None:
    with pytest.raises(xdr.XdrDecodeError, match=f"invalid base64: ({message})"):
        xdr.SCValType.from_xdr_base64(text)


def test_input_must_be_bytes() -> None:
    with pytest.raises(TypeError, match="expected bytes, got bytearray"):
        xdr.SCVal.from_xdr_bytes(bytearray(8))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="expected str or bytes, got int"):
        xdr.SCVal.from_xdr_base64(1)  # type: ignore[arg-type]


def nested_vec(depth: int) -> xdr.SCVal.Any:
    value: xdr.SCVal.Any = xdr.SCVal.Void()
    for _ in range(depth):
        value = xdr.SCVal.Vec([value])
    return value


def test_depth_counts_recursive_types() -> None:
    # Five vectors around a void: six SCVal levels.
    value = nested_vec(5)
    data = value.to_xdr_bytes(max_depth=6)
    assert xdr.SCVal.from_xdr_bytes(data, max_depth=6) == value
    with pytest.raises(xdr.XdrDecodeError, match="nesting deeper than max_depth=5"):
        xdr.SCVal.from_xdr_bytes(data, max_depth=5)
    with pytest.raises(xdr.XdrDepthError, match="nested deeper than max_depth=5"):
        value.to_xdr_bytes(max_depth=5)
    with pytest.raises(xdr.XdrDepthError):
        value.to_xdr_base64(max_depth=5)


def test_the_default_depth_accepts_what_soroban_accepts() -> None:
    value = nested_vec(150)
    assert xdr.SCVal.from_xdr_bytes(value.to_xdr_bytes()) == value


def test_recursion_beyond_python_limits_is_an_error() -> None:
    data = u32(VEC, 1) * 3000 + u32(xdr.SCValType.SCV_VOID)
    with pytest.raises(xdr.XdrDecodeError, match="recursion limit"):
        xdr.SCVal.from_xdr_bytes(data, max_depth=10_000)
    value = nested_vec(3000)
    with pytest.raises(xdr.XdrDepthError, match="recursion limit"):
        value.to_xdr_bytes(max_depth=10_000)


def test_errors_are_value_errors() -> None:
    assert issubclass(xdr.XdrDecodeError, xdr.XdrError)
    assert issubclass(xdr.XdrJsonError, xdr.XdrError)
    assert issubclass(xdr.XdrDepthError, xdr.XdrError)
    assert issubclass(xdr.XdrError, ValueError)


@pytest.mark.parametrize(
    ("max_depth", "error"),
    [(True, TypeError), (1.5, TypeError), (float("nan"), TypeError), (-1, ValueError)],
)
def test_max_depth_is_checked(max_depth: object, error: type[Exception]) -> None:
    value = xdr.SCVal.Void()
    with pytest.raises(error, match="max_depth"):
        xdr.SCVal.from_xdr_bytes(value.to_xdr_bytes(), max_depth=max_depth)  # type: ignore[arg-type]
    with pytest.raises(error, match="max_depth"):
        value.to_xdr_bytes(max_depth=max_depth)  # type: ignore[arg-type]
    with pytest.raises(error, match="max_depth"):
        value.to_json_value(max_depth=max_depth)  # type: ignore[arg-type]
    with pytest.raises(error, match="max_depth"):
        xdr.SCVal.from_json_value("void", max_depth=max_depth)  # type: ignore[arg-type]
