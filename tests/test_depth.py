"""The default depth accepts what the network admits, in every direction.

Since protocol 28, stellar-core admits a transaction only if rs-stellar-xdr reads it
within a depth of 1000. That depth counts every type rs-stellar-xdr reads, so each
shape of nesting costs a number of them for each level, and no admitted transaction
nests that shape more deeply than 1000 divided by that number. The tests nest each
shape that deep inside a transaction, whose envelope costs more: deeper than anything
the network admits, so that whatever passes them, an admitted transaction passes too.

Claim predicates nest as well, but stellar-core rejects one nested more than four
levels deep, so they are not among the shapes.
"""

import functools
import inspect
import re
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

import stellar_xdr as xdr

# The stack frames that the code calling the library may have in use, as the guide
# says: the deepest admitted values leave this many of Python's 1000.
CALLER_FRAMES = 300

_T = TypeVar("_T")

VOID = xdr.SCVal.Void()
ADDRESS = xdr.SCAddress.Contract(bytes(32))
FUNCTION = xdr.SorobanAuthorizedFunction.ContractFn(
    xdr.InvokeContractArgs(ADDRESS, "f", [])
)
INVOCATION = xdr.SorobanAuthorizedInvocation(FUNCTION, [])
DELEGATE = xdr.SorobanDelegateSignature(ADDRESS, VOID, [])


def transaction(
    auth: list[xdr.SorobanAuthorizationEntry], args: list[xdr.SCVal.Any]
) -> xdr.TransactionEnvelope.Any:
    """A transaction that calls a contract with these arguments and authorizations."""
    call = xdr.HostFunction.InvokeContract(xdr.InvokeContractArgs(ADDRESS, "f", args))
    body = xdr.OperationBody.InvokeHostFunction(xdr.InvokeHostFunctionOp(call, auth))
    tx = xdr.Transaction(
        xdr.MuxedAccount.Ed25519(bytes(32)),
        100,
        1,
        xdr.Preconditions.None_(),
        xdr.Memo.None_(),
        [xdr.Operation(None, body)],
        xdr.TransactionExt.V0(),
    )
    return xdr.TransactionEnvelope.Tx(xdr.TransactionV1Envelope(tx, []))


def auth_tree(levels: int) -> xdr.TransactionEnvelope.Any:
    invocation = INVOCATION
    for _ in range(levels - 1):
        invocation = xdr.SorobanAuthorizedInvocation(FUNCTION, [invocation])
    source = xdr.SorobanCredentials.SourceAccount()
    return transaction([xdr.SorobanAuthorizationEntry(source, invocation)], [])


def delegates(levels: int) -> xdr.TransactionEnvelope.Any:
    delegate = DELEGATE
    for _ in range(levels - 1):
        delegate = xdr.SorobanDelegateSignature(ADDRESS, VOID, [delegate])
    credentials = xdr.SorobanCredentials.AddressWithDelegates(
        xdr.SorobanAddressCredentialsWithDelegates(
            xdr.SorobanAddressCredentials(ADDRESS, 0, 0, VOID), [delegate]
        )
    )
    return transaction([xdr.SorobanAuthorizationEntry(credentials, INVOCATION)], [])


def argument(
    wrap: Callable[[xdr.SCVal.Any], xdr.SCVal.Any],
) -> Callable[[int], xdr.TransactionEnvelope.Any]:
    """A transaction whose argument wraps a value in a value at each level."""

    def build(levels: int) -> xdr.TransactionEnvelope.Any:
        value: xdr.SCVal.Any = VOID
        for _ in range(levels - 1):
            value = wrap(value)
        return transaction([], [value])

    return build


def vec(value: xdr.SCVal.Any) -> xdr.SCVal.Any:
    return xdr.SCVal.Vec([value])


def map_(value: xdr.SCVal.Any) -> xdr.SCVal.Any:
    return xdr.SCVal.Map([xdr.SCMapEntry(VOID, value)])


def contract_instance(value: xdr.SCVal.Any) -> xdr.SCVal.Any:
    executable = xdr.ContractExecutable.StellarAsset()
    storage = [xdr.SCMapEntry(VOID, value)]
    return xdr.SCVal.ContractInstance(xdr.SCContractInstance(executable, storage))


