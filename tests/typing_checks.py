"""What type checkers see in code that uses the package.

Not run by pytest: mypy and pyright check it as part of `make typecheck`. Each
`# type: ignore[...]` marks an error that must be reported; both checkers fail on an
ignore that is not needed, so a missing error fails the check too.
"""

import copy
import sys
from typing import assert_never, assert_type

import stellar_xdr as xdr


def construction() -> None:
    assert_type(xdr.SCVal.U32(5), xdr.SCVal.U32)
    assert_type(xdr.SCVal.U32(5).u32, int)
    assert_type(xdr.SCVal.Symbol("transfer").sym, xdr.SCSymbol)
    assert_type(xdr.SCVal.Vec([xdr.SCVal.Void()]).vec, xdr.SCVec | None)
    xdr.SCVal.U32("5")  # type: ignore[arg-type]
    xdr.UInt128Parts(1)  # type: ignore[call-arg]
    # A constructor takes the plain value and stores the typedef's.
    assert_type(xdr.SCAddress.Contract(bytes(32)).contract_id, xdr.ContractID)
    xdr.SCAddress.Contract(xdr.ContractID(bytes(32)))
    xdr.SCAddress.Contract("C...")  # type: ignore[arg-type]


def typedefs(value: xdr.SCVal.Vec, key: xdr.Hash, number: xdr.SequenceNumber) -> None:
    # A typedef's value is also a value of the type it extends.
    assert_type(key[:4], bytes)
    assert_type(key.hex(), str)
    assert_type(number + 1, int)
    if value.vec is not None:
        assert_type(value.vec[0], xdr.SCVal.Any)
        assert_type(len(value.vec), int)
    assert_type(xdr.Hash(bytes(32)), xdr.Hash)
    assert_type(xdr.SCVec([xdr.SCVal.Void()]), xdr.SCVec)
    xdr.SCVec([1])  # type: ignore[list-item]
    assert_type(xdr.Hash.from_xdr_bytes(bytes(32)), xdr.Hash)
    assert_type(key.to_xdr_bytes(), bytes)
    # A typedef of a union is the union under another name.
    account: xdr.AccountID.Any = xdr.PublicKey.Ed25519(bytes(32))
    assert_type(xdr.AccountID.from_xdr_bytes(account.to_xdr_bytes()), xdr.PublicKey.Any)


def immutability(value: xdr.UInt128Parts) -> None:
    value.hi = 1  # type: ignore[misc]


def decoding(data: bytes) -> None:
    assert_type(xdr.SCVal.from_xdr_bytes(data), xdr.SCVal.Any)
    assert_type(
        xdr.TransactionEnvelope.from_xdr_base64("..."), xdr.TransactionEnvelope.Any
    )
    assert_type(xdr.UInt128Parts.from_xdr_bytes(data), xdr.UInt128Parts)
    assert_type(xdr.SCValType.from_xdr_bytes(data), xdr.SCValType)
    assert_type(xdr.LedgerEntryChanges.from_xdr_bytes(data), xdr.LedgerEntryChanges)
    assert_type(
        xdr.LedgerEntryChanges.from_xdr_bytes(data)[0], xdr.LedgerEntryChange.Any
    )
    assert_type(
        list(xdr.decode_stream(xdr.SCSpecEntry, data)), list[xdr.SCSpecEntry.Any]
    )
    assert_type(xdr.SCVal.U32(1).to_xdr_base64(), str)


def narrowing(value: xdr.SCVal.Any) -> None:
    if value.type == xdr.SCValType.SCV_U32:
        assert_type(value, xdr.SCVal.U32)
    match value:
        case xdr.SCVal.U32(n):
            assert_type(n, int)
        case xdr.SCVal.Vec(items):
            assert_type(items, xdr.SCVec | None)
        case _:
            pass


def exhaustive(value: xdr.MuxedAccount.Any) -> str:
    match value:
        case xdr.MuxedAccount.Ed25519(key):
            return key.hex()
        case xdr.MuxedAccount.MuxedEd25519(med25519):
            return str(med25519.id)
        case _:
            assert_never(value)


def base_classes(value: xdr.XdrValue, record: xdr.XdrStruct | xdr.XdrArm) -> None:
    # Code that works on values of more than one type names the base classes.
    assert_type(value.to_xdr_bytes(), bytes)
    assert_type(type(record).__match_args__, tuple[str, ...])
    kinds: list[xdr.XdrValue] = [
        xdr.Price(1, 2),
        xdr.SCVal.U32(1),
        xdr.SCValType.SCV_U32,
        xdr.Hash(bytes(32)),
        xdr.SequenceNumber(1),
        xdr.SCVec([]),
    ]
    assert_type(xdr.encode_stream(kinds), bytes)
    xdr.encode_stream([5])  # type: ignore[list-item]


def replacing(value: xdr.UInt128Parts) -> None:
    assert_type(xdr.replace(value, lo=1), xdr.UInt128Parts)
    if sys.version_info >= (3, 13):
        assert_type(copy.replace(value, lo=1), xdr.UInt128Parts)
