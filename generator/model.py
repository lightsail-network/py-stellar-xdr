"""Load `xdr.json` into a typed model, rejecting anything the generator doesn't handle.

The format is documented only by the upstream tool that writes it, so the loader checks
every shape it relies on and fails on anything else: a format change then stops the
generator instead of producing wrong code.
"""

import json
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# --- Type references -----------------------------------------------------------------

PrimitiveKind = Literal["bool", "int", "unsigned_int", "hyper", "unsigned_hyper"]


@dataclass(frozen=True)
class Primitive:
    """A built-in XDR type."""

    kind: PrimitiveKind


@dataclass(frozen=True)
class Ref:
    """A reference to a named definition."""

    name: str


@dataclass(frozen=True)
class OpaqueFixed:
    """`opaque[size]`."""

    size: int


@dataclass(frozen=True)
class OpaqueVar:
    """`opaque<max_size>`, or `opaque<>` when `max_size` is None."""

    max_size: int | None


@dataclass(frozen=True)
class String:
    """`string<max_size>`, or `string<>` when `max_size` is None."""

    max_size: int | None


@dataclass(frozen=True)
class Array:
    """`element[count]` for a non-opaque element."""

    element: "TypeRef"
    count: int


@dataclass(frozen=True)
class VarArray:
    """`element<max_count>`, or `element<>` when `max_count` is None."""

    element: "TypeRef"
    max_count: int | None


@dataclass(frozen=True)
class Optional:
    """`element*`."""

    element: "TypeRef"


TypeRef = (
    Primitive | Ref | OpaqueFixed | OpaqueVar | String | Array | VarArray | Optional
)

# --- Definitions ---------------------------------------------------------------------


@dataclass(frozen=True)
class Field:
    """A field of a struct."""

    name: str
    type: TypeRef


@dataclass(frozen=True)
class Struct:
    """A struct definition."""

    name: str
    file: str
    source: str
    fields: tuple[Field, ...]


@dataclass(frozen=True)
class Member:
    """A member of an enum."""

    name: str
    value: int


@dataclass(frozen=True)
class Enum:
    """An enum definition."""

    name: str
    file: str
    source: str
    member_prefix: str
    members: tuple[Member, ...]


@dataclass(frozen=True)
class Case:
    """A case label of a union arm: an enum member, or a value for integer switches."""

    value: int
    name: str | None


@dataclass(frozen=True)
class Arm:
    """An arm of a union, which several cases may share; `type` is None for void."""

    cases: tuple[Case, ...]
    name: str | None
    type: TypeRef | None


@dataclass(frozen=True)
class Union:
    """A union definition, switching on an enum or on `int` or `unsigned int`."""

    name: str
    file: str
    source: str
    discriminant_name: str
    discriminant_type: Ref | Primitive
    arms: tuple[Arm, ...]


@dataclass(frozen=True)
class Typedef:
    """A typedef definition."""

    name: str
    file: str
    source: str
    type: TypeRef


@dataclass(frozen=True)
class Const:
    """A const definition."""

    name: str
    file: str
    source: str
    value: int


Definition = Struct | Enum | Union | Typedef | Const


@dataclass(frozen=True)
class Model:
    """Every definition, in the order of the files and of the definitions in them."""

    files: tuple[str, ...]
    definitions: tuple[Definition, ...]
    by_name: dict[str, Definition] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "by_name", {d.name: d for d in self.definitions})

    def get(self, name: str) -> Definition:
        """Look up a definition by name."""
        return self.by_name[name]

    def switch(self, union: "Union") -> "Enum | Primitive":
        """What a union switches on: an enum, or `int` or `unsigned int`.

        `switch (uint32 v)` refers to the `uint32` typedef, which is resolved here.
        """
        t: TypeRef = union.discriminant_type
        while isinstance(t, Ref):
            d = self.get(t.name)
            if isinstance(d, Enum):
                return d
            if not isinstance(d, Typedef):
                msg = f"{union.name}: discriminant {t.name} is not an enum or integer"
                raise InputError(msg)
            t = d.type
        if t not in {Primitive("int"), Primitive("unsigned_int")}:
            msg = f"{union.name}: unsupported discriminant {t}"
            raise InputError(msg)
        return t


