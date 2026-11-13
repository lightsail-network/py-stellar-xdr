"""The types SEP-51 writes in a form of their own, rather than as structs and unions.

Addresses and keys become strkeys, 128 and 256-bit integers one integer string, and
asset codes a string. Each rule here names the runtime functions in `xdr_json` that
do the conversion; the generator emits the calls.

Every name in a rule is a name of the XDR definitions: a type, a field, or the case of
a union. No rule refers to a Python name, so renaming an arm class in `names.py` can't
change what a value looks like in JSON.

A rule also states the XDR type of every value it reads, since the runtime function
behind it returns values of that type and the generated code stores them without
checking them again. `check` compares each rule with the definitions, names and types,
and the generator fails when one doesn't match: an upstream change to a type can't
produce code that reads JSON into values of the wrong size or sign.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, TypeVar

from .model import (
    Definition,
    Enum,
    GenerationError,
    Model,
    OpaqueFixed,
    OpaqueVar,
    Primitive,
    Struct,
    Typedef,
    TypeRef,
    Union,
)


@dataclass(frozen=True)
class TypedefRule:
    """A typedef written as a string: the functions that write and read it.

    `type` is the XDR type the typedef has on the wire, which `read` returns.
    """

    write: str
    read: str
    type: TypeRef


@dataclass(frozen=True)
class StructRule:
    """A struct written as one string.

    `fields` names every field with its XDR type on the wire. `write` takes the fields
    in this order, and `read` returns them in this order.
    """

    write: str
    read: str
    fields: Mapping[str, TypeRef]


@dataclass(frozen=True)
class BuiltStruct:
    """A struct built from a strkey: what each of its fields holds."""

    struct: str
    fields: Mapping[str, "Payload"]


@dataclass(frozen=True)
class BuiltArm:
    """An arm of another union built from a strkey, and what the arm holds."""

    union: str
    case: str
    payload: "Payload"


# What an arm holds when it is read from a strkey: an attribute of the parsed strkey,
# such as `key` or `hash`, or a struct or an arm built from such attributes.
Payload = str | BuiltStruct | BuiltArm

_HYPER: Final[TypeRef] = Primitive("hyper")
_UNSIGNED_HYPER: Final[TypeRef] = Primitive("unsigned_hyper")
_KEY: Final[TypeRef] = OpaqueFixed(32)

# The attributes of the strkeys that `stellar_strkey` parses, and the XDR type that
# each one's value fits.
STRKEY_ATTRIBUTES: Final[Mapping[str, TypeRef]] = {
    "key": _KEY,
    "hash": _KEY,
    "id": _UNSIGNED_HYPER,
    "payload": OpaqueVar(64),
}


@dataclass(frozen=True)
class StrkeyArm:
    """One arm of a union that is written as a strkey.

    Reading: a strkey of the class `strkey` becomes the arm of `case`, holding
    `payload`. Writing: `write` takes the arm's value when that is plain bytes, which
    don't say which strkey they are; otherwise the value is written by its own rule.
    """

    strkey: str
    case: str
    payload: Payload
    write: str | None = None


@dataclass(frozen=True)
class Rules:
    """Every rule. The empty rules write each type as the struct or union it is."""

    typedefs: Mapping[str, TypedefRule] = field(default_factory=dict[str, TypedefRule])
    structs: Mapping[str, StructRule] = field(default_factory=dict[str, StructRule])
    # Unions written as the bare value of their arm, a string, instead of an object
    # keyed by the arm. The arms of one are told apart by the kind of strkey, and
    # those of the other by the length of the string: (case, length in bytes), from
    # the shortest up.
    strkey_unions: Mapping[str, tuple[StrkeyArm, ...]] = field(
        default_factory=dict[str, tuple[StrkeyArm, ...]]
    )
    length_unions: Mapping[str, tuple[tuple[str, int], ...]] = field(
        default_factory=dict[str, tuple[tuple[str, int], ...]]
    )

    def is_bare(self, union: str) -> bool:
        """Whether a union is written as the bare value of its arm."""
        return union in self.strkey_unions or union in self.length_unions

    def strkey_arm(self, union: str, case: str | None) -> StrkeyArm | None:
        """The rule of one arm of a union written as a strkey, if it has one."""
        for arm in self.strkey_unions.get(union, ()):
            if arm.case == case:
                return arm
        return None


# The parts of the 128 and 256-bit integers: the highest one carries the sign of a
# signed integer.
_INT128: Final = {"hi": _HYPER, "lo": _UNSIGNED_HYPER}
_UINT128: Final = {"hi": _UNSIGNED_HYPER, "lo": _UNSIGNED_HYPER}
_INT256: Final = {
    "hi_hi": _HYPER,
    "hi_lo": _UNSIGNED_HYPER,
    "lo_hi": _UNSIGNED_HYPER,
    "lo_lo": _UNSIGNED_HYPER,
}
_UINT256: Final = dict.fromkeys(_INT256, _UNSIGNED_HYPER)
_MUXED: Final = {"ed25519": _KEY, "id": _UNSIGNED_HYPER}

RULES: Final = Rules(
    typedefs={
        "ContractID": TypedefRule("write_contract", "read_contract", _KEY),
        "PoolID": TypedefRule("write_liquidity_pool", "read_liquidity_pool", _KEY),
        "AssetCode4": TypedefRule(
            "write_asset_code4", "read_asset_code4", OpaqueFixed(4)
        ),
        "AssetCode12": TypedefRule(
            "write_asset_code12", "read_asset_code12", OpaqueFixed(12)
        ),
    },
    structs={
        "Int128Parts": StructRule("write_int128", "read_int128", _INT128),
        "UInt128Parts": StructRule("write_int128", "read_uint128", _UINT128),
        "Int256Parts": StructRule("write_int256", "read_int256", _INT256),
        "UInt256Parts": StructRule("write_int256", "read_uint256", _UINT256),
        "MuxedAccountMed25519": StructRule(
            "write_muxed_account", "read_muxed_account", _MUXED
        ),
        "MuxedEd25519Account": StructRule(
            "write_muxed_account", "read_muxed_account", _MUXED
        ),
        "MuxedContract": StructRule(
            "write_muxed_contract",
            "read_muxed_contract",
            {"contractId": _KEY, "id": _UNSIGNED_HYPER},
        ),
        "SignerKeyEd25519SignedPayload": StructRule(
            "write_signed_payload",
            "read_signed_payload",
            {"ed25519": _KEY, "payload": OpaqueVar(64)},
        ),
    },
    strkey_unions={
        "PublicKey": (
            StrkeyArm(
                "Ed25519PublicKey", "PUBLIC_KEY_TYPE_ED25519", "key", "write_account"
            ),
        ),
        "ClaimableBalanceID": (
            StrkeyArm(
                "ClaimableBalance",
                "CLAIMABLE_BALANCE_ID_TYPE_V0",
                "hash",
                "write_claimable_balance",
            ),
        ),
        "MuxedAccount": (
            StrkeyArm("Ed25519PublicKey", "KEY_TYPE_ED25519", "key", "write_account"),
            StrkeyArm(
                "MuxedEd25519Account",
                "KEY_TYPE_MUXED_ED25519",
                BuiltStruct("MuxedAccountMed25519", {"id": "id", "ed25519": "key"}),
            ),
        ),
        "SignerKey": (
            StrkeyArm(
                "Ed25519PublicKey", "SIGNER_KEY_TYPE_ED25519", "key", "write_account"
            ),
            StrkeyArm(
                "PreAuthTx", "SIGNER_KEY_TYPE_PRE_AUTH_TX", "hash", "write_pre_auth_tx"
            ),
            StrkeyArm("HashX", "SIGNER_KEY_TYPE_HASH_X", "hash", "write_hash_x"),
            StrkeyArm(
                "Ed25519SignedPayload",
                "SIGNER_KEY_TYPE_ED25519_SIGNED_PAYLOAD",
                BuiltStruct(
                    "SignerKeyEd25519SignedPayload",
                    {"ed25519": "key", "payload": "payload"},
                ),
            ),
        ),
        "SCAddress": (
            StrkeyArm(
                "Ed25519PublicKey",
                "SC_ADDRESS_TYPE_ACCOUNT",
                BuiltArm("PublicKey", "PUBLIC_KEY_TYPE_ED25519", "key"),
            ),
            StrkeyArm("Contract", "SC_ADDRESS_TYPE_CONTRACT", "hash"),
            StrkeyArm(
                "MuxedEd25519Account",
                "SC_ADDRESS_TYPE_MUXED_ACCOUNT",
                BuiltStruct("MuxedEd25519Account", {"id": "id", "ed25519": "key"}),
            ),
            StrkeyArm(
                "ClaimableBalance",
                "SC_ADDRESS_TYPE_CLAIMABLE_BALANCE",
                BuiltArm("ClaimableBalanceID", "CLAIMABLE_BALANCE_ID_TYPE_V0", "hash"),
            ),
            StrkeyArm("LiquidityPool", "SC_ADDRESS_TYPE_LIQUIDITY_POOL", "hash"),
            StrkeyArm(
                "MuxedContract",
                "SC_ADDRESS_TYPE_MUXED_CONTRACT",
                BuiltStruct("MuxedContract", {"id": "id", "contractId": "hash"}),
            ),
        ),
    },
    # An AssetCode12 always keeps 5 bytes, so the length tells the two apart.
    length_unions={
        "AssetCode": (
            ("ASSET_TYPE_CREDIT_ALPHANUM4", 4),
            ("ASSET_TYPE_CREDIT_ALPHANUM12", 12),
        ),
    },
)


# --- Checking the rules against the definitions --------------------------------------


_D = TypeVar("_D", Struct, Union, Typedef)


def defined(model: Model, name: str, kind: type[_D]) -> _D:
    """The definition a SEP-51 rule names, which has to be of the kind it is for."""
    d = model.by_name.get(name)
    if not isinstance(d, kind):
        msg = f"SEP-51 rule for {name}: the definitions have no such {kind.__name__}"
        raise GenerationError(msg)
    return d


def check(model: Model, rules: Rules) -> None:
    """Fail on a rule that doesn't match the definitions, by name or by type.

    A rule names definitions by their XDR names. When a definition is renamed or
    removed upstream, its rule would otherwise stop applying without a word, and
    the type would be written as a plain struct or union. When a definition keeps its
    name but changes its type, the rule's runtime functions would read values of the
    old type into it.
    """
    for name, typedef_rule in rules.typedefs.items():
        d = defined(model, name, Typedef)
        _check_type(model, name, d.type, typedef_rule.type)
    for name, struct_rule in rules.structs.items():
        struct = defined(model, name, Struct)
        _check_struct_fields(struct, set(struct_rule.fields))
        for f in struct.fields:
            _check_type(model, f"{name}.{f.name}", f.type, struct_rule.fields[f.name])
    for name, strkey_arms in rules.strkey_unions.items():
        union = defined(model, name, Union)
        _check_cases(union, [arm.case for arm in strkey_arms])
        for arm in strkey_arms:
            where = f"{name}.{arm.case}"
            _check_payload(model, where, _held(union, arm.case), arm.payload)
    for name, lengths in rules.length_unions.items():
        union = defined(model, name, Union)
        _check_cases(union, [case for case, _ in lengths])
        for case, length in lengths:
            where = f"{name}.{case}"
            _check_type(model, where, _held(union, case), OpaqueFixed(length))
    both = rules.strkey_unions.keys() & rules.length_unions.keys()
    if both:
        msg = f"SEP-51 rules for {sorted(both)}: a strkey and a length rule each"
        raise GenerationError(msg)


def _describe(t: TypeRef | Definition) -> str:
    return t.name if isinstance(t, Struct | Union | Enum) else str(t)


def _check_type(model: Model, where: str, t: TypeRef, expected: TypeRef) -> None:
    actual = model.resolve(t)
    if actual != expected:
        msg = (
            f"SEP-51 rule for {where}: the definitions have {_describe(actual)}, "
            f"where the rule reads {_describe(expected)}"
        )
        raise GenerationError(msg)


def _held(union: Union, case: str) -> TypeRef:
    """What the arm of a case holds; `_check_cases` found that every arm holds one."""
    arm = next(a for a in union.arms for c in a.cases if c.name == case)
    assert arm.type is not None  # noqa: S101
    return arm.type


def _check_struct_fields(d: Struct, fields: set[str]) -> None:
    if fields != {f.name for f in d.fields}:
        msg = f"SEP-51 rule for {d.name}: it doesn't name exactly its fields"
        raise GenerationError(msg)


def _check_cases(union: Union, cases: list[str]) -> None:
    # A union written as a bare string has no key to say which arm it is, so
    # every arm needs a rule, and a value to write.
    expected = [c.name for arm in union.arms for c in arm.cases]
    if sorted(cases) != sorted(str(c) for c in expected):
        msg = f"SEP-51 rule for {union.name}: it doesn't name exactly its cases"
        raise GenerationError(msg)
    if any(arm.type is None for arm in union.arms):
        msg = f"SEP-51 rule for {union.name}: an arm without a value has no string"
        raise GenerationError(msg)


def _check_payload(model: Model, where: str, held: TypeRef, payload: Payload) -> None:
    """Check what a rule builds from a strkey against `held`, the type it goes into."""
    if isinstance(payload, str):
        expected = STRKEY_ATTRIBUTES.get(payload)
        if expected is None:
            msg = f"SEP-51 rule for {where}: a strkey has no attribute {payload!r}"
            raise GenerationError(msg)
        _check_type(model, where, held, expected)
    elif isinstance(payload, BuiltStruct):
        struct = defined(model, payload.struct, Struct)
        _check_built(model, where, held, struct)
        _check_struct_fields(struct, set(payload.fields))
        types = {f.name: f.type for f in struct.fields}
        for name, inner in payload.fields.items():
            _check_payload(model, f"{struct.name}.{name}", types[name], inner)
    else:
        union = defined(model, payload.union, Union)
        cases = [c.name for arm in union.arms for c in arm.cases]
        if payload.case not in cases:
            msg = f"SEP-51 rule for {union.name}: it has no case {payload.case}"
            raise GenerationError(msg)
        _check_built(model, where, held, union)
        arm = next(a for a in union.arms for c in a.cases if c.name == payload.case)
        if arm.type is None:
            msg = f"SEP-51 rule for {union.name}.{payload.case}: the arm holds nothing"
            raise GenerationError(msg)
        inner_where = f"{union.name}.{payload.case}"
        _check_payload(model, inner_where, arm.type, payload.payload)


def _check_built(
    model: Model, where: str, held: TypeRef, built: Struct | Union
) -> None:
    actual = model.resolve(held)
    if actual is not built:
        msg = (
            f"SEP-51 rule for {where}: the definitions have {_describe(actual)}, "
            f"where the rule builds {built.name}"
        )
        raise GenerationError(msg)
