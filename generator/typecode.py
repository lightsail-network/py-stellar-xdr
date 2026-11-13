"""The code the generated modules use for a type, wherever the type is referred to.

Every expression the generated code evaluates for a type comes from one of the
`TypeCode` methods, so the annotation, the constructor check, the decoder and the
encoder of a type can't drift apart.
"""

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Final

from . import names, sep51
from .analysis import Sizes
from .model import (
    Array,
    Const,
    Enum,
    GenerationError,
    Model,
    OpaqueFixed,
    OpaqueVar,
    Optional,
    Primitive,
    Ref,
    String,
    Struct,
    Typedef,
    TypeRef,
    Union,
    VarArray,
)
from .text import indent

_PRIMITIVE_ANNOTATION: Final = {
    "bool": "bool",
    "int": "int",
    "unsigned_int": "int",
    "hyper": "int",
    "unsigned_hyper": "int",
}

# The name a primitive has in the runtime: `reader`, `writer` and `check` each have a
# function of this name for it, and `xdr_json` has `read_` followed by this name.
_PRIMITIVE_NAME: Final = {
    "bool": "boolean",
    "int": "int32",
    "unsigned_int": "uint32",
    "hyper": "int64",
    "unsigned_hyper": "uint64",
}

# The function that makes a plain value a value of a typedef, by the typedef's base.
TYPEDEF_NEW: Final = {
    "XdrBytes": "new_bytes",
    "XdrInt": "new_int",
    "XdrArray": "new_tuple",
}


# The typedefs that give an XDR integer its width, which nearly every integer field
# refers to. A class of their own would make every such field hold an object instead
# of a plain int, so their values are plain ints. Every other integer typedef, such as
# SequenceNumber, is a class, however upstream writes it: `typedef int64` and
# `typedef hyper` give the same.
PLAIN_INTEGERS: Final = frozenset({"uint32", "int32", "uint64", "int64"})


def typedef_base(model: Model, d: Typedef) -> str | None:
    """The base class of a typedef that is a class of its own, or None.

    A typedef is a class that extends the Python type of its values: `bytes` for
    opaque data and strings, `int` for integers, `tuple` for arrays. The rest are
    not classes:

    - a typedef of a struct, an enum or a union is that type itself;
    - a typedef of an optional value is another name for it, `X | None`, since `None`
      can't be an instance of a class of its own. Like the type it names, it can't
      be called, and `isinstance` checks it correctly;
    - the typedefs in `PLAIN_INTEGERS`, and a typedef of `bool`, which can't be
      extended, are type aliases (`TypeAliasType`): names for annotations, which
      can't be called or used with `isinstance`. Another name for `int` could be
      called, and would convert where it should check: `1.9` would become `1`.
    """
    if d.name in PLAIN_INTEGERS:
        return None
    t: TypeRef = d.type
    while isinstance(t, Ref):
        target = model.get(t.name)
        if not isinstance(target, Typedef):
            return None
        t = target.type
    if isinstance(t, Primitive):
        return None if t.kind == "bool" else "XdrInt"
    if isinstance(t, OpaqueFixed | OpaqueVar | String):
        return "XdrBytes"
    if isinstance(t, Array | VarArray):
        return "XdrArray"
    return None


def sets_name(union: Union) -> str:
    """The name of the set of a union's arm classes, which the check of a value uses."""
    return f"_{names.snake(union.name).upper()}_CLASSES"


@dataclass(frozen=True)
class Context:
    """What the emitter of one module works with.

    The model, the rules and what was worked out of the model are the same for every
    module. `module` is the one being written, and `imports` collects what it turns
    out to need from the others: for each module, the names to import from it.
    """

    model: Model
    rules: sep51.Rules
    module_of: Mapping[str, str]
    counted: AbstractSet[str]
    sizes: Sizes
    module: str
    imports: dict[str, set[str]] = field(default_factory=dict[str, set[str]])

    def use(self, xdr_name: str, python_name: str | None = None) -> str:
        """Refer to a name of a definition, importing it when it's in another module."""
        python_name = python_name or names.type_name(xdr_name)
        module = self.module_of[xdr_name]
        if module != self.module:
            self.imports.setdefault(module, set()).add(python_name)
        return python_name


