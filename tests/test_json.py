"""SEP-51 XDR-JSON: the representation of each kind of value, and strict reading."""

import json
import sys
from typing import Any

import pytest
import stellar_strkey as strkey

import stellar_xdr as xdr

KEY = bytes(range(32))
HASH = bytes(32)
G = str(strkey.Ed25519PublicKey(KEY))
C = str(strkey.Contract(KEY))
T = str(strkey.PreAuthTx(KEY))


def test_numbers() -> None:
    assert xdr.SCVal.U32(5).to_json_value() == {"u32": 5}
    assert xdr.SCVal.I64(-5).to_json_value() == {"i64": "-5"}
    assert xdr.SCVal.U64(2**64 - 1).to_json_value() == {"u64": "18446744073709551615"}
    # 64-bit integers are read from strings and from numbers.
    assert xdr.SCVal.from_json_value({"i64": "-5"}) == xdr.SCVal.I64(-5)
    assert xdr.SCVal.from_json_value({"i64": -5}) == xdr.SCVal.I64(-5)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"u32": "5"}, r"SCVal\.U32\.u32: expected an integer, got a string"),
        ({"u32": 5.0}, "expected an integer, got a number"),
        ({"u32": True}, "expected an integer, got a boolean"),
        ({"u32": -1}, "-1 is out of range for uint32"),
        ({"i32": 2**31}, "out of range for int32"),
        ({"u64": "05"}, "'05' is not a 64-bit base 10 integer"),
        ({"i64": "+5"}, "not a 64-bit base 10 integer"),
        ({"i64": "-0"}, "not a 64-bit base 10 integer"),
        ({"i64": " 5"}, "not a 64-bit base 10 integer"),
        ({"i64": "1_000"}, "not a 64-bit base 10 integer"),
        ({"i64": None}, "expected an integer string, got null"),
        ({"u64": "-1"}, "out of range for uint64"),
        ({"bool": 1}, "expected a boolean, got a number"),
    ],
)
def test_invalid_numbers(value: object, message: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match=message):
        xdr.SCVal.from_json_value(value)


def test_big_integers_are_one_string() -> None:
    assert xdr.SCVal.I128(xdr.Int128Parts(-1, 2**64 - 1)).to_json_value() == {
        "i128": "-1"
    }
    big = xdr.SCVal.U256(xdr.UInt256Parts(1, 2, 3, 4))
    text = str((1 << 192) | (2 << 128) | (3 << 64) | 4)
    assert big.to_json_value() == {"u256": text}
    assert xdr.SCVal.from_json_value({"u256": text}) == big
    negative = xdr.SCVal.from_json_value({"i256": str(-(2**255))})
    assert negative == xdr.SCVal.I256(xdr.Int256Parts(-(2**63), 0, 0, 0))
    assert xdr.SCVal.from_json_value({"u128": str(2**128 - 1)}) == xdr.SCVal.U128(
        xdr.UInt128Parts(2**64 - 1, 2**64 - 1)
    )
    with pytest.raises(xdr.XdrJsonError, match="out of range for int128"):
        xdr.SCVal.from_json_value({"i128": str(2**127)})
    with pytest.raises(xdr.XdrJsonError, match="expected an integer string"):
        xdr.SCVal.from_json_value({"i128": 5})
    with pytest.raises(xdr.XdrJsonError, match="not a base 10 integer"):
        xdr.SCVal.from_json_value({"u256": "9" * 100})


def test_opaque_is_hex() -> None:
    assert xdr.SCVal.Bytes(b"\xab\xcd").to_json_value() == {"bytes": "abcd"}
    assert xdr.SCVal.from_json_value({"bytes": "ABCD"}) == xdr.SCVal.Bytes(b"\xab\xcd")
    with pytest.raises(xdr.XdrJsonError, match="expected 32 bytes, got 1"):
        xdr.TTLEntry.from_json_value({"key_hash": "00", "live_until_ledger_seq": 1})