# --- Loading ------------------------------------------------------------------------


class InputError(Exception):
    """`xdr.json` has a shape the generator doesn't handle."""


class GenerationError(Exception):
    """The model can't be turned into valid, unambiguous Python."""


def _keys(
    obj: dict[str, Any],
    required: AbstractSet[str],
    optional: AbstractSet[str] = frozenset(),
) -> None:
    keys = set(obj)
    if not required <= keys or not keys <= required | optional:
        msg = f"unexpected keys {sorted(keys)} in {json.dumps(obj)[:200]}"
        raise InputError(msg)


def _size(value: object, what: str, *, optional: bool = False) -> Any:  # noqa: ANN401
    """Check a size, count or value: an int, or None where it may be absent."""
    if value is None and optional:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        msg = f"invalid {what} {value!r}"
        raise InputError(msg)
    return value


def _integer(value: object, what: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"invalid {what} {value!r}"
        raise InputError(msg)
    return value


def _int32(value: object, what: str) -> int:
    value = _integer(value, what)
    if not -(2**31) <= value < 2**31:
        msg = f"{what} {value} is out of range for an XDR int"
        raise InputError(msg)
    return value


def _type(obj: dict[str, Any]) -> TypeRef:
    kind = obj.get("kind")
    if kind in {"bool", "int", "unsigned_int", "hyper", "unsigned_hyper"}:
        _keys(obj, {"kind"})
        return Primitive(kind)
    if kind == "ref":
        _keys(obj, {"kind", "name"})
        return Ref(obj["name"])
    if kind == "opaque_fixed":
        _keys(obj, {"kind", "size"})
        return OpaqueFixed(_size(obj["size"], "opaque size"))
    if kind == "opaque_var":
        _keys(obj, {"kind"}, {"max_size"})
        return OpaqueVar(_size(obj.get("max_size"), "opaque size", optional=True))
    if kind == "string":
        _keys(obj, {"kind"}, {"max_size"})
        return String(_size(obj.get("max_size"), "string size", optional=True))
    if kind == "array":
        _keys(obj, {"kind", "element", "count"})
        return Array(_type(obj["element"]), _size(obj["count"], "array count"))
    if kind == "var_array":
        _keys(obj, {"kind", "element"}, {"max_count"})
        count = _size(obj.get("max_count"), "array count", optional=True)
        return VarArray(_type(obj["element"]), count)
    if kind == "optional":
        _keys(obj, {"kind", "element"})
        return Optional(_type(obj["element"]))
    # float, double and anything new.
    msg = f"unsupported type kind {kind!r}"
    raise InputError(msg)


def _file(obj: dict[str, Any], files: tuple[str, ...]) -> str:
    """The `.x` file of a definition, which also has to have a name and a source."""
    if not {"name", "source", "file_index"} <= obj.keys():
        msg = (
            f"definition without a name, source or file_index: {json.dumps(obj)[:200]}"
        )
        raise InputError(msg)
    index: int = _size(obj["file_index"], "file_index")
    if index >= len(files):
        msg = f"{obj['name']}: file_index {index} is not one of the {len(files)} files"
        raise InputError(msg)
    return files[index]


def _definition(obj: dict[str, Any], files: tuple[str, ...]) -> Definition:
    kind = obj.get("kind")
    # Every kind has these; each kind then checks the keys of its own.
    file = _file(obj, files)
    name: str = obj["name"]
    source: str = obj["source"]
    if kind == "struct":
        _keys(obj, {"kind", "name", "fixed_size", "source", "file_index", "fields"})
        fields: list[Field] = []
        for f in obj["fields"]:
            _keys(f, {"name", "type"})
            fields.append(Field(f["name"], _type(f["type"])))
        return Struct(name, file, source, tuple(fields))
    if kind == "enum":
        _keys(obj, {"kind", "name", "source", "file_index", "member_prefix", "members"})
        members: list[Member] = []
        for m in obj["members"]:
            _keys(m, {"name", "value"})
            members.append(Member(m["name"], _int32(m["value"], "enum value")))
        prefix: str = obj["member_prefix"]
        if not all(m.name.startswith(prefix) for m in members):
            msg = f"{name}: member_prefix {prefix!r} does not prefix every member"
            raise InputError(msg)
        return Enum(name, file, source, prefix, tuple(members))
    if kind == "union":
        _keys(
            obj,
            {
                "kind",
                "name",
                "fixed_size",
                "source",
                "file_index",
                "discriminant",
                "arms",
            },
        )
        _keys(obj["discriminant"], {"name", "type"})
        discriminant = _type(obj["discriminant"]["type"])
        if not (
            isinstance(discriminant, Ref)
            or discriminant in {Primitive("int"), Primitive("unsigned_int")}
        ):
            msg = f"{name}: unsupported discriminant {discriminant}"
            raise InputError(msg)
        arms: list[Arm] = []
        for a in obj["arms"]:
            # A default arm would carry other keys and is rejected here.
            _keys(a, {"cases", "name"}, {"type"})
            cases: list[Case] = []
            for c in a["cases"]:
                _keys(c, {"value"}, {"name"})
                cases.append(Case(_int32(c["value"], "case value"), c.get("name")))
            if (a["name"] is None) != ("type" not in a):
                msg = f"{name}: an arm has a name without a type or the reverse"
                raise InputError(msg)
            arm_type = _type(a["type"]) if "type" in a else None
            arms.append(Arm(tuple(cases), a["name"], arm_type))
        return Union(
            name, file, source, obj["discriminant"]["name"], discriminant, tuple(arms)
        )
    if kind == "typedef":
        _keys(obj, {"kind", "name", "source", "file_index", "type"})
        return Typedef(name, file, source, _type(obj["type"]))
    if kind == "const":
        _keys(obj, {"kind", "name", "value", "source", "file_index"})
        return Const(name, file, source, _integer(obj["value"], "const value"))
    msg = f"unsupported definition kind {kind!r}"
    raise InputError(msg)


def _walk(t: TypeRef) -> list[TypeRef]:
    if isinstance(t, Array | VarArray | Optional):
        return [t, *_walk(t.element)]
    return [t]


def _validate(model: Model) -> None:
    names: set[str] = set()
    for d in model.definitions:
        if d.name in names:
            msg = f"duplicate definition {d.name}"
            raise InputError(msg)
        names.add(d.name)
    index = model.by_name

    def refs(d: Definition) -> list[TypeRef]:
        if isinstance(d, Struct):
            return [t for f in d.fields for t in _walk(f.type)]
        if isinstance(d, Union):
            arms = [t for a in d.arms if a.type is not None for t in _walk(a.type)]
            return [d.discriminant_type, *arms]
        if isinstance(d, Typedef):
            return _walk(d.type)
        return []

    for d in model.definitions:
        for t in refs(d):
            if isinstance(t, Ref) and t.name not in index:
                msg = f"{d.name}: unresolved reference {t.name}"
                raise InputError(msg)
        if isinstance(d, Union):
            values = [c.value for a in d.arms for c in a.cases]
            if len(values) != len(set(values)):
                msg = f"{d.name}: duplicate case values"
                raise InputError(msg)
            switch = model.switch(d)
            if isinstance(switch, Enum):
                enum = switch
                members = {m.name: m.value for m in enum.members}
                for a in d.arms:
                    for c in a.cases:
                        if c.name is None or members.get(c.name) != c.value:
                            msg = f"{d.name}: case {c} is not a member of {enum.name}"
                            raise InputError(msg)
            elif any(c.name is not None for a in d.arms for c in a.cases):
                msg = f"{d.name}: named case in an integer switch"
                raise InputError(msg)


def load(path: Path) -> Model:
    """Load and validate `xdr.json`."""
    document = json.loads(path.read_bytes())
    _keys(document, {"version", "files", "resolved_features", "definitions"})
    if document["version"] != 1:
        msg = f"unsupported xdr.json version {document['version']!r}"
        raise InputError(msg)
    # Resolved #ifdef features would change the set of types, and are never wanted
    # for the network's types.
    if document["resolved_features"] != []:
        msg = f"unexpected resolved_features {document['resolved_features']!r}"
        raise InputError(msg)
    files = tuple(f["name"] for f in document["files"])
    definitions = tuple(_definition(d, files) for d in document["definitions"])
    model = Model(files, definitions)
    _validate(model)
    return model
