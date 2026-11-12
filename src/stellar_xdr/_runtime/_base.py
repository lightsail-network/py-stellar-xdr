"""Base classes of the generated types, and the functions that work on any of them.

The generated classes hold only what differs between types: their fields, constructor,
equality, hashing and codec. Everything else is written once here.

The classes are not dataclasses. The `dataclasses` decorator generates and compiles
several functions for each class when it is defined, so with roughly 800 classes every
process spent about 110 ms importing the package instead of 20 ms. `dataclass_transform`
still lets type checkers treat the classes as frozen dataclasses. The cost is that
`dataclasses.fields`, `asdict` and `replace` don't apply to them; `copy.replace` and
`replace` here take the place of the last. Going the other way later, to real
dataclasses, would only add features, so it stays possible.
"""

# The functions at the end call the codec methods of any generated class.
# pyright: reportPrivateUsage=false

from collections.abc import Callable, Iterable, Iterator
from dataclasses import FrozenInstanceError
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    NoReturn,
    Protocol,
    Self,
    TypeVar,
    dataclass_transform,
)

from ._codec import (
    DEFAULT_MAX_DEPTH,
    Reader,
    Writer,
    decode_base64,
    decode_bytes,
    decode_from,
    encode_base64,
)
from ._errors import XdrDepthError
from ._json import JsonReader, JsonWriter

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)


class _Encodable:
    """The encoding methods shared by every generated type."""

    __slots__ = ()

    def _encode(self, writer: Writer) -> None:
        raise NotImplementedError  # pragma: no cover - every type defines it

    def to_xdr_bytes(self, *, max_depth: int = DEFAULT_MAX_DEPTH) -> bytes:
        """Encode the value as XDR.

        Args:
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                encode.

        Raises:
            XdrDepthError: The value is nested more deeply than `max_depth`.
        """
        writer = Writer(max_depth)
        encode_into(self, writer)
        return bytes(writer.buffer)

    def to_xdr_base64(self, *, max_depth: int = DEFAULT_MAX_DEPTH) -> str:
        """Encode the value as XDR in base64, the form used by Stellar's APIs.

        Args:
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                encode.

        Raises:
            XdrDepthError: The value is nested more deeply than `max_depth`.
        """
        return encode_base64(self.to_xdr_bytes(max_depth=max_depth))

    def _to_json(self, ctx: JsonWriter) -> Any:  # noqa: ANN401 - a JSON value
        raise NotImplementedError  # pragma: no cover - every type defines it

    def to_json_value(self, *, max_depth: int = DEFAULT_MAX_DEPTH) -> Any:  # noqa: ANN401
        """Convert the value to SEP-51 XDR-JSON.

        Returns a JSON value: a `dict`, `list`, `str`, `int` or `bool`, ready for
        `json.dumps`.

        Args:
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                convert.

        Raises:
            XdrDepthError: The value is nested more deeply than `max_depth`.
            XdrJsonError: SEP-51 can't represent the value.
        """
        return encode_json(self._to_json, max_depth)


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


def encode_into(value: _Encodable, writer: Writer) -> None:
    """Encode one value, turning a too deep recursion into `XdrDepthError`."""
    encode_into_writer(value._encode, writer)  # noqa: SLF001


def encode_into_writer(encode: Callable[[Writer], None], writer: Writer) -> None:
    """Run an encoder, turning a too deep recursion into `XdrDepthError`."""
    try:
        encode(writer)
    except RecursionError:
        # Only reachable when max_depth is set above what Python's recursion limit
        # allows; the depth check catches everything else first.
        msg = "value nested deeper than Python's recursion limit"
        raise XdrDepthError(msg) from None


# The classes the generated classes may derive from, once they exist.
_BASES: set[type] = set()


@dataclass_transform(frozen_default=True)
class _XdrValue(_Encodable):
    """Immutability, representation, pickling and copying of structs and union arms."""

    __slots__ = ()

    _fields: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # The generated classes are final: a subclass would lose the fields of its
        # parent in repr, replace and pickle, and wouldn't be accepted where its
        # parent is. @final only tells type checkers, so this tells the runtime.
        if _BASES and not all(base in _BASES for base in cls.__bases__):
            msg = f"{cls.__qualname__}: the generated classes can't be subclassed"
            raise TypeError(msg)
        # Without its own __slots__, a class would inherit the empty tuple: every
        # instance would compare equal and have an empty repr.
        if "__slots__" not in cls.__dict__:
            msg = f"{cls.__qualname__} must define __slots__"
            raise TypeError(msg)
        cls._fields = tuple(cls.__dict__["__slots__"])
        type.__setattr__(cls, "__match_args__", cls._fields)

    def __repr__(self) -> str:
        fields = ", ".join(f"{name}={getattr(self, name)!r}" for name in self._fields)
        return f"{type(self).__qualname__}({fields})"

    # Hidden from type checkers: an explicit __setattr__ would make mypy accept any
    # assignment, while dataclass_transform already reports one as an error.
    if not TYPE_CHECKING:

        def __setattr__(self, name: str, value: object) -> NoReturn:
            msg = f"can't assign to field {name!r}; use copy.replace or replace"
            raise FrozenInstanceError(msg)

        def __delattr__(self, name: str) -> NoReturn:
            msg = f"can't delete field {name!r}"
            raise FrozenInstanceError(msg)

    def __reduce__(self) -> tuple[type[Self], tuple[object, ...]]:
        return type(self), tuple(getattr(self, name) for name in self._fields)

    # Values are immutable all the way down, so copies can share them.
    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __replace__(self, /, **changes: Any) -> Self:  # noqa: ANN401 - any field
        fields = {name: getattr(self, name) for name in self._fields}
        fields.update(changes)
        return type(self)(**fields)