@pytest.mark.parametrize("text", ["abc", "ab cd", "zz", "0x"])
def test_invalid_hex(text: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match="not hex"):
        xdr.SCVal.from_json_value({"bytes": text})


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="PyPy has no tracemalloc"
)
@pytest.mark.parametrize(
    ("decoder", "message"),
    [
        (xdr.Hash, "expected 32 bytes, got 1000000"),
        (xdr.DataValue, "expected at most 64 bytes, got 1000000"),
    ],
    ids=["fixed", "variable"],
)
def test_overlong_hex_is_rejected_before_it_is_read(
    decoder: type[xdr.XdrBytes], message: str
) -> None:
    # Imported here: on PyPy, importing the module fails.
    import tracemalloc  # noqa: PLC0415

    # Hex for a million bytes, where at most 64 fit: rejected by its length alone,
    # without matching or decoding 2 MB of text.
    text = "00" * 1_000_000
    tracemalloc.start()
    try:
        with pytest.raises(xdr.XdrJsonError, match=message):
            decoder.from_json_value(text)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < len(text) // 4


def test_inline_fixed_opaque_is_hex() -> None:
    # SEP-51 writes all opaque data as hex, including inline fixed-length fields.
    assert xdr.Curve25519Public(KEY).to_json_value() == {"key": KEY.hex()}
    assert xdr.PeerAddressIP.IPv4(b"\1\2\3\4").to_json_value() == {"i_pv4": "01020304"}


def test_strings_are_escaped_ascii() -> None:
    value = xdr.SCVal.String(b"h\xc3\xa9 \\ \0\t\n\r\x7f")
    expected = "h\\xc3\\xa9 \\\\ \\0\\t\\n\\r\\x7f"
    assert value.to_json_value() == {"string": expected}
    assert xdr.SCVal.from_json_value({"string": expected}) == value
    # Text outside ASCII is also accepted as it is.
    assert xdr.SCVal.from_json_value({"string": "hé"}) == xdr.SCVal.String("hé")
    assert xdr.SCVal.Symbol("abc").to_json_value() == {"symbol": "abc"}


@pytest.mark.parametrize("text", ["\\q", "\\x4", "\\xzz", "\\"])
def test_invalid_escapes(text: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match="invalid escape"):
        xdr.SCVal.from_json_value({"string": text})


def test_string_length_is_checked_in_bytes() -> None:
    with pytest.raises(xdr.XdrJsonError, match="at most 32 bytes"):
        xdr.SCVal.from_json_value({"symbol": "é" * 17})


def test_asset_codes() -> None:
    issuer = xdr.PublicKey.Ed25519(xdr.Uint256(KEY))
    four = xdr.Asset.CreditAlphaNum4(xdr.AlphaNum4(xdr.AssetCode4(b"AB\0\0"), issuer))
    assert four.to_json_value() == {
        "credit_alphanum4": {"asset_code": "AB", "issuer": G}
    }
    twelve = xdr.AlphaNum12(xdr.AssetCode12(b"ABC" + bytes(9)), issuer)
    assert twelve.to_json_value()["asset_code"] == "ABC\\0\\0"
    assert xdr.AlphaNum12.from_json_value(twelve.to_json_value()) == twelve
    with pytest.raises(xdr.XdrJsonError, match="at most 4 bytes"):
        xdr.AlphaNum4.from_json_value({"asset_code": "ABCDE", "issuer": G})
    with pytest.raises(xdr.XdrJsonError, match="5 to 12 bytes"):
        xdr.AlphaNum12.from_json_value({"asset_code": "ABC", "issuer": G})