class TypeCode:
    """The code the generated modules use for one type reference."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx

    # Annotations -------------------------------------------------------------------

    def annotation(self, t: TypeRef) -> str:
        """The type of a stored value."""
        if isinstance(t, Primitive):
            return _PRIMITIVE_ANNOTATION[t.kind]
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            name = self.ctx.use(t.name)
            # A typedef of a union is the union's namespace under another name.
            if isinstance(d, Typedef) and isinstance(
                self.ctx.model.resolve(d.type), Union
            ):
                return f"{name}.Any"
            return f"{name}.Any" if isinstance(d, Union) else name
        if isinstance(t, OpaqueFixed | OpaqueVar | String):
            return "bytes"
        if isinstance(t, Array | VarArray):
            return f"tuple[{self.annotation(t.element)}, ...]"
        return f"{self.annotation(t.element)} | None"

    def typedef_class(self, t: TypeRef) -> tuple[Typedef, str] | None:
        """The typedef a reference names and its base, if the typedef is a class."""
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                base = typedef_base(self.ctx.model, d)
                if base is not None:
                    return d, base
        return None

    def plain(self, d: Typedef) -> TypeRef:
        """What the values of a typedef that is a class are, apart from their class."""
        resolved = self.ctx.model.resolve(d.type)
        assert not isinstance(resolved, Struct | Enum | Union | Typedef | Const)  # noqa: S101
        return resolved

    def wrap(self, t: TypeRef, value: str) -> str:
        """Make a plain value, already checked or decoded, a value of its typedef."""
        found = self.typedef_class(t)
        if found is None:
            return value
        d, base = found
        return f"{TYPEDEF_NEW[base]}({self.ctx.use(d.name)}, {value})"

    def parameter(self, t: TypeRef) -> str:
        """The type a constructor accepts.

        It is the plain value of a typedef, any sequence for an array, and `str` too
        for a string.
        """
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef) and (
                typedef_base(self.ctx.model, d) is not None
                or self._needs_expansion(d.type)
            ):
                return self.parameter(d.type)
            return self.annotation(t)
        if isinstance(t, String):
            return "bytes | str"
        if isinstance(t, Array | VarArray):
            return f"Sequence[{self.parameter(t.element)}]"
        if isinstance(t, Optional):
            return f"{self.parameter(t.element)} | None"
        return self.annotation(t)

    def _needs_expansion(self, t: TypeRef) -> bool:
        if isinstance(t, String | Array | VarArray):
            return True
        if isinstance(t, Optional):
            return self._needs_expansion(t.element)
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            return isinstance(d, Typedef) and self._needs_expansion(d.type)
        return False

    # Constructor checks ------------------------------------------------------------

    def check(self, t: TypeRef) -> tuple[str, list[str]]:
        """The check function for a type and its arguments after (value, where)."""
        if isinstance(t, Primitive):
            return f"check.{_PRIMITIVE_NAME[t.kind]}", []
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                if typedef_base(self.ctx.model, d) is not None:
                    return f"{self.ctx.use(t.name)}._checked", []
                return self.check(d.type)
            name = self.ctx.use(t.name)
            if isinstance(d, Union):
                display = repr(names.type_name(t.name))
                return "check.union", [self.ctx.use(t.name, sets_name(d)), display]
            return "check.instance", [name]
        if isinstance(t, OpaqueFixed):
            return "check.opaque_fixed", [str(t.size)]
        if isinstance(t, OpaqueVar):
            return "check.opaque_var", [str(t.max_size)]
        if isinstance(t, String):
            return "check.string", [str(t.max_size)]
        if isinstance(t, VarArray):
            fn, args = self.check(t.element)
            return "check.array", [str(t.max_count), fn, *args]
        if isinstance(t, Array):
            fn, args = self.check(t.element)
            return "check.array_fixed", [str(t.count), fn, *args]
        fn, args = self.check(t.element)
        return "check.optional", [fn, *args]

    def check_call(self, t: TypeRef, value: str, where: str) -> str:
        """A call that checks and returns the value to store."""
        fn, args = self.check(t)
        return f"{fn}({', '.join([value, repr(where), *args])})"

    # Decoding ----------------------------------------------------------------------

    def decode(self, t: TypeRef, *, as_list: bool = False) -> str:
        """An expression that reads a value from `reader`.

        With `as_list`, an array is read as the list of its items, for a typedef to
        make its own tuple of.
        """
        if isinstance(t, Primitive):
            return f"reader.{_PRIMITIVE_NAME[t.kind]}()"
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                if typedef_base(self.ctx.model, d) is not None:
                    return self.wrap(t, self.decode(self.plain(d), as_list=True))
                return self.decode(d.type)
            return f"{self.ctx.use(t.name)}._decode(reader)"
        if isinstance(t, OpaqueFixed):
            if t.size % 4 == 0:
                return f"reader.opaque_aligned({t.size})"
            return f"reader.opaque_fixed({t.size})"
        if isinstance(t, OpaqueVar | String):
            return f"reader.opaque_var({t.max_size})"
        if isinstance(t, VarArray):
            size = self.ctx.sizes.min_size(t.element)
            if size == 0:
                # The reader bounds a length by what the rest of the input can hold.
                msg = f"an array of {t.element} has elements that encode to no bytes"
                raise GenerationError(msg)
            count = f"reader.count({t.max_count}, {size})"
            items = f"[{self.decode(t.element)} for _ in range({count})]"
            return items if as_list else f"tuple({items})"
        if isinstance(t, Array):
            items = f"[{self.decode(t.element)} for _ in range({t.count})]"
            return items if as_list else f"tuple({items})"
        # The condition is evaluated first, so the flag is read before the value.
        return f"({self.decode(t.element)} if reader.present() else None)"

    # Encoding ----------------------------------------------------------------------

    def encode(self, t: TypeRef, value: str, tag: str, depth: int = 0) -> list[str]:
        """Statements that write `value` to `writer`.

        `tag` makes loop variables unique within a method: mypy gives a variable one
        type, so two loops over different types can't share one.
        """
        if isinstance(t, Primitive):
            return [f"writer.{_PRIMITIVE_NAME[t.kind]}({value})"]
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                return self.encode(d.type, value, tag, depth)
            if isinstance(d, Enum):
                return [f"writer.int32({value})"]
            return [f"{value}._encode(writer)"]
        if isinstance(t, OpaqueFixed):
            return [f"writer.opaque_fixed({value})"]
        if isinstance(t, OpaqueVar | String):
            return [f"writer.opaque_var({value})"]
        item = f"{tag}{depth}"
        body = indent(self.encode(t.element, item, tag, depth + 1))
        if isinstance(t, VarArray):
            return [f"writer.uint32(len({value}))", f"for {item} in {value}:", *body]
        if isinstance(t, Array):
            return [f"for {item} in {value}:", *body]
        return [
            f"if {value} is None:",
            "    writer.uint32(0)",
            "else:",
            "    writer.uint32(1)",
            *indent(self.encode(t.element, value, tag, depth)),
        ]

    # JSON --------------------------------------------------------------------------

    def is_optional(self, t: TypeRef) -> bool:
        """Whether a type is optional, directly or through typedefs."""
        resolved = self.ctx.model.resolve(t)
        return isinstance(resolved, Optional)

    def to_json(self, t: TypeRef, value: str, depth: int = 0) -> str:
        """An expression that converts `value` to SEP-51 JSON."""
        if isinstance(t, Primitive):
            return f"str({value})" if t.kind in {"hyper", "unsigned_hyper"} else value
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                rule = self.ctx.rules.typedefs.get(d.name)
                if rule is not None:
                    return f"xdr_json.{rule.write}({value})"
                converted = self.to_json(d.type, value, depth)
                if converted == value and typedef_base(self.ctx.model, d) == "XdrInt":
                    # Written as it is: as a plain int, not as the typedef's value.
                    return f"int({value})"
                return converted
            return f"{value}._to_json(ctx)"
        if isinstance(t, OpaqueFixed | OpaqueVar):
            return f"{value}.hex()"
        if isinstance(t, String):
            return f"xdr_json.write_string({value})"
        if isinstance(t, Array | VarArray):
            item = f"item{depth}"
            element = self.to_json(t.element, item, depth + 1)
            if element == item:
                return f"list({value})"
            return f"[{element} for {item} in {value}]"
        return f"(None if {value} is None else {self.to_json(t.element, value, depth)})"

    def from_json(self, t: TypeRef, value: str, where: str, depth: int = 0) -> str:
        """An expression that reads `value`, a JSON value, as SEP-51 JSON."""
        if isinstance(t, Primitive):
            return f"xdr_json.read_{_PRIMITIVE_NAME[t.kind]}({value}, {where!r})"
        if isinstance(t, Ref):
            d = self.ctx.model.get(t.name)
            if isinstance(d, Typedef):
                return self.wrap(t, self.from_json_plain(d, value, where, depth))
            return f"{self.ctx.use(t.name)}._from_json({value}, ctx)"
        if isinstance(t, OpaqueFixed):
            return f"xdr_json.read_hex_fixed({value}, {where!r}, {t.size})"
        if isinstance(t, OpaqueVar):
            return f"xdr_json.read_hex_var({value}, {where!r}, {t.max_size})"
        if isinstance(t, String):
            return f"xdr_json.read_string({value}, {where!r}, {t.max_size})"
        item = f"item{depth}"
        element = self.from_json(t.element, item, where, depth + 1)
        # The items are read through a function, so that an error can say which one.
        read = f"lambda {item}: {element}"
        if isinstance(t, VarArray):
            items = f"xdr_json.read_array({value}, {where!r}, {t.max_count})"
            return f"xdr_json.read_items({items}, {where!r}, {read})"
        if isinstance(t, Array):
            items = f"xdr_json.read_array_fixed({value}, {where!r}, {t.count})"
            return f"xdr_json.read_items({items}, {where!r}, {read})"
        inner = self.from_json(t.element, value, where, depth)
        return f"(None if {value} is None else {inner})"

    def from_json_plain(self, d: Typedef, value: str, where: str, depth: int) -> str:
        """An expression that reads the plain value of a typedef from JSON."""
        rule = self.ctx.rules.typedefs.get(d.name)
        if rule is not None:
            return f"xdr_json.{rule.read}({value}, {where!r})"
        found = self.typedef_class(d.type)
        if found is not None:
            # A typedef of a typedef: the value becomes one of the outer type only.
            return self.from_json_plain(found[0], value, where, depth)
        return self.from_json(d.type, value, where, depth)
