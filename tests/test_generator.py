"""The generator: naming rules, the loader's checks, and what it counts as recursive.

Names are part of the API, and changing one breaks the code that uses it, so the rules
are tested here, and the JSON names against the reference's schemas (see
`tests/vectors/README.md`).
"""

import dataclasses
import json
import pkgutil
from pathlib import Path
from typing import Any

import pytest

import stellar_xdr
from generator import names, sep51
from generator.analysis import counted_types
from generator.model import (
    Case,
    Enum,
    GenerationError,
    InputError,
    Model,
    Struct,
    Typedef,
    Union,
    load,
)
from generator.package import Generator

ROOT = Path(__file__).parent.parent
MODEL = load(ROOT / "xdr" / "xdr.json")
PROTOCOL = 30
REFERENCE: dict[str, list[str]] = json.loads(
    (ROOT / "tests" / "vectors" / "xdr_json_names.json").read_text()
)


def reference_names(definition: Enum | Struct | Union) -> list[str] | None:
    # The reference names types in UpperCamel case: SCVal is ScVal.
    return REFERENCE.get(names.upper_camel(definition.name))


def our_names(definition: Enum | Struct | Union) -> list[str]:
    if isinstance(definition, Enum):
        return sorted(
            names.json_member_name(m.name, definition) for m in definition.members
        )
    if isinstance(definition, Struct):
        return sorted(names.json_field_name(f.name) for f in definition.fields)
    return sorted(c.json_key for c in names.union_cases(MODEL, definition))


@pytest.mark.parametrize(
    "definition",
    [d for d in MODEL.definitions if isinstance(d, Enum | Struct | Union)],
    ids=lambda d: d.name,
)
def test_json_names_match_the_reference(definition: Enum | Struct | Union) -> None:
    expected = reference_names(definition)
    if expected is None:
        # Written as a string by SEP-51, such as a strkey or a big integer.
        return
    assert our_names(definition) == expected


def test_the_reference_names_cover_most_types() -> None:
    covered = [
        d
        for d in MODEL.definitions
        if isinstance(d, Enum | Struct | Union) and reference_names(d) is not None
    ]
    assert len(covered) > 400


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("quorumSetHash", ["quorum", "Set", "Hash"]),
        ("SCPBallot", ["SCP", "Ballot"]),
        ("txFEE_BUMP_INNER_SUCCESS", ["tx", "FEE", "BUMP", "INNER", "SUCCESS"]),
        ("Ed25519", ["Ed25519"]),
        ("fee1KB", ["fee1", "KB"]),
        ("IPv4", ["I", "Pv4"]),
    ],
)
def test_words(name: str, expected: list[str]) -> None:
    assert names.words(name) == expected


def test_field_and_type_names() -> None:
    assert names.field_name("quorumSetHash") == "quorum_set_hash"
    assert names.field_name("from") == "from_"
    assert names.field_name("type") == "type"  # a soft keyword stays
    assert names.type_name("uint32") == "Uint32"
    assert names.type_name("SCVal") == "SCVal"
    assert names.module_name("xdr/Stellar-contract-config-setting.x") == (
        "_contract_config_setting"
    )


def test_the_modules_of_the_x_files_are_private() -> None:
    # A definition can move to another `.x` file, so its module is not part of the
    # API: every type is imported from the package itself.
    public = {
        module.name
        for module in pkgutil.iter_modules(stellar_xdr.__path__)
        if not module.name.startswith("_")
    }
    assert public == set()
    assert stellar_xdr.SCVal.__module__ == "stellar_xdr._contract"


def arm(union: str, case: str) -> str:
    definition = MODEL.get(union)
    assert isinstance(definition, Union)
    return next(
        c.class_name for c in names.union_cases(MODEL, definition) if c.xdr_name == case
    )


def test_arm_names() -> None:
    assert arm("SCVal", "SCV_U32") == "U32"
    assert (
        arm("SCVal", "SCV_LEDGER_KEY_CONTRACT_INSTANCE") == "LedgerKeyContractInstance"
    )
    assert arm("TransactionResultResult", "txFEE_BUMP_INNER_SUCCESS") == (
        "TxFeeBumpInnerSuccess"
    )
    assert arm("Memo", "MEMO_NONE") == "None_"
    union = MODEL.get("TransactionExt")
    assert isinstance(union, Union)
    assert names.arm_class_name(MODEL, union, Case(0, None)) == "V0"
    assert names.arm_class_name(MODEL, union, Case(-1, None)) == "VMinus1"


