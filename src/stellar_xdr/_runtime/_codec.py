"""Reading and writing the XDR binary encoding (RFC 4506)."""

import binascii
import struct
from collections.abc import Callable
from typing import Final, NoReturn, TypeVar

from ._errors import XdrDecodeError, XdrDepthError

# Only recursive types, such as SCVal, count towards the depth. Soroban accepts
# contract values nested up to 100 levels, so the default leaves room above that.
DEFAULT_MAX_DEPTH: Final = 200

_INT32: Final = struct.Struct(">i")
_UINT32: Final = struct.Struct(">I")
_INT64: Final = struct.Struct(">q")
_UINT64: Final = struct.Struct(">Q")

_PADDING: Final = (b"", b"\x00\x00\x00", b"\x00\x00", b"\x00")

_T = TypeVar("_T")


def check_max_depth(max_depth: object) -> int:
    """Check a `max_depth` argument: a non-negative int."""
    # Anything else, such as NaN, could make the depth check never fail.
    if not isinstance(max_depth, int) or isinstance(max_depth, bool):
        msg = f"max_depth: expected int, got {type(max_depth).__name__}"
        raise TypeError(msg)
    if max_depth < 0:
        msg = f"max_depth: {max_depth} is negative"
        raise ValueError(msg)
    return max_depth


class Reader:
    """Reads values from XDR input, keeping track of the offset and the depth."""

    __slots__ = ("data", "depth", "max_depth", "pos")

    def __init__(self, data: bytes, max_depth: int) -> None:
        self.data = data
        self.pos = 0
        self.depth = 0
        self.max_depth = check_max_depth(max_depth)

    def error(self, message: str) -> XdrDecodeError:
        """Build an error that says where in the input the problem is."""
        return XdrDecodeError(f"{message} at offset {self.pos}")

    def enter(self) -> None:
        """Count one more level of nesting of a recursive type."""
        self.depth += 1
        if self.depth > self.max_depth:
            msg = f"nesting deeper than max_depth={self.max_depth} at offset {self.pos}"
            raise XdrDepthError(msg)

    def int32(self) -> int:
        """Read a signed 32-bit integer."""
        value: int = _INT32.unpack_from(self.data, self.pos)[0]
        self.pos += 4
        return value

    def uint32(self) -> int:
        """Read an unsigned 32-bit integer."""
        value: int = _UINT32.unpack_from(self.data, self.pos)[0]
        self.pos += 4
        return value

    def int64(self) -> int:
        """Read a signed 64-bit integer."""
        value: int = _INT64.unpack_from(self.data, self.pos)[0]
        self.pos += 8
        return value

    def uint64(self) -> int:
        """Read an unsigned 64-bit integer."""
        value: int = _UINT64.unpack_from(self.data, self.pos)[0]
        self.pos += 8
        return value

    def boolean(self) -> bool:
        """Read a boolean, which must be encoded as 0 or 1."""
        value = self.uint32()
        if value > 1:
            self.pos -= 4
            raise self.error(f"invalid bool {value}")
        return value == 1

    def present(self) -> bool:
        """Read the flag in front of an optional value, which must be 0 or 1."""
        value = self.uint32()
        if value > 1:
            self.pos -= 4
            raise self.error(f"invalid optional flag {value}")
        return value == 1

    def count(self, max_count: int | None, min_size: int) -> int:
        """Read the length of a variable-length array.

        The length is checked against what the remaining input can hold before the
        array is allocated, so a short input can't claim a huge array.
        """
        count = self.uint32()
        if max_count is not None and count > max_count:
            self.pos -= 4
            raise self.error(f"array length {count} exceeds the maximum {max_count}")
        if count > (len(self.data) - self.pos) // min_size:
            self.pos -= 4
            raise self.error(f"array length {count} exceeds the remaining input")
        return count

    def opaque_fixed(self, size: int) -> bytes:
        """Read fixed-length opaque data and its padding."""
        start = self.pos
        end = start + size
        padded = end + (-size % 4)
        if padded > len(self.data):
            raise self.error("unexpected end of input")
        if self.data[end:padded].count(0) != padded - end:
            self.pos = end
            raise self.error("non-zero padding")
        self.pos = padded
        return self.data[start:end]

    def opaque_aligned(self, size: int) -> bytes:
        """Read fixed-length opaque data whose length is a multiple of 4.

        Most fixed-length data, such as hashes and keys, has no padding to check.
        """
        start = self.pos
        end = start + size
        if end > len(self.data):
            raise self.error("unexpected end of input")
        self.pos = end
        return self.data[start:end]

    def opaque_var(self, max_size: int | None) -> bytes:
        """Read variable-length opaque data, its length and its padding."""
        size = self.uint32()
        if max_size is not None and size > max_size:
            self.pos -= 4
            raise self.error(f"length {size} exceeds the maximum {max_size}")
        if size > len(self.data) - self.pos:
            self.pos -= 4
            raise self.error(f"length {size} exceeds the remaining input")
        return self.opaque_fixed(size)

    def unknown(self, union: str, discriminant: int) -> NoReturn:
        """Report a discriminant that selects no arm of a union."""
        self.pos -= 4
        raise self.error(f"unknown {union} discriminant {discriminant}")

    def unknown_enum(self, enum: str, value: int) -> NoReturn:
        """Report a value that is not a member of an enum."""
        self.pos -= 4
        raise self.error(f"unknown {enum} value {value}")


