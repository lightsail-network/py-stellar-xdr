"""Typedefs are classes that extend the Python type of their values."""

import copy
import inspect
import pickle
import typing
from typing import Any

import pytest

import stellar_xdr as xdr

KEY = bytes(range(32))


def test_a_value_is_also_a_value_of_the_type_it_extends() -> None:
    key = xdr.Hash(KEY)
    assert isinstance(key, bytes)
    assert key == KEY
    assert hash(key) == hash(KEY)
    assert key.hex() == KEY.hex()
    assert type(key[:4]) is bytes
    number = xdr.SequenceNumber(5)
    assert number == 5
    assert type(number + 1) is int
    items = xdr.SCVec([xdr.SCVal.U32(1), xdr.SCVal.Void()])
    assert len(items) == 2
    assert items[1] == xdr.SCVal.Void()
    assert items == (xdr.SCVal.U32(1), xdr.SCVal.Void())
    assert xdr.SCSymbol("transfer").decode() == "transfer"


def test_constructors_check_the_value() -> None:
    with pytest.raises(ValueError, match=r"^Hash: expected 32 bytes, got 3$"):
        xdr.Hash(b"abc")
    with pytest.raises(TypeError, match=r"^Hash: expected bytes, got str$"):
        xdr.Hash("abc")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"^SCSymbol: expected at most 32 bytes"):
        xdr.SCSymbol("x" * 33)
    with pytest.raises(
        ValueError, match=r"^SequenceNumber: .* out of range for int64$"
    ):
        xdr.SequenceNumber(2**63)
    with pytest.raises(TypeError, match=r"^SCVec\[1\]: expected SCVal\.Any, got int$"):
        xdr.SCVec([xdr.SCVal.Void(), 1])  # type: ignore[list-item]
    with pytest.raises(
        ValueError, match=r"^TxAdvertVector: expected at most 1000 items"
    ):
        xdr.TxAdvertVector([KEY] * 1001)


def test_a_value_of_the_type_is_returned_as_it_is() -> None:
    key = xdr.Hash(KEY)
    assert xdr.Hash(key) is key
    items = xdr.SCVec([xdr.SCVal.Void()])
    assert xdr.SCVal.Vec(items).vec is items


def test_items_and_fields_are_stored_as_their_types() -> None:
    hashes = xdr.TxAdvertVector([KEY])
    assert type(hashes[0]) is xdr.Hash
    stage = xdr.ParallelTxExecutionStage([[]])
    assert type(stage[0]) is xdr.DependentTxCluster
    entry = xdr.TTLEntry(KEY, 1)
    assert type(entry.key_hash) is xdr.Hash
    assert type(entry.live_until_ledger_seq) is int


def test_decoding_gives_the_types_too() -> None:
    address = xdr.SCAddress.Contract(KEY)
    for decoded in [
        xdr.SCAddress.from_xdr_bytes(address.to_xdr_bytes()),
        xdr.SCAddress.from_json_value(address.to_json_value()),
    ]:
        assert isinstance(decoded, xdr.SCAddress.Contract)
        assert type(decoded.contract_id) is xdr.ContractID
    value = xdr.SCVal.Vec([xdr.SCVal.Symbol("a")])
    for value_again in [
        xdr.SCVal.from_xdr_bytes(value.to_xdr_bytes()),
        xdr.SCVal.from_json_value(value.to_json_value()),
    ]:
        assert isinstance(value_again, xdr.SCVal.Vec)
        assert type(value_again.vec) is xdr.SCVec
        assert value_again.vec is not None
        symbol = value_again.vec[0]
        assert isinstance(symbol, xdr.SCVal.Symbol)
        assert type(symbol.sym) is xdr.SCSymbol


def test_values_encode_and_decode_themselves() -> None:
    items = xdr.SCVec([xdr.SCVal.Void()])
    assert items.to_xdr_bytes() == bytes([0, 0, 0, 1, 0, 0, 0, 1])
    assert items.to_xdr_base64() == "AAAAAQAAAAE="
    assert xdr.SCVec.from_xdr_base64("AAAAAQAAAAE=") == items
    assert xdr.LedgerEntryChanges.from_xdr_base64("AAAAAA==") == ()
    assert xdr.Thresholds(b"\1\2\3\4").to_xdr_bytes() == b"\1\2\3\4"
    assert xdr.String32("a").to_xdr_bytes() == b"\0\0\0\1a\0\0\0"
    assert xdr.SequenceNumber.from_xdr_bytes(bytes(7) + b"\5") == 5


def test_decoding_is_strict() -> None:
    with pytest.raises(xdr.XdrDecodeError, match="unexpected bytes after the value"):
        xdr.SequenceNumber.from_xdr_bytes(bytes(12))
    with pytest.raises(xdr.XdrDecodeError, match="non-zero padding"):
        xdr.String32.from_xdr_bytes(b"\0\0\0\1a\0\0\1")


