"""Every naming rule, in one place.

Names are part of the API and, once released, can only change with a protocol major,
so each rule is explicit and tested. The SEP-51 JSON names are computed here too, from
the XDR names alone, so that a Python override can never change a JSON name.
"""

import keyword
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from .model import Arm, Case, Enum, Model, Union

# --- Word splitting ------------------------------------------------------------------


def words(name: str) -> list[str]:
    """Split an identifier into words.

    Words are separated by anything that is not a letter or a digit, and inside a run of
    letters and digits at a lower-case-to-upper-case boundary (`quorumSet`) and before
    the last capital of a run of capitals followed by a lower-case letter (`SCPBallot`).
    Digits never start a word (`Ed25519`, `fee1KB`). This is the rule SEP-51 names are
    built with.
    """
    result: list[str] = []
    for chunk in re.split(r"[^A-Za-z0-9]+", name):
        if not chunk:
            continue
        current = ""
        for i, c in enumerate(chunk):
            if i > 0:
                previous = chunk[i - 1]
                following = chunk[i + 1] if i + 1 < len(chunk) else ""
                if (c.isupper() and (previous.islower() or previous.isdigit())) or (
                    c.isupper() and previous.isupper() and following.islower()
                ):
                    result.append(current)
                    current = ""
            current += c
        result.append(current)
    return result


def _capitalized(name: str) -> list[str]:
    return [w[:1].upper() + w[1:].lower() for w in words(name)]


def upper_camel(name: str) -> str:
    """`SCV_LEDGER_KEY_NONCE` -> `LedgerKeyNonce`-style capitalization of every word."""
    return "".join(_capitalized(name))


def snake(name: str) -> str:
    """`quorumSetHash` -> `quorum_set_hash`."""
    return "_".join(w.lower() for w in words(name))


def _serde_snake(name: str) -> str:
    # An underscore before every capital except the first, then lower case.
    return "".join(
        ("_" if c.isupper() and i > 0 else "") + c.lower() for i, c in enumerate(name)
    )


# --- Python names -------------------------------------------------------------------


def _escape(name: str) -> str:
    # PEP 8: a trailing underscore avoids a clash with a keyword. Soft keywords such as
    # `type` and `match` are valid names and stay as they are.
    return f"{name}_" if keyword.iskeyword(name) else name


# Words that the type names of the `.x` files spell with capitals of their own: five
# acronyms, and four words that they write as two (`AlphaNum4`, `SCPQuorumSet`,
# `TimePoint`, `TrustLineEntry`). A name made from an enum member or from a field
# doesn't say how its words are spelled, since the member is all capitals and the field
# starts in lower case. These words are spelled here, so that a class name has them as
# the type names do: the arm that holds a `TTLEntry` is `TTL`, not `Ttl`.
SPELLINGS: Final[dict[str, str]] = {
    "Id": "ID",
    "Ip": "IP",
    "Scp": "SCP",
    "Ttl": "TTL",
    "Udt": "UDT",
    "Alphanum4": "AlphaNum4",
    "Alphanum12": "AlphaNum12",
    "Quorumset": "QuorumSet",
    "Timepoint": "TimePoint",
    "Trustline": "TrustLine",
}


def _spell(capitalized: Iterable[str]) -> str:
    return "".join(SPELLINGS.get(w, w) for w in capitalized)


def type_name(xdr_name: str) -> str:
    """The Python name of a definition: as in the `.x` files, capitalized.

    Only the built-in typedefs (`uint32`, `int64`, `string32`, ...) start with a lower
    case letter; they become `Uint32`, `Int64` and `String32`.

    A struct or union declared inside another type has no name in the `.x` files.
    `xdr.json` names it after that type and the field, as in `LedgerKeyTtl` for the
    field `ttl`; its words are spelled as in `SPELLINGS`, which makes it `LedgerKeyTTL`.
    """
    return _spell(words(xdr_name[:1].upper() + xdr_name[1:]))


def field_name(xdr_name: str) -> str:
    """The Python name of a struct field or of the payload of a union arm."""
    return _escape(snake(xdr_name))


def discriminant_name(xdr_name: str) -> str:
    """The Python name of the class attribute that holds a union's discriminant."""
    return _escape(snake(xdr_name))


def module_name(xdr_file: str) -> str:
    """`xdr/Stellar-contract-config-setting.x` -> `_contract_config_setting`.

    The modules are private: upstream moves definitions between `.x` files without
    changing the protocol, so only `stellar_xdr` itself is a stable place to import a
    type from.
    """
    stem = xdr_file.rsplit("/", 1)[-1].removesuffix(".x").removeprefix("Stellar-")
    return f"_{snake(stem)}"


