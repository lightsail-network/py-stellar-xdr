"""The generator: naming rules, the loader's checks, and what it counts as recursive.

Names are part of the API, and changing one breaks the code that uses it, so the rules
are tested here, and the JSON names against the reference's schemas (see
`tests/vectors/README.md`).
"""

import json
import pkgutil
from pathlib import Path
from typing import Any

import pytest

import stellar_xdr
from generator import names
from generator.emit import GenerationError, Generator, counted_types
from generator.model import Enum, InputError, Model, Struct, Union, load

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
    return sorted(
        names.json_case_name(MODEL, definition, c.value, c.name)
        for a in definition.arms
        for c in a.cases
    )


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
    assert public == {"typedefs"}
    assert stellar_xdr.SCVal.__module__ == "stellar_xdr._contract"


def arm(union: str, case: str) -> str:
    definition = MODEL.get(union)
    assert isinstance(definition, Union)
    value = next(c.value for a in definition.arms for c in a.cases if c.name == case)
    return names.arm_class_name(MODEL, definition, value, case)


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
    assert names.arm_class_name(MODEL, union, 0, None) == "V0"
    assert names.arm_class_name(MODEL, union, -1, None) == "VMinus1"


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
        Generator(model, PROTOCOL).sources()
