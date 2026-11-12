"""How values behave as Python objects: immutable, comparable, printable, copyable."""

import copy
import dataclasses
import pickle
import sys

import pytest

import stellar_xdr as xdr
from stellar_xdr._runtime import XdrStruct


def test_values_are_immutable() -> None:
    value = xdr.UInt128Parts(1, 2)
    with pytest.raises(dataclasses.FrozenInstanceError, match=r"copy\.replace"):
        value.hi = 3  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        del value.hi  # pyright: ignore[reportAttributeAccessIssue]
    with pytest.raises(AttributeError):
        value.extra = 1  # type: ignore[attr-defined]


def test_equality_and_hashing_follow_the_fields_and_the_class() -> None:
    assert xdr.SCVal.U32(5) == xdr.SCVal.U32(5)
    assert xdr.SCVal.U32(5) != xdr.SCVal.I32(5)
    assert xdr.SCVal.Void() == xdr.SCVal.Void()
    assert xdr.SCVal.Void() != xdr.Memo.None_()
    assert len({xdr.SCVal.U32(5), xdr.SCVal.U32(5), xdr.SCVal.I32(5)}) == 2
    # Void arms of different unions don't share a hash.
    assert hash(xdr.SCVal.Void()) != hash(xdr.Memo.None_())


def test_repr_shows_a_struct_with_its_fields() -> None:
    assert repr(xdr.UInt128Parts(1, 2)) == "UInt128Parts(hi=1, lo=2)"
    entry = xdr.SCMapEntry(xdr.SCVal.U32(1), xdr.SCVal.Void())
    assert repr(entry) == "SCMapEntry(key=SCVal.U32(1), val=SCVal.Void())"


def test_repr_shows_an_arm_with_its_value_alone() -> None:
    assert repr(xdr.SCVal.Symbol("a")) == "SCVal.Symbol(b'a')"
    assert repr(xdr.SCVal.Void()) == "SCVal.Void()"
    assert repr(xdr.SCVal.Vec(None)) == "SCVal.Vec(None)"
    assert repr(xdr.SCVal.Vec([xdr.SCVal.U32(1)])) == "SCVal.Vec((SCVal.U32(1),))"
    parts = xdr.SCVal.I128(xdr.Int128Parts(0, 1))
    assert repr(parts) == "SCVal.I128(Int128Parts(hi=0, lo=1))"


def test_repr_shows_an_enum_member_by_name() -> None:
    assert repr(xdr.SCValType.SCV_U32) == "SCValType.SCV_U32"
    error = xdr.SCError.WasmVm(xdr.SCErrorCode.SCEC_ARITH_DOMAIN)
    assert repr(error) == "SCError.WasmVm(SCErrorCode.SCEC_ARITH_DOMAIN)"
    # str() is unchanged: an IntEnum member formats as its number.
    assert str(xdr.SCValType.SCV_U32) == "3"


def test_repr_evaluates_back_to_the_value() -> None:
    value = xdr.SCVal.Map(
        [
            xdr.SCMapEntry(
                xdr.SCVal.Symbol("error"),
                xdr.SCVal.Error(xdr.SCError.WasmVm(xdr.SCErrorCode.SCEC_ARITH_DOMAIN)),
            ),
            xdr.SCMapEntry(xdr.SCVal.Bytes(b"\x00\xff"), xdr.SCVal.Vec(None)),
        ]
    )
    assert eval(repr(value), dict(vars(xdr))) == value  # noqa: S307 - our own repr


def test_match_with_class_patterns() -> None:
    def describe(value: xdr.SCVal.Any) -> str:
        match value:
            case xdr.SCVal.U32(n):
                return f"u32 {n}"
            case xdr.SCVal.Vec(items):
                return f"vec of {len(items or ())}"
            case _:
                return "other"

    assert describe(xdr.SCVal.U32(5)) == "u32 5"
    assert describe(xdr.SCVal.Vec([xdr.SCVal.Void()])) == "vec of 1"
    assert describe(xdr.SCVal.Void()) == "other"
    assert xdr.UInt128Parts.__match_args__ == ("hi", "lo")


def test_the_discriminant_is_a_class_attribute() -> None:
    assert xdr.SCVal.U32(5).type is xdr.SCValType.SCV_U32
    assert xdr.SCVal.U32.type is xdr.SCValType.SCV_U32
    assert xdr.TransactionExt.V0().v == 0


def test_replace_builds_a_checked_copy() -> None:
    value = xdr.UInt128Parts(1, 2)
    assert xdr.replace(value, lo=3) == xdr.UInt128Parts(1, 3)
    assert value == xdr.UInt128Parts(1, 2)
    with pytest.raises(ValueError, match="out of range"):
        xdr.replace(value, lo=-1)
    with pytest.raises(TypeError):
        xdr.replace(value, missing=1)


@pytest.mark.skipif(sys.version_info < (3, 13), reason="copy.replace needs 3.13")
def test_copy_replace() -> None:
    replace = copy.replace  # type: ignore[attr-defined]
    assert replace(xdr.SCVal.U32(1), u32=2) == xdr.SCVal.U32(2)


def test_copies_share_the_immutable_value() -> None:
    value = xdr.SCVal.Vec([xdr.SCVal.U32(1)])
    assert copy.copy(value) is value
    assert copy.deepcopy(value) is value


def test_pickle_round_trips_nested_classes() -> None:
    value = xdr.SCVal.Vec([xdr.SCVal.Symbol("a"), xdr.SCVal.Void()])
    for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
        assert pickle.loads(pickle.dumps(value, protocol)) == value  # noqa: S301


def test_a_union_is_a_namespace_not_a_type() -> None:
    with pytest.raises(
        TypeError, match=r"use SCVal\.Any or an arm such as SCVal\.Bool"
    ):
        isinstance(xdr.SCVal.U32(1), xdr.SCVal)  # pyright: ignore[reportUnnecessaryIsInstance]
    with pytest.raises(TypeError, match="namespace, not a type"):
        issubclass(xdr.SCVal.U32, xdr.SCVal)  # pyright: ignore[reportUnnecessaryIsInstance]
    with pytest.raises(TypeError, match="can't be instantiated"):
        xdr.SCVal()
    assert isinstance(xdr.SCVal.U32(1), xdr.SCVal.Any)


def test_generated_classes_cant_be_subclassed() -> None:
    with pytest.raises(TypeError, match="can't be subclassed"):

        class Child(xdr.SCVal.U32):  # type: ignore[misc]
            __slots__ = ()


def test_a_class_without_slots_is_rejected() -> None:
    with pytest.raises(TypeError, match="must define __slots__"):

        class Broken(XdrStruct):  # pyright: ignore[reportUnusedClass]
            pass


def test_values_are_not_dataclasses() -> None:
    # Type checkers treat them as frozen dataclasses, but the runtime doesn't.
    assert not dataclasses.is_dataclass(xdr.UInt128Parts(1, 2))
