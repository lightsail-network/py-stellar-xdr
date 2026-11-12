"""Argument checks for the generated constructors.

Every check takes the value and a description of where it goes (such as
`"SCVal.U32.u32"`), followed by its own arguments, and returns the value to store. They
share that shape so that checks for arrays and optional values can take the check of
their elements as an argument.

A check raises `TypeError` for a value of the wrong type and `ValueError` for a value of
the right type that XDR can't represent, so that any constructed value can be encoded.
"""

from collections.abc import Callable, Sequence
from typing import Any, Final, cast

_INT32_MIN: Final = -(2**31)
_INT32_MAX: Final = 2**31 - 1
_UINT32_MAX: Final = 2**32 - 1
_INT64_MIN: Final = -(2**63)
_INT64_MAX: Final = 2**63 - 1
_UINT64_MAX: Final = 2**64 - 1

# str() of an int with more than 4,300 digits raises ValueError, so a message only
# quotes an integer that is no longer than the longest XDR-JSON one, of 256 bits.
_MAX_SHOWN_BITS: Final = 256

Check = Callable[..., Any]


def _type_error(where: str, expected: str, value: object) -> TypeError:
    return TypeError(f"{where}: expected {expected}, got {type(value).__name__}")


def _integer(value: object, where: str, low: int, high: int, name: str) -> int:
    # bool is a subclass of int, but True is not a sensible integer argument.
    if not isinstance(value, int) or isinstance(value, bool):
        raise _type_error(where, "int", value)
    if not low <= value <= high:
        shown = value if value.bit_length() <= _MAX_SHOWN_BITS else "a huge number"
        msg = f"{where}: {shown} is out of range for {name}"
        raise ValueError(msg)
    # A subclass such as an IntEnum member is stored as a plain int.
    return value if value.__class__ is int else int(value)


def int32(value: object, where: str) -> int:
    """Check a signed 32-bit integer."""
    return _integer(value, where, _INT32_MIN, _INT32_MAX, "int32")


def uint32(value: object, where: str) -> int:
    """Check an unsigned 32-bit integer."""
    return _integer(value, where, 0, _UINT32_MAX, "uint32")


def int64(value: object, where: str) -> int:
    """Check a signed 64-bit integer."""
    return _integer(value, where, _INT64_MIN, _INT64_MAX, "int64")


def uint64(value: object, where: str) -> int:
    """Check an unsigned 64-bit integer."""
    return _integer(value, where, 0, _UINT64_MAX, "uint64")


def boolean(value: object, where: str) -> bool:
    """Check a boolean."""
    if value.__class__ is not bool:
        raise _type_error(where, "bool", value)
    return value is True


def _bytes(value: object, where: str) -> bytes:
    if isinstance(value, bytes):
        # A subclass is stored as plain bytes.
        return value if value.__class__ is bytes else bytes(value)
    raise _type_error(where, "bytes", value)


def opaque_fixed(value: object, where: str, size: int) -> bytes:
    """Check fixed-length opaque data."""
    data = _bytes(value, where)
    if len(data) != size:
        msg = f"{where}: expected {size} bytes, got {len(data)}"
        raise ValueError(msg)
    return data


def opaque_var(value: object, where: str, max_size: int | None) -> bytes:
    """Check variable-length opaque data."""
    data = _bytes(value, where)
    if max_size is not None and len(data) > max_size:
        msg = f"{where}: expected at most {max_size} bytes, got {len(data)}"
        raise ValueError(msg)
    return data


def string(value: object, where: str, max_size: int | None) -> bytes:
    """Check a string, which is stored as bytes; `str` is encoded as UTF-8."""
    if isinstance(value, str):
        try:
            value = value.encode()
        except UnicodeEncodeError:
            msg = f"{where}: a lone surrogate has no UTF-8 encoding"
            raise ValueError(msg) from None
    elif not isinstance(value, bytes):
        raise _type_error(where, "bytes or str", value)
    return opaque_var(value, where, max_size)


def instance(value: object, where: str, cls: type[Any]) -> object:
    """Check an enum member or a struct, whose classes are final."""
    if value.__class__ is not cls:
        raise _type_error(where, cls.__qualname__, value)
    return value


def union(value: object, where: str, arms: frozenset[type[Any]], name: str) -> object:
    """Check a value of a union, which is an instance of one of its arm classes."""
    if value.__class__ not in arms:
        raise _type_error(where, f"{name}.Any", value)
    return value


def optional(value: object, where: str, check: Check, *args: object) -> object:
    """Check an optional value: `None` or a value that passes `check`."""
    if value is None:
        return None
    return check(value, where, *args)


def array(
    value: object, where: str, max_count: int | None, check: Check, *args: object
) -> tuple[object, ...]:
    """Check a variable-length array and its elements, and return it as a tuple."""
    # str and bytes are sequences, but of characters and integers, never of XDR values.
    if isinstance(value, tuple | list) or (
        isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray)
    ):
        items = tuple(cast("Sequence[object]", value))
    else:
        raise _type_error(where, "a sequence", value)
    if max_count is not None and len(items) > max_count:
        msg = f"{where}: expected at most {max_count} items, got {len(items)}"
        raise ValueError(msg)
    try:
        return tuple([check(item, where, *args) for item in items])
    except (TypeError, ValueError):
        # Check again with the index in the description, so that the error says
        # which item is wrong, without building a description for every item.
        for i, item in enumerate(items):
            check(item, f"{where}[{i}]", *args)
        raise  # pragma: no cover - the loop above raises the same error first


def array_fixed(
    value: object, where: str, count: int, check: Check, *args: object
) -> tuple[object, ...]:
    """Check a fixed-length array and its elements, and return it as a tuple."""
    items = array(value, where, None, check, *args)
    if len(items) != count:
        msg = f"{where}: expected {count} items, got {len(items)}"
        raise ValueError(msg)
    return items
