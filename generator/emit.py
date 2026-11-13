"""Emit the definitions of a module: structs, unions, enums, typedefs and constants.

Code is built as plain strings. What differs from one type reference to another comes
from `typecode.py`; here is what a whole class looks like.
"""

import itertools
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from . import names, sep51
from .model import (
    Array,
    Const,
    Enum,
    GenerationError,
    Primitive,
    Ref,
    Struct,
    Typedef,
    TypeRef,
    Union,
    VarArray,
)
from .text import docstring, indent, source_block, tuple_display
from .typecode import TYPEDEF_NEW, Context, TypeCode, sets_name, typedef_base

_ANNOTATION_BUILTINS: Final = frozenset({"bool", "bytes", "int", "str", "tuple"})

# The methods every value has; a field of the same name would hide one.
_RESERVED_FIELDS: Final = frozenset(
    {
        "to_xdr_bytes",
        "to_xdr_base64",
        "to_json_value",
        "from_xdr_bytes",
        "from_xdr_base64",
        "from_json_value",
    }
)


def _check_unique(owner: str, what: str, values: list[str]) -> None:
    if len(set(values)) != len(values):
        msg = f"{owner}: duplicate {what} in {values}"
        raise GenerationError(msg)


@dataclass(frozen=True)
class _Conversion:
    """The body of a `_to_json` or `_from_json` method: statements, then a result."""

    statements: list[str]
    result: str

    def lines(self, *, counted: bool) -> list[str]:
        """The body, with one level of depth counted around it when asked."""
        if not counted:
            return [*self.statements, f"return {self.result}"]
        return [
            "ctx.enter()",
            *self.statements,
            f"result = {self.result}",
            "ctx.depth -= 1",
            "return result",
        ]


def _arms_name(union: Union) -> str:
    return f"_{names.snake(union.name).upper()}_ARMS"


def _json_arms_name(union: Union) -> str:
    return f"_{names.snake(union.name).upper()}_JSON_ARMS"


def _json_void_name(union: Union) -> str:
    return f"_{names.snake(union.name).upper()}_JSON_VOID"


@dataclass(frozen=True)
class _UnionHead:
    """What the arms of a union share.

    `discriminant` is the class attribute that holds the discriminant, and `write` the
    method of the writer that writes it.
    """

    d: Union
    name: str
    discriminant: str
    switch: Enum | Primitive
    write: str
    counted: bool


@dataclass(frozen=True)
class _ArmParts:
    """What the class of an arm has that the class of a struct doesn't.

    `class_var` is the discriminant as a class attribute, and `write` the statement
    that writes it before the arm's value.
    """

    class_var: str
    write: str