class XdrStruct(_XdrValue):
    """Base class of the generated structs."""

    __slots__ = ()

    @classmethod
    def _decode(cls, reader: Reader) -> Self:
        raise NotImplementedError  # pragma: no cover - every struct defines it

    @classmethod
    def from_xdr_bytes(cls, data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH) -> Self:
        """Decode a value from XDR.

        Args:
            data: The encoded value, and nothing else.
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                accept.

        Raises:
            XdrDecodeError: The data is not a valid encoding of this type.
            XdrDepthError: The data is nested more deeply than `max_depth`.
        """
        return decode_bytes(cls._decode, data, max_depth)

    @classmethod
    def from_xdr_base64(
        cls, text: str | bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> Self:
        """Decode a value from XDR in base64.

        Args:
            text: Canonical, padded standard base64 of the encoded value.
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                accept.

        Raises:
            XdrDecodeError: The text is not valid base64, or not a valid encoding of
                this type.
            XdrDepthError: The data is nested more deeply than `max_depth`.
        """
        return decode_bytes(cls._decode, decode_base64(text), max_depth)

    @classmethod
    def _from_json(cls, value: object, ctx: JsonReader) -> Self:
        raise NotImplementedError  # pragma: no cover - every struct defines it

    @classmethod
    def from_json_value(
        cls, value: object, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> Self:
        """Convert SEP-51 XDR-JSON to a value.

        Args:
            value: A JSON value, as `json.loads` returns it.
            max_depth: The deepest nesting of recursive types, such as `SCVal`, to
                accept.

        Raises:
            XdrJsonError: The JSON is not a valid representation of this type.
            XdrDepthError: The JSON is nested more deeply than `max_depth`.
        """
        return decode_json(cls._from_json, value, max_depth)


class XdrArm(_XdrValue):
    """Base class of the generated union arms.

    Arms only encode: decoding starts from the union, such as `SCVal.from_xdr_bytes`,
    because the encoding doesn't say in advance which arm it holds.
    """

    __slots__ = ()

    # An arm holds one value at most, and its class already says which arm it is, so
    # it is shown the way it is written: `SCVal.U32(5)`, not `SCVal.U32(u32=5)`.
    def __repr__(self) -> str:
        values = ", ".join([repr(getattr(self, name)) for name in self._fields])
        return f"{type(self).__qualname__}({values})"


class XdrEnum(_Encodable, IntEnum):
    """Base class of the generated enums."""

    # Shown the way it is written, like the structs and arms that hold it, rather
    # than as the `<SCValType.SCV_U32: 3>` of a plain enum.
    def __repr__(self) -> str:
        return f"{type(self).__qualname__}.{self.name}"

    def _encode(self, writer: Writer) -> None:
        writer.int32(self)

    @classmethod
    def _decode(cls, reader: Reader) -> Self:
        value = reader.int32()
        member = cls._value2member_map_.get(value)
        if member is None:
            reader.unknown_enum(cls.__name__, value)
        return member  # type: ignore[return-value]

    @classmethod
    def from_xdr_bytes(cls, data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH) -> Self:
        """Decode a member from XDR.

        Args:
            data: The encoded member, and nothing else.
            max_depth: Accepted for consistency with the other types; enums don't
                nest.

        Raises:
            XdrDecodeError: The data is not a valid encoding of a member.
        """
        return decode_bytes(cls._decode, data, max_depth)

    @classmethod
    def from_xdr_base64(
        cls, text: str | bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> Self:
        """Decode a member from XDR in base64.

        Args:
            text: Canonical, padded standard base64 of the encoded member.
            max_depth: Accepted for consistency with the other types; enums don't
                nest.

        Raises:
            XdrDecodeError: The text is not valid base64, or not a valid encoding of
                a member.
        """
        return decode_bytes(cls._decode, decode_base64(text), max_depth)

    @classmethod
    def _from_json(cls, value: object, ctx: JsonReader) -> Self:
        raise NotImplementedError  # pragma: no cover - every enum defines it

    @classmethod
    def from_json_value(
        cls, value: object, *, max_depth: int = DEFAULT_MAX_DEPTH
    ) -> Self:
        """Convert SEP-51 XDR-JSON, the member's name, to a member.

        Args:
            value: A JSON value, as `json.loads` returns it.
            max_depth: Accepted for consistency with the other types; enums don't
                nest.

        Raises:
            XdrJsonError: The JSON is not the name of a member.
        """
        return decode_json(cls._from_json, value, max_depth)


_BASES.update({XdrStruct, XdrArm})


class UnionNamespace(type):
    """Metaclass of the classes that group the arms of a union, such as `SCVal`.

    A union is not a class of its own: its values are instances of the arm classes, and
    `SCVal.Any` is the union of those. Checking `isinstance(x, SCVal)` would therefore
    always be false, so it raises instead of failing silently.
    """

    def _hint(cls) -> str:
        arm = next(v for v in vars(cls).values() if isinstance(v, type))
        return f"use {cls.__name__}.Any or an arm such as {cls.__name__}.{arm.__name__}"

    def __instancecheck__(cls, instance: object) -> bool:
        msg = f"{cls.__name__} is a namespace, not a type: {cls._hint()}"
        raise TypeError(msg)

    def __subclasscheck__(cls, subclass: type) -> bool:
        msg = f"{cls.__name__} is a namespace, not a type: {cls._hint()}"
        raise TypeError(msg)

    def __call__(cls, *_args: object, **_kwargs: object) -> NoReturn:
        msg = f"{cls.__name__} is a namespace and can't be instantiated: {cls._hint()}"
        raise TypeError(msg)


_Value = TypeVar("_Value", bound=_XdrValue)


def replace(value: _Value, /, **changes: Any) -> _Value:  # noqa: ANN401 - any field
    """Return a copy of a struct or union arm with some fields replaced.

    The same as `copy.replace`, which needs Python 3.13. The new value is checked like
    any other constructed value.

    Raises:
        TypeError: A field doesn't exist, or a new value has the wrong type.
        ValueError: A new value is out of range.
    """
    return value.__replace__(**changes)


class _Decodable(Protocol[_T_co]):
    def _decode(self, reader: Reader, /) -> _T_co: ...


def decode_stream(
    type_: _Decodable[_T], data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> Iterator[_T]:
    """Decode values of one type written back to back, with nothing between them.

    The data has no count in front and no length before each value, so each value ends
    where decoding it ends. The custom sections of a Soroban contract's Wasm file, such
    as its metadata (SEP-46) and its interface spec (SEP-48), are stored this way. Files
    that put a length before each value, such as those in history archives, are not.

    Args:
        type_: A struct, an enum, or a union such as `SCSpecEntry`.
        data: The encoded values, back to back.
        max_depth: The deepest nesting of recursive types to accept, for each value.

    Raises:
        TypeError: The data is not bytes.
        XdrDecodeError: While iterating, when the data is not a valid encoding of a
            sequence of values.
        XdrDepthError: While iterating, when a value is nested more deeply than
            `max_depth`.
    """
    # Checked here rather than in the generator below, so that the error comes from
    # the call.
    if not isinstance(data, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"expected bytes, got {type(data).__name__}"
        raise TypeError(msg)
    return _decode_values(type_._decode, Reader(bytes(data), max_depth))  # noqa: SLF001


def _decode_values(decode: Callable[[Reader], _T], reader: Reader) -> Iterator[_T]:
    while reader.pos < len(reader.data):
        reader.depth = 0
        yield decode_from(decode, reader)


def encode_stream(
    values: Iterable[_Encodable], *, max_depth: int = DEFAULT_MAX_DEPTH
) -> bytes:
    """Encode values back to back, with nothing between them.

    This is the format that `decode_stream` reads.

    Args:
        values: The values to encode.
        max_depth: The deepest nesting of recursive types to encode, for each value.

    Raises:
        TypeError: A value is not a struct, enum or union arm.
        XdrDepthError: A value is nested more deeply than `max_depth`.
    """
    writer = Writer(max_depth)
    for value in values:
        if not isinstance(value, _Encodable):  # pyright: ignore[reportUnnecessaryIsInstance]
            # A typedef's value, such as an int for Uint32, has no codec of its own.
            msg = (
                f"expected a struct, enum or union arm, got {type(value).__name__}; "
                "encode typedef values with their codec in stellar_xdr.typedefs"
            )
            raise TypeError(msg)
        writer.depth = 0
        encode_into(value, writer)
    return bytes(writer.buffer)


__all__ = [
    "UnionNamespace",
    "XdrArm",
    "XdrEnum",
    "XdrStruct",
    "decode_stream",
    "encode_stream",
    "replace",
]