# Each shape, nested 1000 levels divided by the types rs-stellar-xdr reads for each of
# them. The signature in each delegate is an SCVal, one level more: 499 delegates are
# 500 levels deep.
SHAPES = {
    # SorobanAuthorizedInvocation, VecM
    "auth tree": (auth_tree, 1000 // 2),
    # SorobanDelegateSignature, VecM
    "delegates": (delegates, 1000 // 2 - 1),
    # ScVal, Option, ScVec, VecM
    "SCVal.Vec": (argument(vec), 1000 // 4),
    # ScVal, Option, ScMap, VecM, ScMapEntry
    "SCVal.Map": (argument(map_), 1000 // 5),
    # ScVal, ScContractInstance, Option, ScMap, VecM, ScMapEntry
    "SCVal.ContractInstance": (argument(contract_instance), 1000 // 6),
}


def frames_in_use() -> int:
    """The stack frames below this function's own, which the recursion limit counts."""
    frame = inspect.currentframe()
    count = 0
    while frame is not None:
        count += 1
        frame = frame.f_back
    return count - 1


def in_caller(call: Callable[[], _T], frames: int = CALLER_FRAMES) -> _T:
    """Make the call from this many stack frames deep, as a program deep in its work.

    The call is a bound method or a functools.partial, which adds no frame of its own.
    """
    if frames_in_use() >= frames:
        return call()
    return in_caller(call, frames)


@pytest.mark.parametrize("shape", SHAPES)
def test_what_the_network_admits_works_by_default(shape: str) -> None:
    build, levels = SHAPES[shape]
    value = build(levels)
    data = in_caller(value.to_xdr_bytes)
    written = in_caller(value.to_json_value)
    # Compared by their encoding: equality and the lists and objects of JSON recurse
    # without a depth limit, taking more frames for each level before CPython 3.12.
    decode = functools.partial(xdr.TransactionEnvelope.from_xdr_bytes, data)
    assert in_caller(decode).to_xdr_bytes() == data
    read = functools.partial(xdr.TransactionEnvelope.from_json_value, written)
    assert in_caller(read).to_xdr_bytes() == data


def test_the_default_depth_is_500_levels() -> None:
    value = auth_tree(501)
    data = value.to_xdr_bytes(max_depth=501)
    written = value.to_json_value(max_depth=501)
    with pytest.raises(xdr.XdrDepthError, match="max_depth=500"):
        value.to_xdr_bytes()
    with pytest.raises(xdr.XdrDepthError, match="max_depth=500"):
        xdr.TransactionEnvelope.from_xdr_bytes(data)
    with pytest.raises(xdr.XdrDepthError, match="max_depth=500"):
        value.to_json_value()
    with pytest.raises(xdr.XdrDepthError, match="max_depth=500"):
        xdr.TransactionEnvelope.from_json_value(written)


ENTRY = xdr.SCMapEntry(VOID, VOID)
UNCONDITIONAL = xdr.ClaimPredicate.Unconditional()
QUORUM_SET = xdr.SCPQuorumSet(1, [], [])
BOOL = xdr.SCSpecTypeDef.Bool()


# Each array on a cycle, which the generated code reads in a loop of its own: the
# function that reads the value, the value with two items, the path to them in its
# JSON, and where an error in one is reported.
ArrayCase = tuple[Callable[[object], object], xdr.XdrValue, list[str], str]
ARRAYS_ON_A_CYCLE: list[ArrayCase] = [
    (xdr.SCVal.from_json_value, xdr.SCVal.Vec([VOID, VOID]), ["vec"], "SCVal.Vec.vec"),
    (
        xdr.SCVal.from_json_value,
        xdr.SCVal.Map([ENTRY, ENTRY]),
        ["map"],
        "SCVal.Map.map",
    ),
    (
        xdr.SCVal.from_json_value,
        xdr.SCVal.ContractInstance(
            xdr.SCContractInstance(
                xdr.ContractExecutable.StellarAsset(), [ENTRY, ENTRY]
            )
        ),
        ["contract_instance", "storage"],
        "SCContractInstance.storage",
    ),
    (
        xdr.SorobanAuthorizedInvocation.from_json_value,
        xdr.SorobanAuthorizedInvocation(FUNCTION, [INVOCATION, INVOCATION]),
        ["sub_invocations"],
        "SorobanAuthorizedInvocation.sub_invocations",
    ),
    (
        xdr.SorobanDelegateSignature.from_json_value,
        xdr.SorobanDelegateSignature(ADDRESS, VOID, [DELEGATE, DELEGATE]),
        ["nested_delegates"],
        "SorobanDelegateSignature.nested_delegates",
    ),
    (
        xdr.ClaimPredicate.from_json_value,
        xdr.ClaimPredicate.And([UNCONDITIONAL, UNCONDITIONAL]),
        ["and"],
        "ClaimPredicate.And.and_predicates",
    ),
    (
        xdr.ClaimPredicate.from_json_value,
        xdr.ClaimPredicate.Or([UNCONDITIONAL, UNCONDITIONAL]),
        ["or"],
        "ClaimPredicate.Or.or_predicates",
    ),
    (
        xdr.SCPQuorumSet.from_json_value,
        xdr.SCPQuorumSet(1, [], [QUORUM_SET, QUORUM_SET]),
        ["inner_sets"],
        "SCPQuorumSet.inner_sets",
    ),
    (
        xdr.SCSpecTypeDef.from_json_value,
        xdr.SCSpecTypeDef.Tuple(xdr.SCSpecTypeTuple([BOOL, BOOL])),
        ["tuple", "value_types"],
        "SCSpecTypeTuple.value_types",
    ),
]


@pytest.mark.parametrize(
    ("read_json", "value", "path", "where"),
    ARRAYS_ON_A_CYCLE,
    ids=[where for *_, where in ARRAYS_ON_A_CYCLE],
)
def test_an_error_in_an_item_says_which_item_it_is(
    read_json: Callable[[object], object],
    value: xdr.XdrValue,
    path: list[str],
    where: str,
) -> None:
    written = value.to_json_value()
    items: Any = written
    for key in path:
        items = items[key]
    items[1] = 7
    with pytest.raises(xdr.XdrJsonError, match=f"^{re.escape(where)}\\[1\\]: "):
        read_json(written)
