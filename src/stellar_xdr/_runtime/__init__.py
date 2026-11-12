"""The hand-written part of the package, used by the generated modules."""

from . import _check as check
from . import _json as xdr_json
from ._base import (
    UnionNamespace,
    XdrArm,
    XdrEnum,
    XdrStruct,
    decode_stream,
    encode_stream,
    replace,
)
from ._codec import DEFAULT_MAX_DEPTH, Reader, Writer, decode_base64, decode_bytes
from ._errors import XdrDecodeError, XdrDepthError, XdrError, XdrJsonError
from ._json import JsonReader, JsonWriter, decode_json, encode_json
from ._typedef import Typedef

new = object.__new__
"""Create an instance without calling `__init__`, for decoded values."""

set_field = object.__setattr__
"""Set a field of an immutable instance, for constructors and decoders."""

__all__ = [
    "DEFAULT_MAX_DEPTH",
    "JsonReader",
    "JsonWriter",
    "Reader",
    "Typedef",
    "UnionNamespace",
    "Writer",
    "XdrArm",
    "XdrDecodeError",
    "XdrDepthError",
    "XdrEnum",
    "XdrError",
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
    "replace",
    "set_field",
    "xdr_json",
]