def _strip(member: str, enum: Enum) -> str:
    stripped = member.removeprefix(enum.member_prefix)
    # A name can't start with a digit: BINARY_FUSE_FILTER_8_BIT keeps the first
    # character of the prefix and becomes B8_BIT.
    if stripped[:1].isdigit():
        stripped = enum.member_prefix[:1] + stripped
    return stripped


# Arm names that the general rule gets wrong, mostly because the enum has a single
# member (so there is no common prefix to strip) or no common prefix. Keyed by
# (union, case). Only Python names change; JSON names always follow the rule.
ARM_OVERRIDES: Final[dict[tuple[str, str], str]] = {
    ("PublicKey", "PUBLIC_KEY_TYPE_ED25519"): "Ed25519",
    ("ClaimableBalanceID", "CLAIMABLE_BALANCE_ID_TYPE_V0"): "V0",
    ("Claimant", "CLAIMANT_TYPE_V0"): "V0",
    ("SCMetaEntry", "SC_META_V0"): "V0",
    ("SCEnvMetaEntry", "SC_ENV_META_KIND_INTERFACE_VERSION"): "InterfaceVersion",
    ("LiquidityPoolEntryBody", "LIQUIDITY_POOL_CONSTANT_PRODUCT"): "ConstantProduct",
    ("LiquidityPoolParameters", "LIQUIDITY_POOL_CONSTANT_PRODUCT"): "ConstantProduct",
    ("TxSetComponent", "TXSET_COMP_TXS_MAYBE_DISCOUNTED_FEE"): "TxsMaybeDiscountedFee",
    ("SurveyResponseBody", "SURVEY_TOPOLOGY_RESPONSE_V2"): "TopologyResponseV2",
    ("BucketEntry", "LIVEENTRY"): "LiveEntry",
    ("BucketEntry", "INITENTRY"): "InitEntry",
    ("BucketEntry", "DEADENTRY"): "DeadEntry",
    ("BucketEntry", "METAENTRY"): "MetaEntry",
    ("HotArchiveBucketEntry", "HOT_ARCHIVE_METAENTRY"): "MetaEntry",
}


def arm_class_name(model: Model, union: Union, case: Case) -> str:
    """The Python name of the class of one case of a union."""
    if case.name is None:
        # Integer switches: `case 0` -> V0. No negative value exists today.
        return f"V{case.value}" if case.value >= 0 else f"VMinus{-case.value}"
    override = ARM_OVERRIDES.get((union.name, case.name))
    if override is not None:
        return override
    enum = model.switch(union)
    assert isinstance(enum, Enum)  # noqa: S101 - checked by the loader
    # MEMO_NONE and PRECOND_NONE become None_.
    return _escape(_spell(_capitalized(_strip(case.name, enum))))


# --- JSON names (SEP-51) ------------------------------------------------------------


def json_member_name(member: str, enum: Enum) -> str:
    """The SEP-51 name of an enum member, which is also the key of a union arm."""
    return _serde_snake(upper_camel(_strip(member, enum)))


def json_case_name(model: Model, union: Union, case: Case) -> str:
    """The SEP-51 key of one case of a union."""
    if case.name is None:
        return f"v{case.value}" if case.value >= 0 else f"v_minus{-case.value}"
    enum = model.switch(union)
    assert isinstance(enum, Enum)  # noqa: S101 - checked by the loader
    return json_member_name(case.name, enum)


def json_field_name(xdr_name: str) -> str:
    """The SEP-51 key of a struct field."""
    return snake(xdr_name)


# --- The cases of a union ------------------------------------------------------------


@dataclass(frozen=True)
class UnionCase:
    """One case of a union: its arm, and every name the case has.

    `xdr_name` is the member of the enum the union switches on, or None when it
    switches on an integer.
    """

    arm: Arm
    value: int
    xdr_name: str | None
    class_name: str
    json_key: str


def union_cases(model: Model, union: Union) -> tuple[UnionCase, ...]:
    """The cases of a union, in the order of the `.x` file.

    Everything that needs a name of a case takes it from here: the class of the arm,
    the tables that find it, the tests' strategies and the list of arm names.
    """
    return tuple(
        UnionCase(
            arm,
            case.value,
            case.name,
            arm_class_name(model, union, case),
            json_case_name(model, union, case),
        )
        for arm in union.arms
        for case in arm.cases
    )
