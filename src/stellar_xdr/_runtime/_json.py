"""SEP-51 XDR-JSON: the conversions the generated `_to_json` and `_from_json` use.

Values go to and come from "JSON values": what `json.loads` returns and `json.dumps`
accepts. Reading is as strict as binary decoding: anything that is not a valid
SEP-51 representation raises `XdrJsonError`, which names the type and field.

Every reading function takes the JSON value and a description of where it goes, such
as `"Transaction.fee"`, followed by its own arguments.
"""

import re
from collections.abc import Callable, Mapping
from typing import Final, NoReturn, TypeVar

import stellar_strkey as strkey

from ._codec import check_max_depth
from ._errors import XdrDepthError, XdrJsonError

_INT32: Final = (-(2**31), 2**31 - 1)
_UINT32: Final = (0, 2**32 - 1)
_INT64: Final = (-(2**63), 2**63 - 1)
_UINT64: Final = (0, 2**64 - 1)
_UINT64_MASK: Final = 2**64 - 1

# Canonical base 10: no sign but a minus, no leading zeros, no "-0".
_DECIMAL: Final = re.compile(r"-?[1-9][0-9]*|0")
_HEX: Final = re.compile(r"(?:[0-9a-fA-F]{2})*")
_SCHEMA: Final = "$schema"

_K = TypeVar("_K")
_T = TypeVar("_T")
_V = TypeVar("_V")


class JsonWriter:
    """Tracks the depth while converting a value to JSON."""

    __slots__ = ("depth", "max_depth")

    def __init__(self, max_depth: int) -> None:
        self.depth = 0
        self.max_depth = check_max_depth(max_depth)

    def enter(self) -> None:
        """Count one more level of nesting of a recursive type."""
        self.depth += 1
        if self.depth > self.max_depth:
            msg = f"value nested deeper than max_depth={self.max_depth}"
            raise XdrDepthError(msg)


class JsonReader:
    """Tracks the depth while converting JSON to a value."""

    __slots__ = ("depth", "max_depth")

    def __init__(self, max_depth: int) -> None:
        self.depth = 0
        self.max_depth = check_max_depth(max_depth)

    def enter(self) -> None:
        """Count one more level of nesting of a recursive type."""
        self.depth += 1
        if self.depth > self.max_depth:
            msg = f"JSON nested deeper than max_depth={self.max_depth}"
            raise XdrDepthError(msg)


def encode_json(convert: Callable[[JsonWriter], _T], max_depth: int) -> _T:
    """Convert to JSON, turning a too deep recursion into `XdrDepthError`."""
    try:
        return convert(JsonWriter(max_depth))
    except RecursionError:
        msg = "value nested deeper than Python's recursion limit"
        raise XdrDepthError(msg) from None


def decode_json(
    convert: Callable[[object, JsonReader], _T], value: object, max_depth: int
) -> _T:
    """Convert from JSON, turning a too deep recursion into `XdrDepthError`."""
    try:
        return convert(value, JsonReader(max_depth))
    except RecursionError:
        msg = "JSON nested deeper than Python's recursion limit"
        raise XdrDepthError(msg) from None


def _fail(where: str, message: str) -> NoReturn:
    msg = f"{where}: {message}"
    raise XdrJsonError(msg)


def _kind(value: object) -> str:  # noqa: PLR0911 - one return per kind of JSON
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, int | float):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "an object"
    return type(value).__name__


def _expected(where: str, expected: str, value: object) -> NoReturn:
    _fail(where, f"expected {expected}, got {_kind(value)}")


def show(value: object) -> str:
    """Quote part of the input in a message, which stays short whatever the input."""
    if isinstance(value, int) and not isinstance(value, bool):
        # str() of an int with more than 4,300 digits raises ValueError.
        return str(value) if value.bit_length() <= 256 else "a huge number"  # noqa: PLR2004
    text = repr(value)
    return text if len(text) <= 40 else f"{text[:37]}..."  # noqa: PLR2004


# --- Numbers and booleans -------------------------------------------------------