class Emitter:
    """Emits the definitions of one module."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.model = ctx.model
        self.rules = ctx.rules
        self.code = TypeCode(ctx)

    # Structs and arms --------------------------------------------------------------

    def _value_class(  # noqa: PLR0913 - the parts of a class, each given once
        self,
        qualname: str,
        doc: list[str],
        fields: list[tuple[str, TypeRef]],
        to_json: _Conversion,
        from_json: _Conversion | None,
        *,
        counted: bool,
        arm: _ArmParts | None = None,
    ) -> list[str]:
        """The class of a struct, or of an arm when `arm` is given.

        `from_json` is None when the class isn't read from JSON by itself.
        """
        code = self.code
        python_name = qualname.rpartition(".")[2]
        base = "XdrStruct" if arm is None else "XdrArm"
        class_vars = [] if arm is None else [arm.class_var]
        # A union finds the arm and then has it read the value it holds.
        reads = "" if arm is None else "_payload"
        # The depth of a counted type is counted once: when reading by the union's
        # _decode and _from_json, when writing by each arm's _encode and _to_json.
        count_encode = counted
        count_decode = counted and arm is None
        slots = [n for n, _ in fields]
        # A field named like a builtin (SCVal.String.str, SCVal.Bytes.bytes) hides it
        # from the annotations in the class, so those refer to the builtin by module.
        shadowed = {n for n in slots if n in _ANNOTATION_BUILTINS}

        def unshadow(annotation: str) -> str:
            for n in shadowed:
                annotation = re.sub(rf"(?<![\w.]){n}\b", f"builtins.{n}", annotation)
            return annotation

        body = [*docstring(doc), ""]
        body.append(f"__slots__ = {tuple_display([repr(s) for s in slots])}")
        if fields or class_vars:
            body.append("")
        body += [f"{n}: {unshadow(code.annotation(t))}" for n, t in fields]
        body += class_vars
        if fields:
            params = ", ".join(f"{n}: {unshadow(code.parameter(t))}" for n, t in fields)
            body += ["", f"def __init__(self, {params}) -> None:"]
            body += indent(
                [
                    f"set_field(self, {n!r}, "
                    f"{code.check_call(t, n, f'{qualname}.{n}')})"
                    for n, t in fields
                ]
            )
        # Equality and hashing are generated per class, unlike the rest of the shared
        # behaviour in the runtime's base classes: a generic version that loops over the
        # fields made `==` on a whole envelope about 3 times slower on CPython and 10
        # times on PyPy. The class is part of the hash so that arms without fields,
        # such as SCVal.Void and Memo.None_, don't all hash alike.
        compare = " and ".join(f"self.{n} == other.{n}" for n in slots) or "True"
        hashed = tuple_display([qualname, *(f"self.{n}" for n in slots)])
        body += [
            "",
            "def __eq__(self, other: object) -> bool:",
            f"    if type(other) is not {qualname}:",
            "        return NotImplemented",
            f"    return {compare}",
            "",
            "def __hash__(self) -> int:",
            f"    return hash({hashed})",
        ]
        encode = [] if arm is None else [arm.write]
        for n, t in fields:
            encode += code.encode(t, f"self.{n}", f"{n.rstrip('_')}_item")
        if count_encode:
            encode = ["writer.enter()", *encode, "writer.depth -= 1"]
        body += [
            "",
            "def _encode(self, writer: Writer) -> None:",
            *indent(encode or ["pass"]),
        ]
        if fields or count_decode:
            decode = ["obj = new(cls)"]
            decode += [f"set_field(obj, {n!r}, {code.decode(t)})" for n, t in fields]
            if count_decode:
                decode = ["reader.enter()", *decode, "reader.depth -= 1"]
            decode.append("return obj")
        else:
            decode = ["return new(cls)"]
        body += [
            "",
            "@classmethod",
            f"def _decode{reads}(cls, reader: Reader) -> Self:",
            *indent(decode),
        ]
        body += [
            "",
            "def _to_json(self, ctx: JsonWriter) -> Any:",
            *indent(to_json.lines(counted=count_encode)),
        ]
        if from_json is not None:
            body += [
                "",
                "@classmethod",
                f"def _from_json{reads}(cls, value: object, ctx: JsonReader) -> Self:",
                *indent(from_json.lines(counted=count_decode)),
            ]
        return ["@final", f"class {python_name}({base}):", *indent(body)]

    def _struct_json(
        self, d: Struct, qualname: str, fields: list[tuple[str, TypeRef]]
    ) -> tuple[_Conversion, _Conversion]:
        code = self.code
        _check_unique(
            d.name, "JSON keys", [names.json_field_name(f.name) for f in d.fields]
        )
        rule = self.rules.structs.get(d.name)
        if rule is not None:
            # sep51.check has compared the rule's fields with the struct's, types too.
            ordered = [names.field_name(f) for f in rule.fields]
            args = ", ".join(f"self.{n}" for n in ordered)
            types = dict(fields)
            build = [
                f"parts = xdr_json.{rule.read}(value, {qualname!r})",
                "obj = new(cls)",
                *(
                    f"set_field(obj, {n!r}, {code.wrap(types[n], f'parts[{i}]')})"
                    for i, n in enumerate(ordered)
                ),
            ]
            return (
                _Conversion([], f"xdr_json.{rule.write}({args})"),
                _Conversion(build, "obj"),
            )
        items = ", ".join(
            f"{names.json_field_name(x)!r}: {code.to_json(t, f'self.{n}')}"
            for (n, t), x in zip(fields, [f.name for f in d.fields], strict=True)
        )
        keys = tuple_display([repr(names.json_field_name(f.name)) for f in d.fields])
        # An optional field that is left out reads as null, as in the reference.
        optional = [
            names.json_field_name(f.name) for f in d.fields if code.is_optional(f.type)
        ]
        args = f"{qualname!r}, {keys}"
        if optional:
            args += f", frozenset({{{', '.join(repr(k) for k in optional)}}})"
        if fields:
            build = [f"fields = xdr_json.read_fields(value, {args})"]
        else:
            build = [f"xdr_json.read_fields(value, {args})"]
        build.append("obj = new(cls)")
        for (n, t), f in zip(fields, d.fields, strict=True):
            key = names.json_field_name(f.name)
            got = f"fields.get({key!r})" if key in optional else f"fields[{key!r}]"
            read = code.from_json(t, got, f"{qualname}.{n}")
            build.append(f"set_field(obj, {n!r}, {read})")
        return _Conversion([], f"{{{items}}}"), _Conversion(build, "obj")

    def struct(self, d: Struct) -> list[str]:
        """A struct class."""
        name = names.type_name(d.name)
        fields = [(names.field_name(f.name), f.type) for f in d.fields]
        self._check_fields(d.name, [n for n, _ in fields])
        # A struct declared inside another type has no name in the `.x` files: the
        # docstring, like every message, has the name of the class.
        doc = [f"XDR struct ``{name}``.", *source_block(d.source)]
        counted = d.name in self.ctx.counted
        to_json, from_json = self._struct_json(d, name, fields)
        return self._value_class(name, doc, fields, to_json, from_json, counted=counted)

    def _check_fields(self, owner: str, fields: list[str]) -> None:
        if len(set(fields)) != len(fields):
            msg = f"{owner}: duplicate field names {fields}"
            raise GenerationError(msg)
        for name in fields:
            if (
                not name.isidentifier()
                or name.startswith("_")
                or name in _RESERVED_FIELDS
            ):
                msg = f"{owner}: {name!r} can't be a field name"
                raise GenerationError(msg)

    # Unions -----------------------------------------------------------------------

    def union(self, d: Union) -> list[str]:
        """A union namespace with one class per case."""
        name = names.type_name(d.name)
        switch = self.model.switch(d)
        discriminant = names.discriminant_name(d.discriminant_name)
        write = "uint32" if switch == Primitive("unsigned_int") else "int32"
        counted = d.name in self.ctx.counted
        body = [*docstring([f"XDR union ``{name}``.", *source_block(d.source)])]
        head = _UnionHead(d, name, discriminant, switch, write, counted)
        cases = names.union_cases(self.model, d)
        for case in cases:
            body += ["", *self._arm(head, case)]
        _check_unique(d.name, "JSON keys", [c.json_key for c in cases])
        arm_names = [c.class_name for c in cases]
        if len(set(arm_names)) != len(arm_names):
            msg = f"{d.name}: several cases have the same arm name: {arm_names}"
            raise GenerationError(msg)
        if not all(n.isidentifier() and not n.startswith("_") for n in arm_names):
            msg = f"{d.name}: invalid arm names {arm_names}"
            raise GenerationError(msg)
        reserved = {
            "Any",
            "from_xdr_bytes",
            "from_xdr_base64",
            "from_json_value",
            "_decode",
            "_from_json",
        }
        clash = reserved.intersection(arm_names)
        if clash:
            msg = f"{d.name}: arm names {clash} are reserved"
            raise GenerationError(msg)
        members = " | ".join(arm_names)
        decode = [
            f"discriminant = reader.{write}()",
            f"arm = {_arms_name(d)}.get(discriminant)",
            "if arm is None:",
            f"    reader.unknown({name!r}, discriminant)",
        ]
        if counted:
            decode += [
                "reader.enter()",
                "value = arm._decode_payload(reader)",
                "reader.depth -= 1",
                "return value",
            ]
        else:
            decode += ["return arm._decode_payload(reader)"]
        body += [
            "",
            f"Any: TypeAlias = {members}",
            "",
            "@staticmethod",
            f"def _decode(reader: Reader) -> {name}.Any:",
            *indent(decode),
            "",
            "@staticmethod",
            "def from_xdr_bytes(",
            "    data: bytes, *, max_depth: int = DEFAULT_MAX_DEPTH",
            f") -> {name}.Any:",
            *indent(docstring(_DECODE_BYTES_DOC)),
            f"    return decode_bytes({name}._decode, data, max_depth)",
            "",
            "@staticmethod",
            "def from_xdr_base64(",
            "    text: str | bytes, *, max_depth: int = DEFAULT_MAX_DEPTH",
            f") -> {name}.Any:",
            *indent(docstring(_DECODE_BASE64_DOC)),
            f"    return decode_bytes({name}._decode, decode_base64(text), max_depth)",
            "",
            "@staticmethod",
            f"def _from_json(value: object, ctx: JsonReader) -> {name}.Any:",
            *indent(self._union_from_json(d, name, counted)),
            "",
            "@staticmethod",
            "def from_json_value(",
            "    value: object, *, max_depth: int = DEFAULT_MAX_DEPTH",
            f") -> {name}.Any:",
            *indent(docstring(_FROM_JSON_DOC)),
            f"    return decode_json({name}._from_json, value, max_depth)",
        ]
        arms = ", ".join(f"{c.value}: {name}.{c.class_name}" for c in cases)
        tail = [
            "",
            "",
            f"{_arms_name(d)}: Final[dict[int, type[{name}.Any]]] = {{{arms}}}",
            f"{sets_name(d)}: Final = frozenset({_arms_name(d)}.values())",
        ]
        if not self.rules.is_bare(d.name):
            keys = [f"{c.json_key!r}: {name}.{c.class_name}" for c in cases]
            void = [repr(c.json_key) for c in cases if c.arm.type is None]
            arms_table = f"dict[str, type[{name}.Any]]"
            void_set = f"frozenset({{{', '.join(void)}}})" if void else "frozenset()"
            tail += [
                f"{_json_arms_name(d)}: Final[{arms_table}] = {{{', '.join(keys)}}}",
                f"{_json_void_name(d)}: Final[frozenset[str]] = {void_set}",
            ]
        return [f"class {name}(metaclass=UnionNamespace):", *indent(body), *tail]

    def _union_from_json(self, d: Union, name: str, counted: bool) -> list[str]:  # noqa: FBT001
        if d.name in self.rules.length_unions:
            return self._length_union_from_json(d, name)
        if d.name in self.rules.strkey_unions:
            lines = [f"key = xdr_json.read_strkey(value, {name!r})"]
            # mypy gives a variable one type, so each branch has its own variables.
            counter = itertools.count()
            for rule in self.rules.strkey_unions[d.name]:
                built: list[str] = []
                part = self._build(rule.payload, built, counter)
                arm_var = f"arm{next(counter)}"
                arm_name, field_name, held = self._arm_of(d, rule.case)
                held_value = self.code.wrap(held, part)
                lines += [
                    f"if isinstance(key, strkey.{rule.strkey}):",
                    *indent(built),
                    f"    {arm_var} = new({name}.{arm_name})",
                    f"    set_field({arm_var}, {field_name!r}, {held_value})",
                    f"    return {arm_var}",
                ]
            return [*lines, f"xdr_json.wrong_strkey({name!r}, key)"]
        tables = f"{_json_arms_name(d)}, {_json_void_name(d)}"
        read = [f"arm, payload = xdr_json.read_union(value, {name!r}, {tables})"]
        if counted:
            return [
                "ctx.enter()",
                *read,
                "result = arm._from_json_payload(payload, ctx)",
                "ctx.depth -= 1",
                "return result",
            ]
        return [*read, "return arm._from_json_payload(payload, ctx)"]

    def _arm_of(self, d: Union, case: str) -> tuple[str, str, TypeRef]:
        """The class of the arm of a case, the field that holds its value, its type."""
        # The rules were checked against the definitions: the case exists.
        found = next(c for c in names.union_cases(self.model, d) if c.xdr_name == case)
        arm = found.arm
        assert arm.name is not None  # noqa: S101 - _check_cases found a value
        assert arm.type is not None  # noqa: S101 - as above
        return found.class_name, names.field_name(arm.name), arm.type

    def _length_union_from_json(self, d: Union, name: str) -> list[str]:
        """Read a union whose arms are told apart by the length of their string."""
        (short_case, short), (long_case, long) = self.rules.length_unions[d.name]
        short_arm, short_field, short_type = self._arm_of(d, short_case)
        long_arm, long_field, long_type = self._arm_of(d, long_case)
        short_code = self.code.wrap(short_type, f'code.ljust({short}, b"\\0")')
        long_code = self.code.wrap(long_type, f'code.ljust({long}, b"\\0")')
        return [
            f"code = xdr_json.read_asset_code(value, {name!r})",
            f"if len(code) <= {short}:",
            f"    short = new({name}.{short_arm})",
            f'    set_field(short, "{short_field}", {short_code})',
            "    return short",
            f"long = new({name}.{long_arm})",
            f'set_field(long, "{long_field}", {long_code})',
            "return long",
        ]

    def _build(
        self, payload: sep51.Payload, lines: list[str], counter: Iterator[int]
    ) -> str:
        """Build the payload of a strkey's arm; return the expression that holds it."""
        if isinstance(payload, str):
            return f"key.{payload}"
        # Each field: its Python name, the type it holds and what it is built from.
        fields: list[tuple[str, TypeRef, sep51.Payload]]
        if isinstance(payload, sep51.BuiltStruct):
            struct = sep51.defined(self.model, payload.struct, Struct)
            target = self.ctx.use(struct.name)
            types = {f.name: f.type for f in struct.fields}
            fields = [
                (names.field_name(f), types[f], p) for f, p in payload.fields.items()
            ]
        else:
            union = sep51.defined(self.model, payload.union, Union)
            arm_name, field_name, held = self._arm_of(union, payload.case)
            target = f"{self.ctx.use(union.name)}.{arm_name}"
            fields = [(field_name, held, payload.payload)]
        values = {
            f: self.code.wrap(t, self._build(p, lines, counter)) for f, t, p in fields
        }
        var = f"part{next(counter)}"
        lines.append(f"{var} = new({target})")
        lines += [f"set_field({var}, {f!r}, {v})" for f, v in values.items()]
        return var

    def _arm(self, union: _UnionHead, case: names.UnionCase) -> list[str]:
        d, arm, value = union.d, case.arm, case.value
        discriminant = union.discriminant
        fields: list[tuple[str, TypeRef]] = []
        if arm.type is not None:
            assert arm.name is not None  # noqa: S101 - checked by the loader
            fields.append((names.field_name(arm.name), arm.type))
        if any(n == discriminant for n, _ in fields):
            msg = f"{d.name}: arm field {discriminant} hides the discriminant"
            raise GenerationError(msg)
        if isinstance(union.switch, Enum):
            enum = self.ctx.use(union.switch.name)
            label = f"{enum}.{case.xdr_name}"
            class_var = f"{discriminant}: ClassVar[Literal[{label}]] = {label}"
            doc = [f"Arm ``{case.xdr_name}`` of ``{union.name}``."]
        else:
            class_var = f"{discriminant}: ClassVar[Literal[{value}]] = {value}"
            doc = [f"Arm ``case {value}`` of ``{union.name}``."]
        if arm.type is not None:
            doc[0] = doc[0].removesuffix(".") + f", holding ``{arm.name}``."
        qualname = f"{union.name}.{case.class_name}"
        key = case.json_key
        bare = self.rules.is_bare(d.name)
        if bare:
            # Written as the bare payload, which is a string.
            assert fields  # noqa: S101 - _check_cases found a value in every arm
            ((n, t),) = fields
            rule = self.rules.strkey_arm(d.name, case.xdr_name)
            converted = (
                f"xdr_json.{rule.write}(self.{n})"
                if rule is not None and rule.write is not None
                else self.code.to_json(t, f"self.{n}")
            )
            to_json = _Conversion([], converted)
        elif fields:
            ((n, t),) = fields
            to_json = _Conversion(
                [], f"{{{key!r}: {self.code.to_json(t, f'self.{n}')}}}"
            )
        else:
            to_json = _Conversion([], repr(key))
        from_json: _Conversion | None
        if bare:
            from_json = None  # the union reads the string and builds the arm
        elif fields:
            ((n, t),) = fields
            read = self.code.from_json(t, "value", f"{qualname}.{n}")
            from_json = _Conversion(
                ["obj = new(cls)", f"set_field(obj, {n!r}, {read})"], "obj"
            )
        else:
            from_json = _Conversion([], "new(cls)")
        parts = _ArmParts(class_var, f"writer.{union.write}({value})")
        return self._value_class(
            qualname, doc, fields, to_json, from_json, counted=union.counted, arm=parts
        )

    # Enums, typedefs and consts ---------------------------------------------------

    def enum(self, d: Enum) -> list[str]:
        """An enum class, and the tables of its SEP-51 names."""
        name = names.type_name(d.name)
        table = f"_{names.snake(d.name).upper()}_JSON"
        _check_unique(
            d.name, "JSON names", [names.json_member_name(m.name, d) for m in d.members]
        )
        body = [*docstring([f"XDR enum ``{d.name}``.", *source_block(d.source)]), ""]
        body += [f"{m.name} = {m.value}" for m in d.members]
        body += [
            "",
            "def _to_json(self, ctx: JsonWriter) -> str:",
            f"    return {table}_NAMES[self]",
            "",
            "@classmethod",
            f"def _from_json(cls, value: object, ctx: JsonReader) -> {name}:",
            f"    return xdr_json.read_enum(value, {name!r}, {table}_MEMBERS)",
        ]
        names_ = ", ".join(
            f"{name}.{m.name}: {names.json_member_name(m.name, d)!r}" for m in d.members
        )
        return [
            f"class {name}(XdrEnum):",
            *indent(body),
            "",
            "",
            f"{table}_NAMES: Final[dict[{name}, str]] = {{{names_}}}",
            f"{table}_MEMBERS: Final = xdr_json.inverse({table}_NAMES)",
        ]

    def typedef(self, d: Typedef) -> list[str]:
        """A typedef: a class that extends the type of its values, or another name."""
        name = names.type_name(d.name)
        comment = f"  # {' '.join(d.source.split())}"
        kind = typedef_base(self.model, d)
        if kind is None:
            target = self.ctx.model.resolve(d.type)
            if isinstance(target, Struct | Enum | Union):
                # The type itself: a union's namespace, with its arms and its `Any`.
                return [f"{name} = {self.ctx.use(target.name)}{comment}"]
            return [f"{name}: TypeAlias = {self.code.annotation(d.type)}{comment}"]
        code = self.code
        plain = code.plain(d)
        this = Ref(d.name)
        fn, args = code.check(plain)
        checked = f"{fn}({', '.join(['value', 'where', *args])})"
        base = kind
        if isinstance(plain, Array | VarArray):
            base = f"XdrArray[{code.annotation(plain.element)}]"
        new = TYPEDEF_NEW[kind]
        body = [
            *docstring([f"XDR typedef ``{d.name}``.", *source_block(d.source)]),
            "",
            "__slots__ = ()",
            "",
            f"def __new__(cls, value: {code.parameter(this)}) -> Self:",
            f"    return cls._checked(value, {name!r})",
            "",
            "@classmethod",
            "def _checked(cls, value: object, where: str) -> Self:",
            "    if isinstance(value, cls):",
            "        return value",
            f"    return {new}(cls, {checked})",
            "",
            "def _encode(self, writer: Writer) -> None:",
            *indent(code.encode(plain, "self", "item")),
            "",
            "@classmethod",
            "def _decode(cls, reader: Reader) -> Self:",
            f"    return {new}(cls, {code.decode(plain, as_list=True)})",
            "",
            "def _to_json(self, ctx: JsonWriter) -> Any:",
            f"    return {code.to_json(this, 'self')}",
            "",
            "@classmethod",
            "def _from_json(cls, value: object, ctx: JsonReader) -> Self:",
            f"    return {new}(cls, {code.from_json_plain(d, 'value', name, 0)})",
        ]
        return ["@final", f"class {name}({base}):", *indent(body)]

    def const(self, d: Const) -> list[str]:
        """A constant."""
        return [f"{d.name}: Final = {d.value}  # {' '.join(d.source.split())}"]