def test_arm_names_spell_acronyms_as_type_names_do() -> None:
    # The arm that holds a TTLEntry, an SCPEnvelope or an SCSpecUDTStructV0.
    assert arm("LedgerEntryData", "TTL") == "TTL"
    assert arm("OperationBody", "EXTEND_FOOTPRINT_TTL") == "ExtendFootprintTTL"
    assert arm("StellarMessage", "SCP_MESSAGE") == "SCPMessage"
    assert arm("StellarMessage", "GET_SCP_STATE") == "GetSCPState"
    assert arm("SCSpecEntry", "SC_SPEC_ENTRY_UDT_STRUCT_V0") == "UDTStructV0"
    assert arm("HashIDPreimage", "ENVELOPE_TYPE_OP_ID") == "OpID"
    assert arm("Memo", "MEMO_ID") == "ID"


def test_arm_names_spell_compound_words_as_type_names_do() -> None:
    # The arm that holds an AlphaNum4, a TimePoint, an SCPQuorumSet or a TrustLineEntry.
    assert arm("Asset", "ASSET_TYPE_CREDIT_ALPHANUM4") == "CreditAlphaNum4"
    assert arm("AssetCode", "ASSET_TYPE_CREDIT_ALPHANUM12") == "CreditAlphaNum12"
    assert arm("SCVal", "SCV_TIMEPOINT") == "TimePoint"
    assert arm("SCSpecTypeDef", "SC_SPEC_TYPE_TIMEPOINT") == "TimePoint"
    assert arm("StellarMessage", "SCP_QUORUMSET") == "SCPQuorumSet"
    assert arm("StellarMessage", "GET_SCP_QUORUMSET") == "GetSCPQuorumSet"
    assert arm("LedgerEntryData", "TRUSTLINE") == "TrustLine"
    assert arm("LedgerKey", "TRUSTLINE") == "TrustLine"
    # CHANGE_TRUST_TRUST_LINE_MISSING is TrustLineMissing by the plain rule.
    assert arm(
        "ClaimClaimableBalanceResult", "CLAIM_CLAIMABLE_BALANCE_TRUSTLINE_FROZEN"
    ) == ("TrustLineFrozen")
    assert arm("ChangeTrustResult", "CHANGE_TRUST_TRUST_LINE_MISSING") == (
        "TrustLineMissing"
    )


def test_json_names_keep_the_plain_rule() -> None:
    # SEP-51 names are not Python names: no spelling of ours reaches them.
    enum = MODEL.get("LedgerEntryType")
    assert isinstance(enum, Enum)
    assert names.json_member_name("TTL", enum) == "ttl"
    enum = MODEL.get("MessageType")
    assert isinstance(enum, Enum)
    assert names.json_member_name("GET_SCP_STATE", enum) == "get_scp_state"


def test_every_class_name_spells_the_words_one_way() -> None:
    class_names = [
        names.type_name(d.name)
        for d in MODEL.definitions
        if isinstance(d, Enum | Struct | Union | Typedef)
    ]
    for d in MODEL.definitions:
        if isinstance(d, Union):
            class_names += [
                arm(d.name, c.name) for a in d.arms for c in a.cases if c.name
            ]
    assert not [
        name
        for name in class_names
        if any(word in names.SPELLINGS for word in names.words(name))
    ]


def test_only_types_the_x_files_dont_name_are_renamed() -> None:
    renamed = {
        d.name: names.type_name(d.name)
        for d in MODEL.definitions
        if isinstance(d, Enum | Struct | Union | Typedef)
        and names.type_name(d.name) != d.name[:1].upper() + d.name[1:]
    }
    assert renamed == {
        "LedgerKeyTtl": "LedgerKeyTTL",
        "PeerAddressIp": "PeerAddressIP",
        "HashIDPreimageOperationId": "HashIDPreimageOperationID",
        "HashIDPreimageRevokeId": "HashIDPreimageRevokeID",
        "HashIDPreimageContractId": "HashIDPreimageContractID",
    }
    # Each is declared inside another type, and named by `xdr.json`: a name written in
    # the `.x` files is never changed.
    for name in renamed:
        definition = MODEL.get(name)
        assert isinstance(definition, Struct | Union)
        assert name not in definition.source


def test_a_leading_digit_keeps_the_prefix_initial() -> None:
    enum = MODEL.get("BinaryFuseFilterType")
    assert isinstance(enum, Enum)
    assert names.json_member_name("BINARY_FUSE_FILTER_8_BIT", enum) == "b8_bit"


