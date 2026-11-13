"""Emit `tests/strategies.py`: a Hypothesis strategy for every type."""

from typing import Final

from . import names
from .model import (
    Array,
    Enum,
    Model,
    OpaqueFixed,
    OpaqueVar,
    Primitive,
    Ref,
    String,
    Struct,
    Typedef,
    TypeRef,
    Union,
    VarArray,
)
from .text import HEADER
from .typecode import typedef_base

# The ranges are written out here, not taken from the package: the tests then state
# them a second time, and the generator runs without importing what it generates.
_INTEGER_RANGES: Final = {
    "int": ("-(2**31)", "2**31 - 1"),
    "unsigned_int": ("0", "2**32 - 1"),
    "hyper": ("-(2**63)", "2**63 - 1"),
    "unsigned_hyper": ("0", "2**64 - 1"),
}

# Kept small so that examples stay fast; the limits themselves are tested separately.
_MAX_TEST_BYTES: Final = 40
_MAX_TEST_ITEMS: Final = 3

# Fields whose random values need a length of their own: (struct, field) to the fewest
# bytes. A strkey, and so SEP-51, needs a signed payload of at least one byte.
_MIN_TEST_BYTES: Final = {("SignerKeyEd25519SignedPayload", "payload"): 1}


class StrategyGenerator:
    """Emits `tests/strategies.py`: a Hypothesis strategy for every type."""

    def __init__(self, model: Model) -> None:
        self.model = model

    def _strategy(self, t: TypeRef, min_bytes: int = 0) -> str:
        if isinstance(t, Primitive):
            if t.kind == "bool":
                return "st.booleans()"
            low, high = _INTEGER_RANGES[t.kind]
            return f"st.integers({low}, {high})"
        if isinstance(t, Ref):
            d = self.model.get(t.name)
            if isinstance(d, Typedef):
                return self._strategy(d.type, min_bytes)
            return f"ref({names.type_name(t.name)!r})"
        if isinstance(t, OpaqueFixed):
            return f"st.binary(min_size={t.size}, max_size={t.size})"
        if isinstance(t, OpaqueVar | String):
            limit = min(t.max_size or _MAX_TEST_BYTES, _MAX_TEST_BYTES)
            if min_bytes:
                return f"st.binary(min_size={min_bytes}, max_size={limit})"
            return f"st.binary(max_size={limit})"
        if isinstance(t, VarArray):
            limit = min(
                _MAX_TEST_ITEMS if t.max_count is None else t.max_count, _MAX_TEST_ITEMS
            )
            return f"st.lists({self._strategy(t.element)}, max_size={limit}).map(tuple)"
        if isinstance(t, Array):
            n = t.count
            element = self._strategy(t.element)
            return f"st.lists({element}, min_size={n}, max_size={n}).map(tuple)"
        return f"st.none() | {self._strategy(t.element)}"

    def source(self) -> str:
        """The source of the strategies module."""
        lines = [
            HEADER.rstrip(),
            '"""A Hypothesis strategy for every type, keyed by its Python name."""',
            "",
            "from typing import Any",
            "",
            "from hypothesis import strategies as st",
            "",
            "import stellar_xdr as xdr",
            "",
            "STRATEGIES: dict[str, st.SearchStrategy[Any]] = {}",
            '"""Every struct, enum, union and typedef that is a class."""',
            "",
            "ARMS: dict[str, tuple[str, st.SearchStrategy[Any]]] = {}",
            '"""Every arm of every union, such as "SCVal.U32", with its union."""',
            "",
            "DISCRIMINANTS: dict[str, frozenset[int]] = {}",
            '"""The discriminants that select an arm, for every union."""',
            "",
            "",
            "def ref(name: str) -> st.SearchStrategy[Any]:",
            '    """The strategy of a definition, looked up when it is first used."""',
            "    return st.deferred(lambda: STRATEGIES[name])",
            "",
            "",
        ]
        for d in self.model.definitions:
            name = names.type_name(d.name)
            if isinstance(d, Struct):
                fields = [
                    self._strategy(f.type, _MIN_TEST_BYTES.get((d.name, f.name), 0))
                    for f in d.fields
                ]
                args = "".join(f", {strategy}" for strategy in fields)
                lines.append(f"STRATEGIES[{name!r}] = st.builds(xdr.{name}{args})")
            elif isinstance(d, Enum):
                lines.append(f"STRATEGIES[{name!r}] = st.sampled_from(xdr.{name})")
            elif isinstance(d, Typedef):
                # An alias has no class of its own to test: its type has.
                if typedef_base(self.model, d) is not None:
                    plain = self._strategy(d.type)
                    lines.append(
                        f"STRATEGIES[{name!r}] = st.builds(xdr.{name}, {plain})"
                    )
            elif isinstance(d, Union):
                cases = names.union_cases(self.model, d)
                arms: list[str] = []
                for case in cases:
                    arm = f"{name}.{case.class_name}"
                    held = case.arm.type
                    payload = "" if held is None else f", {self._strategy(held)}"
                    strategy = f"st.builds(xdr.{arm}{payload})"
                    arms.append(strategy)
                    lines.append(f"ARMS[{arm!r}] = ({name!r}, {strategy})")
                lines.append(f"STRATEGIES[{name!r}] = st.one_of({', '.join(arms)})")
                values = sorted(c.value for c in cases)
                lines.append(f"DISCRIMINANTS[{name!r}] = frozenset({values})")
        lines.append("")
        return "\n".join(lines)