class Writer:
    """Collects the encoding of values, keeping track of the depth."""

    __slots__ = ("buffer", "depth", "max_depth")

    def __init__(self, max_depth: int) -> None:
        self.buffer = bytearray()
        self.depth = 0
        self.max_depth = check_max_depth(max_depth)

    def enter(self) -> None:
        """Count one more level of nesting of a recursive type."""
        self.depth += 1
        if self.depth > self.max_depth:
            raise XdrDepthError(f"value nested deeper than max_depth={self.max_depth}")

    def int32(self, value: int) -> None:
        """Write a signed 32-bit integer."""
        self.buffer += _INT32.pack(value)

    def uint32(self, value: int) -> None:
        """Write an unsigned 32-bit integer."""
        self.buffer += _UINT32.pack(value)

    def int64(self, value: int) -> None:
        """Write a signed 64-bit integer."""
        self.buffer += _INT64.pack(value)

    def uint64(self, value: int) -> None:
        """Write an unsigned 64-bit integer."""
        self.buffer += _UINT64.pack(value)

    def boolean(self, value: bool) -> None:  # noqa: FBT001 - mirrors the other writers
        """Write a boolean."""
        self.buffer += _UINT32.pack(value)

    def opaque_fixed(self, value: bytes) -> None:
        """Write fixed-length opaque data and its padding."""
        self.buffer += value
        self.buffer += _PADDING[len(value) % 4]

    def opaque_var(self, value: bytes) -> None:
        """Write variable-length opaque data, its length and its padding."""
        self.buffer += _UINT32.pack(len(value))
        self.buffer += value
        self.buffer += _PADDING[len(value) % 4]


def decode_bytes(decode: Callable[[Reader], _T], data: bytes, max_depth: int) -> _T:
    """Decode one value that must take up the whole input."""
    # Checked at runtime too: bytes(...) would accept an int or a list.
    if not isinstance(data, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"expected bytes, got {type(data).__name__}"
        raise TypeError(msg)
    reader = Reader(bytes(data), max_depth)
    value = decode_from(decode, reader)
    if reader.pos != len(reader.data):
        msg = f"{len(reader.data) - reader.pos} unexpected bytes after the value"
        raise reader.error(msg)
    return value


def decode_from(decode: Callable[[Reader], _T], reader: Reader) -> _T:
    """Decode one value, turning low-level failures into the package's errors."""
    try:
        return decode(reader)
    except struct.error:
        raise reader.error("unexpected end of input") from None
    except RecursionError:
        # Only reachable when max_depth is set above what Python's recursion limit
        # allows; the depth check catches everything else first.
        msg = f"nesting deeper than Python's recursion limit at offset {reader.pos}"
        raise XdrDepthError(msg) from None


def decode_base64(text: str | bytes) -> bytes:
    """Decode canonical, padded standard base64."""
    if isinstance(text, str):
        if not text.isascii():
            raise XdrDecodeError("invalid base64: non-ASCII character")
        raw = text.encode("ascii")
    elif isinstance(text, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        raw = text
    else:
        msg = f"expected str or bytes, got {type(text).__name__}"
        raise TypeError(msg)
    try:
        data = binascii.a2b_base64(raw, strict_mode=True)
    except binascii.Error as e:
        raise XdrDecodeError(f"invalid base64: {e}") from None
    # strict_mode still accepts non-zero bits after the last full byte, such as
    # "AAAAAR==", so only the canonical encoding of the result is accepted.
    if binascii.b2a_base64(data, newline=False) != raw:
        raise XdrDecodeError("invalid base64: not canonical")
    return data


def encode_base64(data: bytes) -> str:
    """Encode standard, padded base64."""
    return binascii.b2a_base64(data, newline=False).decode("ascii")