def _number(value: object, where: str, bounds: tuple[int, int], name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        _expected(where, "an integer", value)
    if not bounds[0] <= value <= bounds[1]:
        _fail(where, f"{show(value)} is out of range for {name}")
    # A subclass, such as an IntEnum member, is stored as a plain int, like constructors
    # store it.
    return value if value.__class__ is int else int(value)


def int32(value: object, where: str) -> int:
    """Read a signed 32-bit integer, which SEP-51 writes as a JSON number."""
    return _number(value, where, _INT32, "int32")


def uint32(value: object, where: str) -> int:
    """Read an unsigned 32-bit integer, which SEP-51 writes as a JSON number."""
    return _number(value, where, _UINT32, "uint32")


def _decimal(value: object, where: str, bounds: tuple[int, int], name: str) -> int:
    # SEP-51 writes 64-bit integers as strings, since JSON numbers can't hold them
    # exactly in many languages. Numbers are accepted too, as earlier versions of
    # SEP-51 wrote them.
    if isinstance(value, str):
        # The longest 64-bit integer has 20 characters; the length check also keeps
        # int() away from strings over its limit of 4,300 digits.
        if len(value) > 20 or _DECIMAL.fullmatch(value) is None:  # noqa: PLR2004
            _fail(where, f"{show(value)} is not a 64-bit base 10 integer")
        number = int(value)
    elif isinstance(value, int) and not isinstance(value, bool):
        number = value if value.__class__ is int else int(value)
    else:
        _expected(where, "an integer string", value)
    if not bounds[0] <= number <= bounds[1]:
        _fail(where, f"{show(number)} is out of range for {name}")
    return number


def int64(value: object, where: str) -> int:
    """Read a signed 64-bit integer from a string or a number."""
    return _decimal(value, where, _INT64, "int64")


def uint64(value: object, where: str) -> int:
    """Read an unsigned 64-bit integer from a string or a number."""
    return _decimal(value, where, _UINT64, "uint64")


def boolean(value: object, where: str) -> bool:
    """Read a boolean."""
    if not isinstance(value, bool):
        _expected(where, "a boolean", value)
    return value


def _big(value: object, where: str, bounds: tuple[int, int], name: str) -> int:
    if not isinstance(value, str):
        _expected(where, "an integer string", value)
    if len(value) > 80 or _DECIMAL.fullmatch(value) is None:  # noqa: PLR2004
        _fail(where, f"{show(value)} is not a base 10 integer")
    number = int(value)
    if not bounds[0] <= number <= bounds[1]:
        _fail(where, f"{show(number)} is out of range for {name}")
    return number


def uint128(value: object, where: str) -> tuple[int, int]:
    """Read a `UInt128Parts`, which SEP-51 writes as one integer string: (hi, lo)."""
    number = _big(value, where, (0, 2**128 - 1), "uint128")
    return number >> 64, number & _UINT64_MASK


def int128(value: object, where: str) -> tuple[int, int]:
    """Read an `Int128Parts`, written as one integer string: (hi, lo)."""
    number = _big(value, where, (-(2**127), 2**127 - 1), "int128")
    return number >> 64, number & _UINT64_MASK


def uint256(value: object, where: str) -> tuple[int, int, int, int]:
    """Read a `UInt256Parts`, written as one integer string: (hi_hi, ..., lo_lo)."""
    number = _big(value, where, (0, 2**256 - 1), "uint256")
    return _split256(number)


def int256(value: object, where: str) -> tuple[int, int, int, int]:
    """Read an `Int256Parts`, written as one integer string: (hi_hi, ..., lo_lo)."""
    number = _big(value, where, (-(2**255), 2**255 - 1), "int256")
    return _split256(number)


def _split256(number: int) -> tuple[int, int, int, int]:
    # The arithmetic shift keeps the sign in the highest part.
    return (
        number >> 192,
        (number >> 128) & _UINT64_MASK,
        (number >> 64) & _UINT64_MASK,
        number & _UINT64_MASK,
    )


def join128(hi: int, lo: int) -> str:
    """Write the parts of a 128-bit integer as one integer string."""
    return str((hi << 64) | lo)


def join256(hi_hi: int, hi_lo: int, lo_hi: int, lo_lo: int) -> str:
    """Write the parts of a 256-bit integer as one integer string."""
    return str((hi_hi << 192) | (hi_lo << 128) | (lo_hi << 64) | lo_lo)


# --- Opaque data and strings ----------------------------------------------------


def _hex(value: object, where: str) -> bytes:
    # bytes.fromhex alone would accept spaces between bytes.
    if not isinstance(value, str):
        _expected(where, "a hex string", value)
    if _HEX.fullmatch(value) is None:
        _fail(where, f"{show(value)} is not hex with two digits per byte")
    return bytes.fromhex(value)


def hex_fixed(value: object, where: str, size: int) -> bytes:
    """Read fixed-length opaque data from hex."""
    data = _hex(value, where)
    if len(data) != size:
        _fail(where, f"expected {size} bytes, got {len(data)}")
    return data


def hex_var(value: object, where: str, max_size: int | None) -> bytes:
    """Read variable-length opaque data from hex."""
    data = _hex(value, where)
    if max_size is not None and len(data) > max_size:
        _fail(where, f"expected at most {max_size} bytes, got {len(data)}")
    return data


_ESCAPES: Final = {0: "\\0", 9: "\\t", 10: "\\n", 13: "\\r", 92: "\\\\"}
_UNESCAPES: Final = {"0": 0, "t": 9, "n": 10, "r": 13, "\\": 92}


def escape(data: bytes) -> str:
    """Write a string: printable ASCII as it is, every other byte escaped."""
    if data.isascii() and data.isalnum():
        return data.decode("ascii")
    parts: list[str] = []
    for byte in data:
        if byte in _ESCAPES:
            parts.append(_ESCAPES[byte])
        elif 0x20 <= byte <= 0x7E:  # noqa: PLR2004
            parts.append(chr(byte))
        else:
            parts.append(f"\\x{byte:02x}")
    return "".join(parts)


def unescape(value: object, where: str) -> bytes:
    """Read a string, written with SEP-51 escapes.

    Characters outside ASCII are accepted as they are and stand for their UTF-8
    encoding, so that text can be typed without escaping it.
    """
    if not isinstance(value, str):
        _expected(where, "a string", value)
    try:
        if "\\" not in value:
            return value.encode()
        return _unescape(value, where)
    except UnicodeEncodeError:
        # json.loads accepts a lone surrogate, such as "\ud800", which has no UTF-8.
        _fail(where, "a lone surrogate has no UTF-8 encoding")


def _unescape(value: str, where: str) -> bytes:
    result = bytearray()
    i = 0
    while i < len(value):
        c = value[i]
        if c != "\\":
            result += c.encode()
            i += 1
            continue
        code = value[i + 1 : i + 2]
        if code in _UNESCAPES:
            result.append(_UNESCAPES[code])
            i += 2
        elif code == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", value[i + 2 : i + 4]):
            result.append(int(value[i + 2 : i + 4], 16))
            i += 4
        else:
            _fail(where, f"invalid escape {show(value[i : i + 4])}")
    return bytes(result)


def string(value: object, where: str, max_size: int | None) -> bytes:
    """Read a string and check its length in bytes."""
    data = unescape(value, where)
    if max_size is not None and len(data) > max_size:
        _fail(where, f"expected at most {max_size} bytes, got {len(data)}")
    return data


def asset_code4(code: bytes) -> str:
    """Write an `AssetCode4`: the code without its trailing zero bytes."""
    return escape(code.rstrip(b"\0"))


def asset_code12(code: bytes) -> str:
    """Write an `AssetCode12`: trailing zero bytes removed, but at least 5 bytes.

    Keeping 5 bytes tells it apart from an `AssetCode4`.
    """
    return escape(code.rstrip(b"\0").ljust(5, b"\0"))


def read_asset_code4(value: object, where: str) -> bytes:
    """Read an `AssetCode4`: at most 4 bytes, padded with zero bytes."""
    data = unescape(value, where)
    if len(data) > 4:  # noqa: PLR2004
        _fail(where, f"expected at most 4 bytes, got {len(data)}")
    return data.ljust(4, b"\0")


def read_asset_code12(value: object, where: str) -> bytes:
    """Read an `AssetCode12`: 5 to 12 bytes, padded with zero bytes."""
    data = unescape(value, where)
    if not 5 <= len(data) <= 12:  # noqa: PLR2004
        _fail(where, f"expected 5 to 12 bytes, got {len(data)}")
    return data.ljust(12, b"\0")


def read_asset_code(value: object, where: str) -> bytes:
    """Read an `AssetCode`, whose length says which arm it is.

    Up to 4 bytes is an `AssetCode4`, which may be empty when its code is all zero
    bytes; 5 to 12 bytes is an `AssetCode12`.
    """
    data = unescape(value, where)
    if len(data) > 12:  # noqa: PLR2004
        _fail(where, f"expected at most 12 bytes, got {len(data)}")
    return data


# --- Containers -----------------------------------------------------------------


def array(value: object, where: str, max_count: int | None) -> list[object]:
    """Read a variable-length array."""
    if not isinstance(value, list):
        _expected(where, "an array", value)
    items: list[object] = value  # pyright: ignore[reportUnknownVariableType]
    if max_count is not None and len(items) > max_count:
        _fail(where, f"expected at most {max_count} items, got {len(items)}")
    return items


def items(
    values: list[object], where: str, read: Callable[[object], _V]
) -> tuple[_V, ...]:
    """Read the items of an array, saying which item is wrong if one is."""
    result: list[_V] = []
    for i, value in enumerate(values):
        try:
            result.append(read(value))
        except XdrJsonError as e:
            msg = f"{where}[{i}]: {e}"
            raise XdrJsonError(msg) from None
    return tuple(result)


def array_fixed(value: object, where: str, count: int) -> list[object]:
    """Read a fixed-length array."""
    items = array(value, where, None)
    if len(items) != count:
        _fail(where, f"expected {count} items, got {len(items)}")
    return items


def fields(
    value: object,
    where: str,
    names: tuple[str, ...],
    optional: frozenset[str] = frozenset(),
) -> Mapping[str, object]:
    """Read the object of a struct, which must have exactly its fields.

    An optional field may be left out, which reads as null, and a `$schema` key is
    allowed and ignored, as SEP-51 specifies.
    """
    if not isinstance(value, dict):
        _expected(where, "an object", value)
    obj: dict[str, object] = value  # pyright: ignore[reportUnknownVariableType]
    if len(obj) != len(names) or obj.keys() != set(names):
        keys = set(obj) - {_SCHEMA}
        missing = [n for n in names if n not in keys and n not in optional]
        unknown = sorted(show(k) for k in keys - set(names))
        if missing:
            _fail(where, f"missing {', '.join(missing)}")
        if unknown:
            _fail(where, f"unknown {', '.join(unknown)}")
    return obj


def union(
    value: object, where: str, arms: Mapping[str, _V], void: frozenset[str]
) -> tuple[_V, object]:
    """Read a union: the name of a void arm, or an object with one key.

    Returns the arm and the JSON value of its payload, `None` for a void arm.
    `{"name": null}` is accepted for a void arm too, and `$schema` is ignored.
    """
    if isinstance(value, str):
        if value in void:
            return arms[value], None
        if value in arms:
            _fail(where, f"{show(value)} needs a value")
        _fail(where, f"unknown arm {show(value)}")
    if not isinstance(value, dict):
        _expected(where, "a string or an object", value)
    obj: dict[str, object] = value  # pyright: ignore[reportUnknownVariableType]
    keys = [k for k in obj if k != _SCHEMA]
    if len(keys) != 1:
        _fail(where, f"expected one key, got {len(keys)}")
    key = keys[0]
    if key not in arms:
        _fail(where, f"unknown arm {show(key)}")
    payload = obj[key]
    if key in void and payload is not None:
        _fail(where, f"{show(key)} holds no value")
    return arms[key], payload


def enum(value: object, where: str, members: Mapping[str, _V]) -> _V:
    """Read an enum member from its name."""
    if not isinstance(value, str):
        _expected(where, "a string", value)
    member = members.get(value)
    if member is None:
        _fail(where, f"unknown member {show(value)}")
    return member


def inverse(names: Mapping[_K, str]) -> dict[str, _K]:
    """Map JSON names back to members."""
    return {name: member for member, name in names.items()}


# --- Strkeys --------------------------------------------------------------------


def parse_strkey(value: object, where: str) -> strkey.Strkey:
    """Read any strkey."""
    if not isinstance(value, str):
        _expected(where, "a strkey string", value)
    try:
        return strkey.parse(value)
    except strkey.StrkeyError as e:
        _fail(where, str(e))


def wrong_strkey(where: str, key: strkey.Strkey) -> NoReturn:
    """Report a valid strkey of a type the field doesn't take."""
    _fail(where, f"a {type(key).__name__} strkey is not allowed here")


def account(key: bytes) -> str:
    """Write an ed25519 public key as a G... strkey."""
    return str(strkey.Ed25519PublicKey(key))


def muxed_account(key: bytes, id_: int) -> str:
    """Write a muxed account as an M... strkey."""
    return str(strkey.MuxedEd25519Account(key, id_))


def contract(hash_: bytes) -> str:
    """Write a contract ID as a C... strkey."""
    return str(strkey.Contract(hash_))


def muxed_contract(hash_: bytes, id_: int) -> str:
    """Write a muxed contract as a W... strkey."""
    return str(strkey.MuxedContract(hash_, id_))


def liquidity_pool(hash_: bytes) -> str:
    """Write a liquidity pool ID as an L... strkey."""
    return str(strkey.LiquidityPool(hash_))


def claimable_balance(hash_: bytes) -> str:
    """Write a claimable balance ID as a B... strkey."""
    return str(strkey.ClaimableBalance(hash_))


def pre_auth_tx(hash_: bytes) -> str:
    """Write a pre-authorized transaction signer as a T... strkey."""
    return str(strkey.PreAuthTx(hash_))


def hash_x(hash_: bytes) -> str:
    """Write a hash(x) signer as an X... strkey."""
    return str(strkey.HashX(hash_))


def signed_payload(key: bytes, payload: bytes) -> str:
    """Write a signed payload signer as a P... strkey.

    XDR allows an empty payload, but a strkey needs 1 to 64 bytes, so such a value has
    no SEP-51 representation.
    """
    try:
        return str(strkey.Ed25519SignedPayload(key, payload))
    except ValueError as e:
        msg = f"SignerKeyEd25519SignedPayload has no SEP-51 representation: {e}"
        raise XdrJsonError(msg) from None


def read_contract(value: object, where: str) -> bytes:
    """Read a C... strkey."""
    key = parse_strkey(value, where)
    if not isinstance(key, strkey.Contract):
        wrong_strkey(where, key)
    return key.hash


def read_liquidity_pool(value: object, where: str) -> bytes:
    """Read an L... strkey."""
    key = parse_strkey(value, where)
    if not isinstance(key, strkey.LiquidityPool):
        wrong_strkey(where, key)
    return key.hash


def read_muxed_account(value: object, where: str) -> tuple[bytes, int]:
    """Read an M... strkey: (key, id)."""
    key = parse_strkey(value, where)
    if not isinstance(key, strkey.MuxedEd25519Account):
        wrong_strkey(where, key)
    return key.key, key.id


def read_muxed_contract(value: object, where: str) -> tuple[bytes, int]:
    """Read a W... strkey: (hash, id)."""
    key = parse_strkey(value, where)
    if not isinstance(key, strkey.MuxedContract):
        wrong_strkey(where, key)
    return key.hash, key.id


def read_signed_payload(value: object, where: str) -> tuple[bytes, bytes]:
    """Read a P... strkey: (key, payload)."""
    key = parse_strkey(value, where)
    if not isinstance(key, strkey.Ed25519SignedPayload):
        wrong_strkey(where, key)
    return key.key, key.payload
