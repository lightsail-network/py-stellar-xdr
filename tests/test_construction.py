"""Constructors check their arguments, so that any value that exists can be encoded."""

import pytest

import stellar_xdr as xdr
from stellar_xdr._runtime import check

KEY = bytes(range(32))


def test_integers_are_range_checked() -> None:
    assert xdr.SCVal.U32(2**32 - 1).u32 == 2**32 - 1
    assert xdr.SCVal.I32(-(2**31)).i32 == -(2**31)
    assert xdr.SCVal.U64(2**64 - 1).u64 == 2**64 - 1
    assert xdr.SCVal.I64(-(2**63)).i64 == -(2**63)
    for make, value in [
        (xdr.SCVal.U32, -1),
        (xdr.SCVal.U32, 2**32),
        (xdr.SCVal.I32, 2**31),
        (xdr.SCVal.U64, 2**64),
        (xdr.SCVal.I64, -(2**63) - 1),
    ]:
        with pytest.raises(ValueError, match="out of range"):
            make(value)


def test_integers_reject_other_types() -> None:
    for value in [True, 1.0, "1", None]:
        with pytest.raises(TypeError, match=r"SCVal\.U32\.u32: expected int"):
            xdr.SCVal.U32(value)  # type: ignore[arg-type]


def test_an_int_subclass_is_stored_as_a_plain_int() -> None:
    value = xdr.SCVal.U32(xdr.SCValType.SCV_U32)
    assert value.u32.__class__ is int


def test_booleans_must_be_bool() -> None:
    assert xdr.SCVal.Bool(True).b is True  # noqa: FBT003
    with pytest.raises(TypeError, match="expected bool"):
        xdr.SCVal.Bool(1)  # type: ignore[arg-type]


def test_fixed_opaque_needs_the_exact_length() -> None:
    assert xdr.SCAddress.Contract(xdr.ContractID(KEY)).contract_id == KEY
    with pytest.raises(ValueError, match="expected 32 bytes, got 31"):
        xdr.SCAddress.Contract(xdr.ContractID(KEY[:31]))
    with pytest.raises(TypeError, match="expected bytes, got bytearray"):
        xdr.SCAddress.Contract(bytearray(KEY))  # type: ignore[arg-type]


def test_a_bytes_subclass_is_stored_as_plain_bytes() -> None:
    class Key(bytes):
        pass

    assert xdr.SCAddress.Contract(Key(KEY)).contract_id.__class__ is bytes  # type: ignore[arg-type]


def test_variable_opaque_has_a_maximum() -> None:
    assert xdr.Memo.Text(b"x" * 28).text == b"x" * 28
    with pytest.raises(ValueError, match="at most 28 bytes, got 29"):
        xdr.Memo.Text(b"x" * 29)


def test_strings_accept_str_and_store_utf8() -> None:
    assert xdr.SCVal.Symbol("transfer").sym == b"transfer"
    assert xdr.Memo.Text("é").text == "é".encode()
    # The limit applies to the encoded bytes.
    with pytest.raises(ValueError, match="at most 28 bytes, got 30"):
        xdr.Memo.Text("é" * 15)
    with pytest.raises(TypeError, match="expected bytes or str, got int"):
        xdr.Memo.Text(1)  # type: ignore[arg-type]


def test_enum_fields_need_a_member() -> None:
    error = xdr.SCError.WasmVm(xdr.SCErrorCode.SCEC_ARITH_DOMAIN)
    assert error.code is xdr.SCErrorCode.SCEC_ARITH_DOMAIN
    with pytest.raises(TypeError, match="expected SCErrorCode, got int"):
        xdr.SCError.WasmVm(0)  # type: ignore[arg-type]


def test_struct_fields_need_an_instance_of_the_struct() -> None:
    entry = xdr.SCMapEntry(xdr.SCVal.U32(1), xdr.SCVal.Void())
    assert xdr.SCVal.Map((entry,)).map == (entry,)
    with pytest.raises(TypeError, match=r"SCVal\.Map\.map\[0\]: expected SCMapEntry"):
        xdr.SCVal.Map(((xdr.SCVal.U32(1), xdr.SCVal.Void()),))  # type: ignore[arg-type]


def test_union_fields_need_an_arm_of_the_union() -> None:
    with pytest.raises(TypeError, match=r"SCMapEntry\.key: expected SCVal\.Any"):
        xdr.SCMapEntry(xdr.SCAddress.Contract(xdr.Hash(KEY)), xdr.SCVal.Void())  # type: ignore[arg-type]


def test_arrays_accept_any_sequence_and_store_a_tuple() -> None:
    items = [xdr.SCVal.U32(1), xdr.SCVal.U32(2)]
    assert xdr.SCVal.Vec(items).vec == tuple(items)
    assert xdr.SCVal.Vec(range(0)).vec == ()  # type: ignore[arg-type]


def test_arrays_reject_strings_iterators_and_mappings() -> None:
    values: list[object] = [b"\x01", "a", iter([]), {}, {1}]
    for value in values:
        with pytest.raises(TypeError, match="expected a sequence"):
            xdr.SCVal.Vec(value)  # type: ignore[arg-type]


def test_arrays_report_the_index_of_a_bad_item() -> None:
    with pytest.raises(TypeError, match=r"SCVal\.Vec\.vec\[1\]: expected SCVal\.Any"):
        xdr.SCVal.Vec([xdr.SCVal.Void(), 1])  # type: ignore[list-item]


def test_arrays_have_a_maximum() -> None:
    # A claim predicate combines at most two predicates.
    predicate = xdr.ClaimPredicate.Unconditional()
    with pytest.raises(ValueError, match="at most 2 items, got 3"):
        xdr.ClaimPredicate.And([predicate] * 3)


def test_fixed_arrays_need_the_exact_count() -> None:
    assert (
        check.array_fixed([KEY] * 4, "skip_list", 4, check.opaque_fixed, 32)
        == (KEY,) * 4
    )
    with pytest.raises(ValueError, match="expected 4 items, got 3"):
        check.array_fixed([KEY] * 3, "skip_list", 4, check.opaque_fixed, 32)


def test_optional_values_accept_none() -> None:
    assert xdr.SCVal.Vec(None).vec is None
    assert xdr.ClaimPredicate.Not(None).not_predicate is None
    with pytest.raises(TypeError, match=r"expected ClaimPredicate\.Any"):
        xdr.ClaimPredicate.Not(1)  # type: ignore[arg-type]


def test_arguments_can_be_given_by_keyword() -> None:
    assert xdr.UInt128Parts(lo=2, hi=1) == xdr.UInt128Parts(1, 2)
    with pytest.raises(TypeError):
        xdr.UInt128Parts(1)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        xdr.SCVal.Void(1)  # type: ignore[call-arg]


def test_hostile_arguments_raise_the_documented_error() -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        xdr.SCVal.Symbol("\ud800")
    # str() refuses integers of more than 4,300 digits.
    with pytest.raises(ValueError, match="a huge number is out of range"):
        xdr.SCVal.U32(10**5000)
