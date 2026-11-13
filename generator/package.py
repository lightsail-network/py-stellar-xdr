"""Put the modules of the package together: what each imports, defines and exports."""

import ast
import keyword
from dataclasses import dataclass, field
from typing import Final

from . import names, sep51
from .analysis import Sizes, counted_types, references
from .emit import Emitter
from .model import (
    Const,
    Definition,
    Enum,
    GenerationError,
    Model,
    OpaqueFixed,
    OpaqueVar,
    Primitive,
    String,
    Struct,
    Typedef,
    Union,
)
from .text import HEADER
from .typecode import Context

# Names the package exports besides the definitions; `__init__.py` imports them.
PUBLIC_RUNTIME_NAMES: Final = (
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
    "XdrValue",
    "decode_stream",
    "encode_stream",
    "replace",
)

# Names the generated modules import; no XDR type may use them.
RUNTIME_NAMES: Final = (
    "DEFAULT_MAX_DEPTH",
    "JsonReader",
    "JsonWriter",
    "Reader",
    "TypeAliasType",
    "UnionNamespace",
    "Writer",
    "XdrArm",
    "XdrArray",
    "XdrBytes",
    "XdrEnum",
    "XdrInt",
    "XdrStruct",
    "check",
    "decode_base64",
    "decode_bytes",
    "decode_json",
    "new",
    "new_bytes",
    "new_int",
    "new_tuple",
    "set_field",
    "xdr_json",
)

TYPING_NAMES: Final = (
    "Any",
    "ClassVar",
    "Final",
    "Literal",
    "Self",
    "TypeAlias",
    "final",
)

# The modules of the package that are not generated from a `.x` file.
_HAND_WRITTEN_MODULES: Final = frozenset({"_runtime"})


def _public_name(d: Definition) -> str:
    """The name a definition is exported under: a const keeps its XDR name."""
    return d.name if isinstance(d, Const) else names.type_name(d.name)


@dataclass
class _Module:
    """One module of the package: the definitions of one `.x` file."""

    name: str
    xdr_file: str
    definitions: list[Definition] = field(default_factory=list[Definition])


def _is_simple_typedef(d: Typedef) -> bool:
    # Typedefs that refer to no other definition can come first in a module.
    return isinstance(d.type, Primitive | OpaqueFixed | OpaqueVar | String)


def _names_used(body: str) -> frozenset[str]:
    """The names that the code of a module refers to, which decide its imports.

    The code is parsed rather than searched: its docstrings and comments quote the XDR
    source, where a word such as `Sequence` is not a use of the name.
    """
    return frozenset(
        node.id for node in ast.walk(ast.parse(body)) if isinstance(node, ast.Name)
    )


def _ordered_typedefs(typedefs: list[Typedef]) -> list[Typedef]:
    # An alias is evaluated at import time, so the aliases it refers to come first.
    by_name = {d.name: d for d in typedefs}
    done: dict[str, Typedef] = {}

    def visit(d: Typedef) -> None:
        if d.name in done:
            return
        for ref in references(d):
            if ref in by_name:
                visit(by_name[ref])
        done[d.name] = d

    for d in typedefs:
        visit(d)
    return list(done.values())


def _imports(others: dict[str, set[str]], body: str) -> list[str]:
    """The imports of a module: what its code uses, and what the others define."""
    used = _names_used(body)
    lines: list[str] = []
    if "builtins" in used:
        lines.append("import builtins")
    if "strkey" in used:
        lines.append("import stellar_strkey as strkey")
    if "Sequence" in used:
        lines.append("from collections.abc import Sequence")
    used_typing = sorted(used.intersection(TYPING_NAMES))
    if used_typing:
        lines.append(f"from typing import {', '.join(used_typing)}")
    lines.append("")
    runtime = sorted(used.intersection(RUNTIME_NAMES))
    lines.append(f"from ._runtime import {', '.join(runtime)}")
    for other in sorted(others):
        imported = ", ".join(sorted(others[other]))
        lines.append(f"from .{other} import {imported}")
    return lines