def test_asset_code_union_is_told_apart_by_length() -> None:
    four = xdr.AssetCode.CreditAlphaNum4(xdr.AssetCode4(b"AB\0\0"))
    twelve = xdr.AssetCode.CreditAlphaNum12(xdr.AssetCode12(b"ABCDE" + bytes(7)))
    empty = xdr.AssetCode.CreditAlphaNum4(xdr.AssetCode4(bytes(4)))
    for value, text in [(four, "AB"), (twelve, "ABCDE"), (empty, "")]:
        assert value.to_json_value() == text
        assert xdr.AssetCode.from_json_value(text) == value
    with pytest.raises(xdr.XdrJsonError, match="at most 12 bytes"):
        xdr.AssetCode.from_json_value("ABCDEFGHIJKLM")


def test_addresses_are_strkeys() -> None:
    account = xdr.SCAddress.Account(xdr.PublicKey.Ed25519(xdr.Uint256(KEY)))
    assert account.to_json_value() == G
    values: list[tuple[xdr.SCAddress.Any, str]] = [
        (account, "G"),
        (xdr.SCAddress.Contract(xdr.ContractID(KEY)), "C"),
        (xdr.SCAddress.MuxedAccount(xdr.MuxedEd25519Account(1, xdr.Uint256(KEY))), "M"),
        (xdr.SCAddress.ClaimableBalance(xdr.ClaimableBalanceID.V0(xdr.Hash(KEY))), "B"),
        (xdr.SCAddress.LiquidityPool(xdr.PoolID(KEY)), "L"),
        (xdr.SCAddress.MuxedContract(xdr.MuxedContract(1, xdr.ContractID(KEY))), "W"),
    ]
    for value, prefix in values:
        text = value.to_json_value()
        assert text.startswith(prefix)
        assert xdr.SCAddress.from_json_value(text) == value


def test_muxed_accounts_and_signers_are_strkeys() -> None:
    plain = xdr.MuxedAccount.Ed25519(xdr.Uint256(KEY))
    muxed = xdr.MuxedAccount.MuxedEd25519(xdr.MuxedAccountMed25519(7, xdr.Uint256(KEY)))
    for value in [plain, muxed]:
        assert xdr.MuxedAccount.from_json_value(value.to_json_value()) == value
    signers: list[tuple[xdr.SignerKey.Any, str]] = [
        (xdr.SignerKey.Ed25519(xdr.Uint256(KEY)), "G"),
        (xdr.SignerKey.PreAuthTx(xdr.Uint256(KEY)), "T"),
        (xdr.SignerKey.HashX(xdr.Uint256(KEY)), "X"),
        (
            xdr.SignerKey.Ed25519SignedPayload(
                xdr.SignerKeyEd25519SignedPayload(xdr.Uint256(KEY), b"\1")
            ),
            "P",
        ),
    ]
    for value, prefix in signers:
        text = value.to_json_value()
        assert text.startswith(prefix)
        assert xdr.SignerKey.from_json_value(text) == value


def test_an_empty_signed_payload_has_no_json() -> None:
    value = xdr.SignerKeyEd25519SignedPayload(xdr.Uint256(KEY), b"")
    with pytest.raises(xdr.XdrJsonError, match="no SEP-51 representation"):
        value.to_json_value()


def test_ids_are_strkeys() -> None:
    assert xdr.ContractID(HASH).to_json_value().startswith("C")
    assert xdr.PoolID(HASH).to_json_value().startswith("L")
    claimable = xdr.ClaimableBalanceID.V0(xdr.Hash(HASH))
    assert (
        xdr.ClaimableBalanceID.from_json_value(claimable.to_json_value()) == claimable
    )
    assert xdr.NodeID.from_json_value(G) == xdr.PublicKey.Ed25519(KEY)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (G.lower(), "Strkey|strkey|base32|character"),
        (G[:-1] + "A", "checksum|Checksum"),
        (C, "Contract strkey"),
        (5, "expected a strkey string, got a number"),
    ],
)
def test_invalid_strkeys(value: object, message: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match=message):
        xdr.MuxedAccount.from_json_value(value)


