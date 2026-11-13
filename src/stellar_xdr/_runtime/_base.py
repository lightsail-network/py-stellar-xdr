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
from enum import IntEnum
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    NoReturn,
    Protocol,
    Self,
    TypeVar,
    cast,
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
    encode_to,
)
from ._json import JsonReader, JsonWriter, decode_json, encode_json

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)


class XdrValue:
    """A value of any XDR type: a struct, a union arm, an enum member or a typedef's.

    Every generated class extends it through `XdrStruct`, `XdrArm`, `XdrEnum`,
    `XdrBytes`, `XdrInt` or `XdrArray`. These base classes are for annotations and
    `isinstance`, in code that works on values of more than one type. They are not
    for classes of your own: a class that extends one has no encoding.
    """

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
        encode_to(self._encode, writer)
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


class _Decodes:
    """The decoding methods of the types whose class says how to decode them."""

    __slots__ = ()

    @classmethod
    def _decode(cls, reader: Reader) -> Self:
        raise NotImplementedError  # pragma: no cover - every type defines it

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
        raise NotImplementedError  # pragma: no cover - every type defines it

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


def _plain(value: object) -> str:
    """The repr of a value inside another one: a typedef's value without its name.

    A field or an arm already says what the value is, so `Hash(b"...")` is shown as
    `b"..."` there, which is also what the constructor takes.
    """
    if isinstance(value, XdrBytes):
        return bytes.__repr__(value)
    if isinstance(value, XdrInt):
        return int.__repr__(value)
    if isinstance(value, tuple):
        items = [_plain(item) for item in cast("tuple[object, ...]", value)]
        return f"({items[0]},)" if len(items) == 1 else f"({', '.join(items)})"
    return repr(value)


# The classes the generated classes may derive from, once they exist.
_BASES: set[type] = set()


@dataclass_transform(frozen_default=True)
class _Record(XdrValue):
    """Immutability, representation, pickling and copying of structs and union arms."""

    __slots__ = ()

    # The names of the fields, in order: what a `match` pattern takes by position.
    __match_args__: ClassVar[tuple[str, ...]] = ()

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
        # Not `cls.__match_args__ = ...`: mypy refuses to assign to that name on a class
        # that `dataclass_transform` covers.
        type.__setattr__(cls, "__match_args__", tuple(cls.__dict__["__slots__"]))

    def __repr__(self) -> str:
        names = self.__match_args__
        fields = [f"{name}={_plain(getattr(self, name))}" for name in names]
        return f"{type(self).__qualname__}({', '.join(fields)})"

    # Hidden from type checkers: an explicit __setattr__ would make mypy accept any
    # assignment, while dataclass_transform already reports one as an error. The error
    # is the AttributeError that a frozen dataclass raises a subclass of; importing
    # `dataclasses` for that subclass alone would cost every process 3 ms.
    if not TYPE_CHECKING:

        def __setattr__(self, name: str, value: object) -> NoReturn:
            msg = f"can't assign to field {name!r}; use copy.replace or replace"
            raise AttributeError(msg)

        def __delattr__(self, name: str) -> NoReturn:
            msg = f"can't delete field {name!r}"
            raise AttributeError(msg)

    def __reduce__(self) -> tuple[type[Self], tuple[object, ...]]:
        return type(self), tuple(getattr(self, name) for name in self.__match_args__)

    # Values are immutable all the way down, so copies can share them.
    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self

    def __replace__(self, /, **changes: Any) -> Self:  # noqa: ANN401 - any field
        fields = {name: getattr(self, name) for name in self.__match_args__}
        fields.update(changes)
        return type(self)(**fields)


class XdrStruct(_Record, _Decodes):
    """Base class of the generated structs.

    `__match_args__` of a struct's class holds the names of its fields, in order.
    """

    __slots__ = ()

    # Declared here too: left to `dataclass_transform`, type checkers would give this
    # class, which has no fields, an empty tuple.
    __match_args__: ClassVar[tuple[str, ...]] = ()


class XdrArm(_Record):
    """Base class of the generated union arms.

    Arms only encode: decoding starts from the union, such as `SCVal.from_xdr_bytes`,
    because the encoding doesn't say in advance which arm it holds.

    `__match_args__` of an arm's class holds the name of the field with its value, or
    nothing for an arm without one.
    """

    __slots__ = ()

    __match_args__: ClassVar[tuple[str, ...]] = ()  # as for XdrStruct

    # An arm holds one value at most, and its class already says which arm it is, so
    # it is shown the way it is written: `SCVal.U32(5)`, not `SCVal.U32(u32=5)`.
    def __repr__(self) -> str:
        names = self.__match_args__
        values = ", ".join([_plain(getattr(self, name)) for name in names])
        return f"{type(self).__qualname__}({values})"


class XdrEnum(XdrValue, IntEnum):
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


# The classes the generated typedefs may derive from, once they exist.
_TYPEDEF_BASES: set[type] = set()


