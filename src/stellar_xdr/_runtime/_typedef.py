"""Codecs for typedefs, which are type aliases rather than classes."""

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from ._base import decode_json, encode_into_writer, encode_json
from ._codec import (
    DEFAULT_MAX_DEPTH,
    Reader,
    Writer,
    decode_base64,
    decode_bytes,
    encode_base64,
)
from ._json import JsonReader, JsonWriter

_Value = TypeVar("_Value")
_Input = TypeVar("_Input")


class Typedef(Generic[_Value, _Input]):
    """The codec of a typedef, such as `typedefs.LedgerEntryChanges`.

    A typedef such as `LedgerEntryChanges` is a type alias, here of
    `tuple[LedgerEntryChange.Any, ...]`, so it has no methods of its own. Its codec
    encodes and decodes values of that type.
    """

    __slots__ = ("_check", "_decode", "_encode", "_from_json", "_to_json", "name")

    name: str
    """The name of the typedef in the XDR definitions."""

    def __init__(  # noqa: PLR0913 - one function per conversion
        self,
        name: str,
        *,
        check: Callable[[object, str], _Value],
        encode: Callable[[Writer, _Value], None],
        decode: Callable[[Reader], _Value],
        to_json: Callable[[_Value, JsonWriter], object],
        from_json: Callable[[object, JsonReader], _Value],
    ) -> None:
        self.name = name
        self._check = check
        self._encode = encode
        self._decode = decode
        self._to_json = to_json
        self._from_json = from_json

    def __repr__(self) -> str:
        return f"<typedef {self.name}>"

    def to_xdr_bytes(
        self, value: _Input, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> bytes:
        """Check a value and encode it as XDR.

        Args:
            value: A value of the typedef's type. Like a constructor argument, any
                sequence is accepted for an array, and `str` for a string.
            max_depth: The deepest nesting of recursive types to encode.

        Raises:
            TypeError: The value has the wrong type.
            ValueError: The value is out of range.
            XdrDepthError: The value is nested more deeply than `max_depth`.
        """
        checked = self._check(value, self.name)
        writer = Writer(max_depth)
        encode_into_writer(lambda w: self._encode(w, checked), writer)
        return bytes(writer.buffer)

    def to_xdr_base64(
        self, value: _Input, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> str:
        """Check a value and encode it as XDR in base64.

        Args:
            value: A value of the typedef's type.
            max_depth: The deepest nesting of recursive types to encode.

        Raises:
            TypeError: The value has the wrong type.
            ValueError: The value is out of range.
            XdrDepthError: The value is nested more deeply than `max_depth`.
        """
        return encode_base64(self.to_xdr_bytes(value, max_depth=max_depth))

    def from_xdr_bytes(
        self, data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> _Value:
        """Decode a value from XDR.

        Args:
            data: The encoded value, and nothing else.
            max_depth: The deepest nesting of recursive types to accept.

        Raises:
            XdrDecodeError: The data is not a valid encoding of the type.
            XdrDepthError: The data is nested more deeply than `max_depth`.
        """
        return decode_bytes(self._decode, data, max_depth)

    def from_xdr_base64(
        self, text: str | bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> _Value:
        """Decode a value from XDR in base64.

        Args:
            text: Canonical, padded standard base64 of the encoded value.
            max_depth: The deepest nesting of recursive types to accept.

        Raises:
            XdrDecodeError: The text is not valid base64, or not a valid encoding of
                the type.
            XdrDepthError: The data is nested more deeply than `max_depth`.
        """
        return decode_bytes(self._decode, decode_base64(text), max_depth)

    def to_json_value(
        self,
        value: _Input,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> Any:  # noqa: ANN401 - a JSON value
        """Check a value and convert it to SEP-51 XDR-JSON.

        Args:
            value: A value of the typedef's type.
            max_depth: The deepest nesting of recursive types to convert.

        Raises:
            TypeError: The value has the wrong type.
            ValueError: The value is out of range.
            XdrDepthError: The value is nested more deeply than `max_depth`.
            XdrJsonError: SEP-51 can't represent the value.
        """
        checked = self._check(value, self.name)
        return encode_json(lambda ctx: self._to_json(checked, ctx), max_depth)

    def from_json_value(
        self, value: object, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> _Value:
        """Convert SEP-51 XDR-JSON to a value.

        Args:
            value: A JSON value, as `json.loads` returns it.
            max_depth: The deepest nesting of recursive types to accept.

        Raises:
            XdrJsonError: The JSON is not a valid representation of the type.
            XdrDepthError: The JSON is nested more deeply than `max_depth`.
        """
        return decode_json(self._from_json, value, max_depth)