# A contract strkey fits none of these; G... fits SignerKey and SCAddress, so those
# get a T... strkey, which fits neither.
@pytest.mark.parametrize(
    ("reader", "value"),
    [
        (xdr.PublicKey, C),
        (xdr.ClaimableBalanceID, C),
        (xdr.PoolID, C),
        (xdr.ContractID, G),
        (xdr.MuxedEd25519Account, C),
        (xdr.MuxedContract, C),
        (xdr.SignerKeyEd25519SignedPayload, C),
        (xdr.SignerKey, C),
        (xdr.SCAddress, T),
    ],
    ids=lambda value: getattr(value, "__name__", getattr(value, "name", None)),
)
def test_wrong_strkey_types_for_every_kind_of_field(reader: Any, value: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match="strkey is not allowed here"):
        reader.from_json_value(value)


def test_unions() -> None:
    assert xdr.SCVal.from_json_value("void") == xdr.SCVal.Void()
    assert xdr.SCVal.from_json_value({"void": None}) == xdr.SCVal.Void()
    assert xdr.TransactionExt.V0().to_json_value() == "v0"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("u32", "'u32' needs a value"),
        ("nope", "unknown arm 'nope'"),
        ({"nope": 1}, "unknown arm 'nope'"),
        ({"void": 1}, "'void' holds no value"),
        ({"u32": 1, "i32": 1}, "expected one key, got 2"),
        ({}, "expected one key, got 0"),
        (5, "expected a string or an object, got a number"),
    ],
)
def test_invalid_unions(value: object, message: str) -> None:
    with pytest.raises(xdr.XdrJsonError, match=message):
        xdr.SCVal.from_json_value(value)


def test_structs_need_exactly_their_fields() -> None:
    assert xdr.UInt128Parts(1, 2).to_json_value() == str((1 << 64) | 2)
    entry = {"key_hash": HASH.hex(), "live_until_ledger_seq": 1}
    assert xdr.TTLEntry.from_json_value(entry) == xdr.TTLEntry(xdr.Hash(HASH), 1)
    with pytest.raises(
        xdr.XdrJsonError, match="TTLEntry: missing live_until_ledger_seq"
    ):
        xdr.TTLEntry.from_json_value({"key_hash": HASH.hex()})
    with pytest.raises(xdr.XdrJsonError, match="TTLEntry: unknown 'extra'"):
        xdr.TTLEntry.from_json_value({**entry, "extra": 1})
    with pytest.raises(xdr.XdrJsonError, match="expected an object, got an array"):
        xdr.TTLEntry.from_json_value([])


def test_schema_is_allowed_and_ignored() -> None:
    schema = "https://stellar.org/schema/xdr-json/main/TTLEntry.json"
    entry = {"key_hash": HASH.hex(), "live_until_ledger_seq": 1}
    assert xdr.TTLEntry.from_json_value({"$schema": schema, **entry}) == xdr.TTLEntry(
        xdr.Hash(HASH), 1
    )
    assert xdr.SCVal.from_json_value({"$schema": "x", "u32": 1}) == xdr.SCVal.U32(1)
    with pytest.raises(xdr.XdrJsonError, match="missing"):
        xdr.TTLEntry.from_json_value({"$schema": schema, "key_hash": HASH.hex()})


def test_arrays_and_optional_values() -> None:
    value = xdr.SCVal.Vec([xdr.SCVal.U32(1)])
    assert value.to_json_value() == {"vec": [{"u32": 1}]}
    assert xdr.SCVal.Vec(None).to_json_value() == {"vec": None}
    assert xdr.SCVal.from_json_value({"vec": None}) == xdr.SCVal.Vec(None)
    with pytest.raises(xdr.XdrJsonError, match="expected an array, got an object"):
        xdr.SCVal.from_json_value({"vec": {}})
    predicate = "unconditional"
    with pytest.raises(xdr.XdrJsonError, match="at most 2 items, got 3"):
        xdr.ClaimPredicate.from_json_value({"and": [predicate] * 3})