class _Typedef(XdrValue, _Decodes):
    """What the typedefs share: they are final, and immutable like the type they extend.

    A typedef such as `Hash` or `SCVec` is a class of its own, so that a value knows
    what it is: it encodes itself, and converts to JSON the way its type is written.
    The class extends `bytes`, `int` or `tuple`, so a value can be used as one, and the
    constructors of the other types take the plain value and store the typedef's.
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if _TYPEDEF_BASES and not all(b in _TYPEDEF_BASES for b in cls.__bases__):
            msg = f"{cls.__qualname__}: the generated classes can't be subclassed"
            raise TypeError(msg)
        # Without empty __slots__, a value would get a __dict__ and take attributes.
        if "__slots__" not in cls.__dict__:
            msg = f"{cls.__qualname__} must define __slots__"
            raise TypeError(msg)

    # Values are immutable all the way down, so copies can share them.
    def __copy__(self) -> Self:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        return self


class XdrBytes(_Typedef, bytes):
    """Base class of the typedefs of opaque data and of strings."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({bytes.__repr__(self)})"


class XdrInt(_Typedef, int):
    """Base class of the typedefs of integers, other than `uint32` and its like."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({int.__repr__(self)})"

    # int has no __str__ of its own: str() and format() would use the repr above.
    def __str__(self) -> str:
        return int.__repr__(self)


class XdrArray(_Typedef, tuple[_T_co, ...]):
    """Base class of the typedefs of arrays."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({_plain(tuple(self))})"


_BASES.update({XdrStruct, XdrArm})
_TYPEDEF_BASES.update({XdrBytes, XdrInt, XdrArray})


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


_Value = TypeVar("_Value", bound=XdrStruct | XdrArm)


def replace(value: _Value, /, **changes: Any) -> _Value:  # noqa: ANN401 - any field
    """Return a copy of a struct or union arm with some fields replaced.

    The same as `copy.replace`, which needs Python 3.13. The new value is checked like
    any other constructed value.

    Raises:
        TypeError: The value is not a struct or a union arm, a field doesn't exist, or
            a new value has the wrong type.
        ValueError: A new value is out of range.
    """
    if not isinstance(value, _Record):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"expected a struct or a union arm, got {type(value).__name__}"
        raise TypeError(msg)
    # `__replace__` returns the class of the value. mypy takes it from the two classes
    # that bound `_Value` instead, so it is told.
    return cast("_Value", value.__replace__(**changes))


class _Decodable(Protocol[_T_co]):
    def _decode(self, reader: Reader, /) -> _T_co: ...


def decode_stream(
    type_: _Decodable[_T], /, data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH
) -> Iterator[_T]:
    """Decode values of one type written back to back, with nothing between them.

    The data has no count in front and no length before each value, so each value ends
    where decoding it ends. The custom sections of a Soroban contract's Wasm file, such
    as its metadata (SEP-46) and its interface spec (SEP-48), are stored this way. Files
    that put a length before each value, such as those in history archives, are not.

    Args:
        type_: A struct, an enum, a typedef, or a union such as `SCSpecEntry`.
        data: The encoded values, back to back.
        max_depth: The deepest nesting of recursive types to accept, for each value.

    Raises:
        TypeError: The type can't be decoded, or the data is not bytes.
        XdrDecodeError: While iterating, when the data is not a valid encoding of a
            sequence of values.
        XdrDepthError: While iterating, when a value is nested more deeply than
            `max_depth`.
    """
    # Checked here rather than in the generator below, so that the errors come from
    # the call. An arm such as `SCVal.U32` has no decoder: its union has.
    decode: Callable[[Reader], _T] | None = getattr(type_, "_decode", None)
    if decode is None:
        shown = type_.__qualname__ if isinstance(type_, type) else type(type_).__name__
        msg = f"expected a struct, an enum, a union or a typedef, got {shown}"
        raise TypeError(msg)
    if not isinstance(data, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"expected bytes, got {type(data).__name__}"
        raise TypeError(msg)
    return _decode_values(decode, Reader(bytes(data), max_depth))


def _decode_values(decode: Callable[[Reader], _T], reader: Reader) -> Iterator[_T]:
    while reader.pos < len(reader.data):
        reader.depth = 0
        yield decode_from(decode, reader)


def encode_stream(
    values: Iterable[XdrValue], *, max_depth: int = DEFAULT_MAX_DEPTH
) -> bytes:
    """Encode values back to back, with nothing between them.

    This is the format that `decode_stream` reads.

    Args:
        values: The values to encode.
        max_depth: The deepest nesting of recursive types to encode, for each value.

    Raises:
        TypeError: A value is not of an XDR type. A plain `int` or `bytes` is not:
            wrap it in its type, such as `Hash`, which says how it is encoded.
        XdrDepthError: A value is nested more deeply than `max_depth`.
    """
    writer = Writer(max_depth)
    for value in values:
        if not isinstance(value, XdrValue):  # pyright: ignore[reportUnnecessaryIsInstance]
            msg = f"expected a value of an XDR type, got {type(value).__name__}"
            raise TypeError(msg)
        writer.depth = 0
        encode_to(value._encode, writer)  # noqa: SLF001
    return bytes(writer.buffer)


__all__ = [
    "UnionNamespace",
    "XdrArm",
    "XdrArray",
    "XdrBytes",
    "XdrEnum",
    "XdrInt",
    "XdrStruct",
    "XdrValue",
    "decode_stream",
    "encode_stream",
    "replace",
]