_DECODE_BYTES_DOC: Final = [
    "Decode a value from XDR.",
    "",
    "Args:",
    "    data: The encoded value, and nothing else.",
    "    max_depth: The deepest nesting of recursive types, such as `SCVal`, to",
    "        accept.",
    "",
    "Raises:",
    "    XdrDecodeError: The data is not a valid encoding of this type.",
    "    XdrDepthError: The data is nested more deeply than `max_depth`.",
]

_FROM_JSON_DOC: Final = [
    "Convert SEP-51 XDR-JSON to a value.",
    "",
    "Args:",
    "    value: A JSON value, as `json.loads` returns it.",
    "    max_depth: The deepest nesting of recursive types, such as `SCVal`, to",
    "        accept.",
    "",
    "Raises:",
    "    XdrJsonError: The JSON is not a valid representation of this type.",
    "    XdrDepthError: The JSON is nested more deeply than `max_depth`.",
]

_DECODE_BASE64_DOC: Final = [
    "Decode a value from XDR in base64.",
    "",
    "Args:",
    "    text: Canonical, padded standard base64 of the encoded value.",
    "    max_depth: The deepest nesting of recursive types, such as `SCVal`, to",
    "        accept.",
    "",
    "Raises:",
    "    XdrDecodeError: The text is not valid base64, or not a valid encoding of",
    "        this type.",
    "    XdrDepthError: The data is nested more deeply than `max_depth`.",
]