def test_fixed_arrays() -> None:
    hashes = [HASH.hex()] * 4
    header = xdr.LedgerHeader.from_xdr_bytes(_HEADER)
    data = header.to_json_value()
    assert data["skip_list"] == hashes
    assert xdr.LedgerHeader.from_json_value(data) == header
    with pytest.raises(xdr.XdrJsonError, match="expected 4 items, got 3"):
        xdr.LedgerHeader.from_json_value({**data, "skip_list": hashes[:3]})


_HEADER = xdr.LedgerHeader(
    ledger_version=1,
    previous_ledger_hash=xdr.Hash(HASH),
    scp_value=xdr.StellarValue(xdr.Hash(HASH), 0, [], xdr.StellarValueExt.Basic()),
    tx_set_result_hash=xdr.Hash(HASH),
    bucket_list_hash=xdr.Hash(HASH),
    ledger_seq=1,
    total_coins=0,
    fee_pool=0,
    inflation_seq=0,
    id_pool=0,
    base_fee=100,
    base_reserve=1,
    max_tx_set_size=1,
    skip_list=[xdr.Hash(HASH)] * 4,
    ext=xdr.LedgerHeaderExt.V0(),
).to_xdr_bytes()


def test_enums_are_names() -> None:
    assert xdr.SCValType.SCV_U32.to_json_value() == "u32"
    assert xdr.SCValType.from_json_value("u32") is xdr.SCValType.SCV_U32
    with pytest.raises(xdr.XdrJsonError, match="unknown member 'U32'"):
        xdr.SCValType.from_json_value("U32")
    with pytest.raises(xdr.XdrJsonError, match="expected a string, got a number"):
        xdr.SCValType.from_json_value(3)


def nested(depth: int) -> Any:
    value: Any = "void"
    for _ in range(depth):
        value = {"vec": [value]}
    return value


def test_depth_is_limited() -> None:
    assert xdr.SCVal.from_json_value(nested(5), max_depth=6).to_json_value(
        max_depth=6
    ) == nested(5)
    with pytest.raises(xdr.XdrDepthError, match="JSON nested deeper than max_depth=5"):
        xdr.SCVal.from_json_value(nested(5), max_depth=5)
    value = xdr.SCVal.from_json_value(nested(5))
    with pytest.raises(xdr.XdrDepthError, match="max_depth=5"):
        value.to_json_value(max_depth=5)


def test_recursion_beyond_python_limits_is_an_error() -> None:
    with pytest.raises(xdr.XdrDepthError, match="recursion limit"):
        xdr.SCVal.from_json_value(nested(3000), max_depth=10_000)
    deep: xdr.SCVal.Any = xdr.SCVal.Void()
    for _ in range(3000):
        deep = xdr.SCVal.Vec([deep])
    with pytest.raises(xdr.XdrDepthError, match="recursion limit"):
        deep.to_json_value(max_depth=10_000)


def test_typedef_json() -> None:
    assert xdr.SequenceNumber(5).to_json_value() == "5"
    assert xdr.SCVec([xdr.SCVal.U32(1)]).to_json_value() == [{"u32": 1}]
    assert xdr.SCSymbol("a b").to_json_value() == "a b"
    decoded = xdr.Hash.from_json_value(HASH.hex())
    assert decoded == HASH
    assert type(decoded) is xdr.Hash
    with pytest.raises(xdr.XdrJsonError, match=r"^SCVec: expected an array, got null$"):
        xdr.SCVec.from_json_value(None)


def test_json_text_round_trip() -> None:
    value = xdr.SCVal.Map(
        [xdr.SCMapEntry(xdr.SCVal.Symbol("a"), xdr.SCVal.I128(xdr.Int128Parts(0, 1)))]
    )
    text = json.dumps(value.to_json_value())
    assert text == '{"map": [{"key": {"symbol": "a"}, "val": {"i128": "1"}}]}'
    assert xdr.SCVal.from_json_value(json.loads(text)) == value


