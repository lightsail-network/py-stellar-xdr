"""What type checkers see in code that uses the package.

Not run by pytest: mypy and pyright check it as part of `make typecheck`. Each
`# type: ignore[...]` marks an error that must be reported; both checkers fail on an
ignore that is not needed, so a missing error fails the check too.
"""

import copy
import sys
from typing import assert_never, assert_type

import stellar_xdr as xdr
from stellar_xdr import typedefs


def construction() -> None:
    assert_type(xdr.SCVal.U32(5), xdr.SCVal.U32)
    assert_type(xdr.SCVal.U32(5).u32, int)
    assert_type(xdr.SCVal.Symbol("transfer").sym, bytes)
    assert_type(xdr.SCVal.Vec([xdr.SCVal.Void()]).vec, tuple[xdr.SCVal.Any, ...] | None)
    xdr.SCVal.U32("5")  # type: ignore[arg-type]
    xdr.UInt128Parts(1)  # type: ignore[call-arg]
    xdr.SCAddress.Contract(bytes(32))  # type: ignore[arg-type]
    xdr.SCAddress.Contract(xdr.ContractID(bytes(32)))
    # A pool ID or a plain hash is not a contract ID.
    xdr.SCAddress.Contract(xdr.PoolID(bytes(32)))  # type: ignore[arg-type]
    xdr.SCAddress.Contract(xdr.Hash(bytes(32)))  # type: ignore[arg-type]


def immutability(value: xdr.UInt128Parts) -> None:
    value.hi = 1  # type: ignore[misc]


def decoding(data: bytes) -> None:
    assert_type(xdr.SCVal.from_xdr_bytes(data), xdr.SCVal.Any)
    assert_type(
        xdr.TransactionEnvelope.from_xdr_base64("..."), xdr.TransactionEnvelope.Any
    )
    assert_type(xdr.UInt128Parts.from_xdr_bytes(data), xdr.UInt128Parts)
    assert_type(xdr.SCValType.from_xdr_bytes(data), xdr.SCValType)
    assert_type(
        typedefs.LedgerEntryChanges.from_xdr_bytes(data),
        tuple[xdr.LedgerEntryChange.Any, ...],
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
            assert_type(items, tuple[xdr.SCVal.Any, ...] | None)
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


def replacing(value: xdr.UInt128Parts) -> None:
    assert_type(xdr.replace(value, lo=1), xdr.UInt128Parts)
    if sys.version_info >= (3, 13):
        assert_type(copy.replace(value, lo=1), xdr.UInt128Parts)