def test_depth_is_limited() -> None:
    value: xdr.SCVal.Any = xdr.SCVal.Void()
    for _ in range(3):
        value = xdr.SCVal.Vec([value])
    with pytest.raises(xdr.XdrDepthError):
        xdr.SCVec([value]).to_xdr_bytes(max_depth=3)
    data = xdr.SCVec([value]).to_xdr_bytes()
    with pytest.raises(xdr.XdrDepthError, match="max_depth=3"):
        xdr.SCVec.from_xdr_bytes(data, max_depth=3)


def test_repr_names_the_type_of_a_value_by_itself() -> None:
    assert repr(xdr.SignatureHint(b"abcd")) == "SignatureHint(b'abcd')"
    assert repr(xdr.SequenceNumber(5)) == "SequenceNumber(5)"
    assert repr(xdr.SCVec([])) == "SCVec(())"
    assert repr(xdr.SCVec([xdr.SCVal.U32(1)])) == "SCVec((SCVal.U32(1),))"
    assert repr(xdr.TxAdvertVector([KEY[:1] * 32] * 2)) == (
        f"TxAdvertVector(({bytes(32)!r}, {bytes(32)!r}))"
    )
    # str() and format() of an integer give the number.
    assert str(xdr.SequenceNumber(5)) == "5"
    assert f"{xdr.SequenceNumber(5)}" == "5"


def test_repr_shows_the_plain_value_inside_another_value() -> None:
    assert repr(xdr.DecoratedSignature(b"abcd", b"xy")) == (
        "DecoratedSignature(hint=b'abcd', signature=b'xy')"
    )
    assert repr(xdr.SCVal.TimePoint(5)) == "SCVal.TimePoint(5)"
    assert repr(xdr.SCVal.Vec([xdr.SCVal.Symbol("a")])) == (
        "SCVal.Vec((SCVal.Symbol(b'a'),))"
    )


def test_values_are_immutable() -> None:
    key = xdr.Hash(KEY)
    with pytest.raises(AttributeError):
        key.extra = 1  # type: ignore[attr-defined]
    assert copy.copy(key) is key
    assert copy.deepcopy(key) is key
    items = xdr.SCVec([xdr.SCVal.Void()])
    assert copy.deepcopy(items) is items


def test_pickle_keeps_the_type() -> None:
    values = [xdr.Hash(KEY), xdr.SequenceNumber(5), xdr.SCVec([xdr.SCVal.Void()])]
    for value in values:
        for protocol in range(pickle.HIGHEST_PROTOCOL + 1):
            again = pickle.loads(pickle.dumps(value, protocol))  # noqa: S301
            assert again == value
            assert type(again) is type(value)


def test_typedef_classes_cant_be_subclassed() -> None:
    with pytest.raises(TypeError, match="can't be subclassed"):

        class Child(xdr.Hash):  # type: ignore[misc]
            __slots__ = ()


def test_a_class_without_slots_is_rejected() -> None:
    with pytest.raises(TypeError, match="must define __slots__"):

        class Broken(xdr.XdrBytes):  # pyright: ignore[reportUnusedClass]
            pass


ALIASES = ["Uint32", "Int32", "Uint64", "Int64"]


@pytest.mark.parametrize("name", ALIASES)
def test_a_typedef_that_cannot_be_a_class_is_a_type_alias(name: str) -> None:
    alias: Any = getattr(xdr, name)
    assert alias.__name__ == name
    # Another name for int would convert where it should check: 1.9 would become 1.
    with pytest.raises(TypeError):
        alias(1)
    with pytest.raises(TypeError):
        isinstance(1, alias)


def test_reflection_gives_the_alias_whose_value_is_the_type() -> None:
    hints = typing.get_type_hints(xdr.Price)
    assert (hints["n"], hints["d"]) == (xdr.Int32, xdr.Int32)
    assert hints["n"].__value__ is int
    assert xdr.Uint64.__value__ is int


def test_an_optional_typedef_is_the_union_with_none() -> None:
    # As the type it names, it can't be called, and isinstance checks it correctly.
    assert xdr.SponsorshipDescriptor == xdr.PublicKey.Any | None
    assert isinstance(None, xdr.SponsorshipDescriptor)
    assert isinstance(xdr.PublicKey.Ed25519(KEY), xdr.SponsorshipDescriptor)
    assert not isinstance(5, xdr.SponsorshipDescriptor)


def test_a_field_of_an_alias_holds_a_plain_value_checked_by_its_xdr_type() -> None:
    # struct Price { int32 n; int32 d; };
    assert inspect.get_annotations(xdr.Price) == {"n": "Int32", "d": "Int32"}
    assert type(xdr.Price(1, 2).n) is int
    with pytest.raises(
        ValueError, match=r"Price\.n: 2147483648 is out of range for int32"
    ):
        xdr.Price(2**31, 1)
    with pytest.raises(TypeError, match=r"Price\.n: expected int, got float"):
        xdr.Price(1.9, 1)  # type: ignore[arg-type]


def test_a_typedef_of_a_union_is_the_union() -> None:
    # Its arms, its Any and its decoding.
    assert xdr.AccountID is xdr.PublicKey
    account = xdr.AccountID.Ed25519(KEY)
    assert xdr.AccountID.from_xdr_bytes(account.to_xdr_bytes()) == account
    assert isinstance(account, xdr.AccountID.Any)