class Generator:
    """Turns a model into the source of every module of the package."""

    def __init__(
        self, model: Model, protocol: int, rules: sep51.Rules = sep51.RULES
    ) -> None:
        self.model = model
        self.rules = rules
        self.protocol = protocol
        self.modules: dict[str, _Module] = {}
        self._module_of: dict[str, str] = {}
        for d in model.definitions:
            name = names.module_name(d.file)
            if name in _HAND_WRITTEN_MODULES:
                msg = f"{d.file}: its module would replace stellar_xdr.{name}"
                raise GenerationError(msg)
            module = self.modules.setdefault(name, _Module(name, d.file))
            module.definitions.append(d)
            self._module_of[d.name] = name
        self._counted = counted_types(model)
        self._sizes = Sizes(model)
        self._check_names()
        sep51.check(model, rules)

    def _check_names(self) -> None:
        # What a generated module or the package's `__init__.py` binds besides the
        # definitions: a definition of the same name would replace it, or be replaced.
        reserved = {
            *RUNTIME_NAMES,
            *PUBLIC_RUNTIME_NAMES,
            *TYPING_NAMES,
            "PROTOCOL_VERSION",
            "Sequence",
            "builtins",
            "cast",
            "strkey",
        }
        seen: dict[str, str] = {}
        for d in self.model.definitions:
            name = _public_name(d)
            if name in reserved or keyword.iskeyword(name):
                msg = f"{d.name}: {name} is reserved"
                raise GenerationError(msg)
            if name in seen:
                msg = f"{d.name} and {seen[name]} are both named {name}"
                raise GenerationError(msg)
            seen[name] = d.name

    def module(self, module: _Module) -> str:
        """The source of one module."""
        # Each module has a context of its own, which collects its imports.
        ctx = Context(
            self.model,
            self.rules,
            self._module_of,
            self._counted,
            self._sizes,
            module.name,
        )
        emit = Emitter(ctx)
        consts = [d for d in module.definitions if isinstance(d, Const)]
        enums = [d for d in module.definitions if isinstance(d, Enum)]
        typedefs = [d for d in module.definitions if isinstance(d, Typedef)]
        simple = [d for d in typedefs if _is_simple_typedef(d)]
        composite = _ordered_typedefs(
            [d for d in typedefs if not _is_simple_typedef(d)]
        )
        classes = [d for d in module.definitions if isinstance(d, Struct | Union)]
        blocks: list[list[str]] = []
        if consts:
            blocks.append([line for d in consts for line in emit.const(d)])
        blocks += [emit.enum(d) for d in enums]
        blocks += [emit.typedef(d) for d in simple]
        for d in classes:
            blocks.append(emit.struct(d) if isinstance(d, Struct) else emit.union(d))
        blocks += [emit.typedef(d) for d in composite]
        body = "\n\n\n".join("\n".join(b) for b in blocks)
        public = sorted(_public_name(d) for d in module.definitions)
        exports = "\n".join(f"    {n!r}," for n in public)
        return "\n".join(
            [
                HEADER.rstrip(),
                f'"""The types of ``{module.xdr_file.rsplit("/", 1)[-1]}``.',
                "",
                "Import them from `stellar_xdr`. This module is private: it follows",
                "the layout of the `.x` files, and a definition can move to another",
                "file between releases.",
                '"""',
                "",
                "# The code uses private parts of the runtime and of other modules.",
                "# pyright: reportPrivateUsage=false",
                "",
                "from __future__ import annotations",
                "",
                *_imports(ctx.imports, body),
                "",
                "",
                body,
                "",
                "",
                f"__all__ = [\n{exports}\n]",
                "",
            ]
        )

    def package_init(self) -> str:
        """The source of the package's `__init__.py`, which re-exports every name."""
        lines = [
            HEADER.rstrip(),
            '"""Strict, fully typed encoding and decoding of Stellar XDR.',
            "",
            "Every type is importable from here, and this is the only place to import",
            "one from: the modules that define them are private.",
            '"""',
            "",
            "from typing import Final",
            "",
            "from ._runtime import (",
            *(f"    {n}," for n in sorted(PUBLIC_RUNTIME_NAMES)),
            ")",
        ]
        exported = [*PUBLIC_RUNTIME_NAMES, "PROTOCOL_VERSION"]
        for module in self.modules.values():
            public = sorted(_public_name(d) for d in module.definitions)
            exported += public
            lines += [
                f"from .{module.name} import (",
                *(f"    {n}," for n in public),
                ")",
            ]
        lines += [
            "",
            f"PROTOCOL_VERSION: Final = {self.protocol}",
            '"""The Stellar protocol version of the XDR definitions in this release.',
            "",
            "The package's own version follows semantic versioning of its API, so it",
            "doesn't say which protocol it supports; this does.",
            '"""',
            "",
            "__all__ = [",
            *(f"    {n!r}," for n in sorted(exported)),
            "]",
            "",
        ]
        return "\n".join(lines)

    def arm_names(self) -> str:
        """`generator/arm_names.txt`: the arm classes of every union, one line each.

        The generated code is too long to review by eye, so a change to the names users
        see, such as an ugly name for a new union, would be easy to miss. In this short
        file, every such change shows up in the diff of an update.
        """
        lines = [
            "# Generated by `python -m generator`: the arm classes of every union. A",
            "# change here is a change to the API; see `arm_class_name` in names.py.",
        ]
        for d in self.model.definitions:
            if isinstance(d, Union):
                arms = [c.class_name for c in names.union_cases(self.model, d)]
                lines.append(f"{names.type_name(d.name)}: {', '.join(arms)}")
        return "\n".join(lines) + "\n"

    def sources(self) -> dict[str, str]:
        """Every generated file of the package, by path relative to the package."""
        result = {f"{m.name}.py": self.module(m) for m in self.modules.values()}
        result["__init__.py"] = self.package_init()
        return result