@pytest.mark.parametrize(("key", "expected"), sorted(names.ARM_OVERRIDES.items()))
def test_every_override_applies_to_an_existing_arm(
    key: tuple[str, str], expected: str
) -> None:
    assert arm(*key) == expected


def test_recursive_types_count_their_unions() -> None:
    counted = counted_types(MODEL)
    assert {"SCVal", "SCSpecTypeDef", "ClaimPredicate"} <= counted
    # SCMapEntry is on the cycle of SCVal, but only the union counts.
    assert "SCMapEntry" not in counted
    assert "TransactionEnvelope" not in counted


def document(*definitions: dict[str, Any], **top: Any) -> dict[str, Any]:
    return {
        "version": 1,
        "files": [{"name": "xdr/Stellar-test.x", "sha256": ""}],
        "resolved_features": [],
        "definitions": list(definitions),
        **top,
    }


def typedef(name: str, type_: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "typedef",
        "name": name,
        "source": "",
        "file_index": 0,
        "type": type_,
    }


def load_document(tmp_path: Path, data: dict[str, Any]) -> Model:
    path = tmp_path / "xdr.json"
    path.write_text(json.dumps(data))
    return load(path)


def test_a_minimal_document_loads(tmp_path: Path) -> None:
    model = load_document(tmp_path, document(typedef("A", {"kind": "int"})))
    assert [d.name for d in model.definitions] == ["A"]


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (document(version=2), "unsupported xdr.json version"),
        (document(resolved_features=["next"]), "unexpected resolved_features"),
        (document(typedef("A", {"kind": "float"})), "unsupported type kind"),
        (document(typedef("A", {"kind": "int", "extra": 1})), "unexpected keys"),
        (document(typedef("A", {"kind": "ref", "name": "B"})), "unresolved reference"),
        (
            document(typedef("A", {"kind": "int"}), typedef("A", {"kind": "int"})),
            "duplicate definition",
        ),
        (
            document(
                {
                    "kind": "union",
                    "name": "U",
                    "fixed_size": None,
                    "source": "",
                    "file_index": 0,
                    "discriminant": {"name": "v", "type": {"kind": "int"}},
                    "arms": [{"cases": [], "name": None, "default": True}],
                }
            ),
            "unexpected keys",
        ),
        (
            document(
                {
                    "kind": "enum",
                    "name": "E",
                    "source": "",
                    "file_index": 0,
                    "member_prefix": "X_",
                    "members": [{"name": "Y_A", "value": 0}],
                }
            ),
            "does not prefix every member",
        ),
    ],
)
def test_unknown_shapes_are_rejected(
    tmp_path: Path, data: dict[str, Any], message: str
) -> None:
    with pytest.raises(InputError, match=message):
        load_document(tmp_path, data)


def enum(name: str, prefix: str, *members: tuple[str, int]) -> dict[str, Any]:
    return {
        "kind": "enum",
        "name": name,
        "source": "",
        "file_index": 0,
        "member_prefix": prefix,
        "members": [{"name": n, "value": v} for n, v in members],
    }


def const(name: str, value: object) -> dict[str, Any]:
    return {
        "kind": "const",
        "name": name,
        "value": value,
        "source": "",
        "file_index": 0,
    }


def struct(name: str, *fields: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "struct",
        "name": name,
        "fixed_size": None,
        "source": "",
        "file_index": 0,
        "fields": [{"name": n, "type": t} for n, t in fields],
    }