def test_values_that_json_cannot_hold() -> None:
    with pytest.raises(
        xdr.XdrJsonError, match="expected a string or an object, got bytes"
    ):
        xdr.SCVal.from_json_value(b"u32")
    with pytest.raises(xdr.XdrJsonError, match="expected a hex string, got a number"):
        xdr.SCVal.from_json_value({"bytes": 1})
    with pytest.raises(xdr.XdrJsonError, match="expected a string, got a number"):
        xdr.SCVal.from_json_value({"string": 1})
    with pytest.raises(xdr.XdrJsonError, match="expected at most 28 bytes, got 29"):
        xdr.Memo.from_json_value({"text": "x" * 29})
    with pytest.raises(xdr.XdrJsonError, match="at most 64 bytes, got 65"):
        xdr.DataEntry.from_json_value(
            {"account_id": G, "data_name": "a", "data_value": "00" * 65, "ext": "v0"}
        )


def test_hostile_input_raises_the_documented_error() -> None:
    # json.loads accepts a lone surrogate, which has no UTF-8 encoding.
    surrogate = json.loads('"\\ud800"')
    with pytest.raises(xdr.XdrJsonError, match="lone surrogate"):
        xdr.SCVal.from_json_value({"string": surrogate})
    with pytest.raises(xdr.XdrJsonError, match="lone surrogate"):
        xdr.SCVal.from_json_value({"string": "\\x41" + surrogate})
    # int() refuses strings of more than 4,300 digits, and str() such integers.
    with pytest.raises(xdr.XdrJsonError, match="not a 64-bit base 10 integer"):
        xdr.SCVal.from_json_value({"i64": "9" * 5000})
    with pytest.raises(xdr.XdrJsonError, match="a huge number is out of range"):
        xdr.SCVal.from_json_value({"u32": 10**5000})
    with pytest.raises(xdr.XdrJsonError, match="a huge number is out of range"):
        xdr.SCVal.from_json_value({"i64": 10**5000})
    with pytest.raises(xdr.XdrJsonError, match="not a base 10 integer"):
        xdr.SCVal.from_json_value({"i128": "9" * 5000})


def test_messages_quote_little_of_the_input() -> None:
    with pytest.raises(xdr.XdrJsonError) as excinfo:
        xdr.SCVal.from_json_value("x" * 1_000_000)
    assert len(str(excinfo.value)) < 100
    entry: dict[object, object] = {"key_hash": HASH.hex(), "live_until_ledger_seq": 1}
    with pytest.raises(xdr.XdrJsonError, match="unknown 1"):
        xdr.TTLEntry.from_json_value({1: 1, **entry})


def test_an_optional_field_may_be_left_out() -> None:
    operation = xdr.Operation.from_json_value({"body": "inflation"})
    assert operation == xdr.Operation(None, xdr.OperationBody.Inflation())
    assert operation.to_xdr_base64() == "AAAAAAAAAAk="
    # It is written as null.
    assert operation.to_json_value() == {"source_account": None, "body": "inflation"}
    with pytest.raises(xdr.XdrJsonError, match="missing body"):
        xdr.Operation.from_json_value({"source_account": None})


def test_integer_subclasses_are_stored_as_plain_ints() -> None:
    class Unhashable(int):
        __hash__ = None  # type: ignore[assignment]

    small = xdr.SCVal.from_json_value({"u32": Unhashable(5)})
    large = xdr.SCVal.from_json_value({"i64": Unhashable(5)})
    assert isinstance(small, xdr.SCVal.U32)
    assert isinstance(large, xdr.SCVal.I64)
    assert small.u32.__class__ is int
    assert large.i64.__class__ is int
    assert hash(small) == hash(xdr.SCVal.U32(5))


def test_errors_say_which_item_is_wrong() -> None:
    with pytest.raises(
        xdr.XdrJsonError, match=r"^SCVal\.Vec\.vec\[1\]: SCVal: unknown arm 'x'$"
    ):
        xdr.SCVal.from_json_value({"vec": ["void", "x"]})
