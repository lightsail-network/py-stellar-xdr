"""The hand-written part of the package, used by the generated modules."""

from typing import TYPE_CHECKING, Any, TypeVar

from . import _check as check
from . import _json as xdr_json
from ._base import (
    UnionNamespace,
    XdrArm,
    XdrArray,
    XdrBytes,
    XdrEnum,
    XdrInt,
    XdrStruct,
    decode_stream,
    encode_stream,
    replace,
)
from ._codec import DEFAULT_MAX_DEPTH, Reader, Writer, decode_base64, decode_bytes
from ._errors import XdrDecodeError, XdrDepthError, XdrError, XdrJsonError
from ._json import JsonReader, JsonWriter, decode_json, encode_json

new = object.__new__
"""Create an instance without calling `__init__`, for decoded values."""

new_bytes = bytes.__new__
new_int = int.__new__
"""Create a typedef's value from a plain value that is already checked or decoded."""

if TYPE_CHECKING:
    from collections.abc import Iterable

    _Array = TypeVar("_Array", bound=tuple[Any, ...])

    # tuple.__new__ wants items of the tuple's type; the checks return objects.
    def new_tuple(cls: type[_Array], items: Iterable[Any], /) -> _Array:
        """Create an array typedef's value from items that are already checked."""
        ...
else:
    new_tuple = tuple.__new__

set_field = object.__setattr__
"""Set a field of an immutable instance, for constructors and decoders."""

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "JsonReader",
    "JsonWriter",
    "Reader",
    "UnionNamespace",
    "Writer",
    "XdrArm",
    "XdrArray",
    "XdrBytes",
    "XdrDecodeError",
    "XdrDepthError",
    "XdrEnum",
    "XdrError",
    "XdrInt",
    "XdrJsonError",
    "XdrStruct",
    "check",
    "decode_base64",
    "decode_bytes",
    "decode_json",
    "decode_stream",
    "encode_json",
    "encode_stream",
    "new",
    "new_bytes",
    "new_int",
    "new_tuple",
    "replace",
    "set_field",
    "xdr_json",
]