def union_on(enum_name: str, *cases: tuple[str, int]) -> dict[str, Any]:
    return {
        "kind": "union",
        "name": "U",
        "fixed_size": None,
        "source": "",
        "file_index": 0,
        "discriminant": {"name": "type", "type": {"kind": "ref", "name": enum_name}},
        "arms": [{"cases": [{"value": v, "name": n}], "name": None} for n, v in cases],
    }


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (
            document(typedef("A", {"kind": "opaque_fixed", "size": -1})),
            "invalid opaque size",
        ),
        (
            document(typedef("A", {"kind": "opaque_var", "max_size": 1.5})),
            "invalid opaque",
        ),
        (
            document(
                typedef("A", {"kind": "array", "element": {"kind": "int"}, "count": -2})
            ),
            "invalid array count",
        ),
        (document(enum("E", "", ("A", 2**31))), "out of range"),
        (document(enum("E", "", ("A", True))), "invalid enum value"),
        (document(const("A", "1")), "invalid const value"),
        (document({**const("A", 1), "file_index": 1}), "is not one of the 1 files"),
        (document({"kind": "const", "value": 1}), "without a name"),
    ],
)
def test_invalid_numbers_are_rejected(
    tmp_path: Path, data: dict[str, Any], message: str
) -> None:
    with pytest.raises(InputError, match=message):
        load_document(tmp_path, data)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        # Two members whose names normalize to the same name, and so do their arms.
        (
            document(
                enum("E", "", ("FOO_BAR", 0), ("fooBAR", 1)),
                union_on("E", ("FOO_BAR", 0), ("fooBAR", 1)),
            ),
            "duplicate JSON names",
        ),
        # Two fields whose names normalize to the same Python name.
        (
            document(
                struct("S", ("fooBar", {"kind": "int"}), ("foo_bar", {"kind": "int"}))
            ),
            "duplicate",
        ),
        # A field that would hide a method.
        (
            document(struct("S", ("toXdrBytes", {"kind": "int"}))),
            "can't be a field name",
        ),
        # Elements that encode to nothing can't bound an array's length.
        (
            document(
                struct("Empty"),
                typedef(
                    "A",
                    {"kind": "var_array", "element": {"kind": "ref", "name": "Empty"}},
                ),
            ),
            "encode to no bytes",
        ),
        # Definitions named like something else the package exports.
        (document(const("PROTOCOL_VERSION", 31)), "PROTOCOL_VERSION is reserved"),
        (document(const("replace", 1)), "replace is reserved"),
        (document(typedef("xdrError", {"kind": "int"})), "XdrError is reserved"),
        # A `.x` file whose module would take the place of the runtime.
        (
            document(
                typedef("A", {"kind": "int"}),
                files=[{"name": "xdr/Stellar-runtime.x", "sha256": ""}],
            ),
            "would replace stellar_xdr._runtime",
        ),
    ],
)
def test_ambiguous_definitions_fail_generation(
    tmp_path: Path, data: dict[str, Any], message: str
) -> None:
    model = load_document(tmp_path, data)
    with pytest.raises(GenerationError, match=message):
        Generator(model, PROTOCOL, sep51.Rules()).sources()


def test_a_typedef_is_a_class_unless_its_values_cant_be_instances(
    tmp_path: Path,
) -> None:
    data = document(
        typedef("uint32", {"kind": "unsigned_int"}),
        typedef("Flag", {"kind": "bool"}),
        typedef("Count", {"kind": "ref", "name": "uint32"}),
        typedef(
            "Counts", {"kind": "var_array", "element": {"kind": "ref", "name": "Count"}}
        ),
        typedef(
            "Maybe", {"kind": "optional", "element": {"kind": "ref", "name": "Count"}}
        ),
        struct("S", ("count", {"kind": "ref", "name": "Count"})),
        typedef("T", {"kind": "ref", "name": "S"}),
    )
    source = Generator(
        load_document(tmp_path, data), PROTOCOL, sep51.Rules()
    ).sources()["_test.py"]
    # A typedef of a primitive, of a bool, of an optional value and of a struct are
    # other names; the rest are classes that extend the type of their values.
    assert "Uint32: TypeAlias = int" in source
    assert "Flag: TypeAlias = bool" in source
    assert "Maybe: TypeAlias = Count | None" in source
    assert "\nT = S  # " in source
    assert "class Count(XdrInt):" in source
    assert "class Counts(XdrArray[Count]):" in source
    count = source.split("class Count(XdrInt):")[1].split("@final")[0]
    assert "return new_int(cls, check.uint32(value, where))" in count
    assert "return new_int(cls, reader.uint32())" in count
    # A 32-bit integer is written to JSON as it is: as a plain int.
    assert "return int(self)" in count
    counts = source.split("class Counts(XdrArray[Count]):")[1]
    assert "check.array(value, where, None, Count._checked)" in counts
    assert (
        "[new_int(Count, reader.uint32()) for _ in range(reader.count(None, 4))]"
        in (counts)
    )
    assert "[int(item0) for item0 in self]" in counts
    struct_code = source.split("class S(XdrStruct):")[1].split("@final")[0]
    assert "def __init__(self, count: Uint32) -> None:" in struct_code
    assert "count: Count\n" in struct_code
    assert "Count._checked(count, 'S.count')" in struct_code
    assert "new_int(Count, xdr_json.read_uint32(fields['count'], 'S.count'))" in (
        struct_code
    )


def test_a_word_in_the_xdr_source_is_not_a_use_of_a_name(tmp_path: Path) -> None:
    # The docstrings quote the XDR source, comments included.
    definition = struct("S", ("a", {"kind": "int"}))
    definition["source"] = (
        "struct S {\n    int a; // Sequence of Literal, see NewType\n};"
    )
    model = load_document(tmp_path, document(definition))
    source = Generator(model, PROTOCOL, sep51.Rules()).sources()["_test.py"]
    assert "Sequence of Literal, see NewType" in source
    imports = [line for line in source.splitlines() if "import" in line]
    runtime = "JsonReader, JsonWriter, Reader, Writer, XdrStruct, check, new, set_field"
    assert imports == [
        "from __future__ import annotations",
        "from typing import Any, Self, final",
        f"from ._runtime import {runtime}, xdr_json",
    ]


def strkey_arms_without(union: str, case: str) -> dict[str, Any]:
    arms = dict(sep51.RULES.strkey_unions)
    arms[union] = tuple(arm for arm in arms[union] if arm.case != case)
    return {"strkey_unions": arms}


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        # A rule for a definition that was renamed or removed upstream.
        (
            {
                "typedefs": {
                    "Gone": sep51.TypedefRule("write_contract", "read_contract")
                }
            },
            "SEP-51 rule for Gone: the definitions have no such Typedef",
        ),
        (
            {
                "structs": {
                    "SCVal": sep51.StructRule(
                        "write_int128", "read_int128", ("hi", "lo")
                    )
                }
            },
            "SEP-51 rule for SCVal: the definitions have no such Struct",
        ),
        # A struct that gained a field its rule doesn't know.
        (
            {
                "structs": {
                    "Int128Parts": sep51.StructRule(
                        "write_int128", "read_int128", ("hi",)
                    )
                }
            },
            "SEP-51 rule for Int128Parts: it doesn't name exactly its fields",
        ),
        # A union that gained an arm no strkey is read as.
        (
            strkey_arms_without("SCAddress", "SC_ADDRESS_TYPE_MUXED_CONTRACT"),
            "SEP-51 rule for SCAddress: it doesn't name exactly its cases",
        ),
        (
            {"length_unions": {"AssetCode": (("ASSET_TYPE_CREDIT_ALPHANUM4", 4),)}},
            "SEP-51 rule for AssetCode: it doesn't name exactly its cases",
        ),
        # A payload built for a case that the other union doesn't have.
        (
            {
                "strkey_unions": {
                    "PublicKey": (
                        sep51.StrkeyArm(
                            "Ed25519PublicKey",
                            "PUBLIC_KEY_TYPE_ED25519",
                            sep51.BuiltArm("SignerKey", "SIGNER_KEY_TYPE_GONE", "key"),
                        ),
                    )
                }
            },
            "SEP-51 rule for SignerKey: it has no case SIGNER_KEY_TYPE_GONE",
        ),
        # A bare string can't say which arm it is when an arm holds nothing.
        (
            {
                "length_unions": {
                    "Preconditions": (
                        ("PRECOND_NONE", 0),
                        ("PRECOND_TIME", 1),
                        ("PRECOND_V2", 2),
                    )
                }
            },
            "SEP-51 rule for Preconditions: an arm without a value has no string",
        ),
        (
            {"length_unions": {"PublicKey": (("PUBLIC_KEY_TYPE_ED25519", 32),)}},
            "a strkey and a length rule each",
        ),
    ],
)
def test_a_rule_that_does_not_apply_fails_generation(
    changes: dict[str, Any], message: str
) -> None:
    rules = dataclasses.replace(sep51.RULES, **changes)
    with pytest.raises(GenerationError, match=message):
        Generator(MODEL, PROTOCOL, rules)


def test_the_rules_apply_to_the_vendored_definitions() -> None:
    Generator(MODEL, PROTOCOL)


def test_a_python_name_does_not_change_the_json_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without its override the arm of PublicKey gets another class name. The rule
    # names the XDR case, so the arm is still written and read as a strkey.
    monkeypatch.delitem(names.ARM_OVERRIDES, ("PublicKey", "PUBLIC_KEY_TYPE_ED25519"))
    source = Generator(MODEL, PROTOCOL).sources()["_types.py"]
    assert "class PublicKeyTypeEd25519(XdrArm):" in source
    assert "new(PublicKey.PublicKeyTypeEd25519)" in source
    assert "new(PublicKey.Ed25519)" not in source
    arm = source.split("class PublicKeyTypeEd25519(XdrArm):")[1].split(
        "Any: TypeAlias"
    )[0]
    assert "return xdr_json.write_account(self.ed25519)" in arm
