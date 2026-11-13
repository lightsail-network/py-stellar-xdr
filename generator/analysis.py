"""What the generator works out of the model as a whole, before it writes anything.

Which types count towards `max_depth`, and the fewest bytes a value of each type
encodes to.
"""

from collections.abc import Iterator

from .model import (
    Array,
    Definition,
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


def references(d: Definition) -> set[str]:
    """The definitions that a definition refers to by name."""

    def walk(t: TypeRef | None) -> Iterator[str]:
        if isinstance(t, Ref):
            yield t.name
        elif isinstance(t, Array | VarArray | Optional):
            yield from walk(t.element)

    if isinstance(d, Struct):
        return {n for f in d.fields for n in walk(f.type)}
    if isinstance(d, Union):
        return {n for a in d.arms for n in walk(a.type)}
    if isinstance(d, Typedef):
        return set(walk(d.type))
    return set()


def counted_types(model: Model) -> set[str]:
    """The types whose nesting counts towards `max_depth`.

    These are the unions on a cycle of references, such as `SCVal` through `SCVec`.
    Counting only the unions makes the depth of an `SCVal` its nesting as a value, not
    the number of XDR structures on the way. If a cycle has no union, its structs are
    counted, so that every cycle counts at least once.
    """
    graph = {d.name: references(d) for d in model.definitions}
    # Tarjan's strongly connected components.
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    components: list[set[str]] = []

    def visit(v: str) -> None:
        index[v] = low[v] = len(index)
        stack.append(v)
        on_stack.add(v)
        for w in graph[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            component: set[str] = set()
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.add(w)
                if w == v:
                    break
            components.append(component)

    for v in graph:
        if v not in index:
            visit(v)
    counted: set[str] = set()
    for component in components:
        first = next(iter(component))
        cyclic = len(component) > 1 or first in graph[first]
        if not cyclic:
            continue
        unions = {n for n in component if isinstance(model.get(n), Union)}
        chosen = unions or {n for n in component if isinstance(model.get(n), Struct)}
        rest = component - chosen
        if _has_cycle({n: graph[n] & rest for n in rest}):
            msg = f"a cycle among {sorted(rest)} passes through no counted type"
            raise GenerationError(msg)
        counted |= chosen
    return counted


def _has_cycle(graph: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(v: str) -> bool:
        visiting.add(v)
        for w in graph[v]:
            if w in visiting or (w not in done and visit(w)):
                return True
        visiting.discard(v)
        done.add(v)
        return False

    return any(v not in done and visit(v) for v in graph)


class Sizes:
    """The smallest encoding of every type, which bounds the length of an array.

    The sizes are worked out for the whole model, when the first one is asked for.
    """

    def __init__(self, model: Model) -> None:
        self._model = model
        self._sizes: dict[str, int] = {}

    def min_size(self, t: TypeRef) -> int:
        """The fewest bytes a value of a type encodes to."""
        if isinstance(t, Primitive):
            return 8 if t.kind in {"hyper", "unsigned_hyper"} else 4
        if isinstance(t, OpaqueFixed):
            return t.size + (-t.size % 4)
        if isinstance(t, OpaqueVar | String | VarArray | Optional):
            return 4
        if isinstance(t, Array):
            return t.count * self.min_size(t.element)
        if not self._sizes:
            self._compute()
        return self._sizes[t.name]

    def _compute(self) -> None:
        # A union can contain itself through a struct when another arm ends the
        # recursion (SCSpecTypeDef holds SCSpecTypeOption, which holds SCSpecTypeDef),
        # so the sizes are a fixed point: start from "infinite" and lower them until
        # nothing changes.
        infinite = 2**62
        definitions = [
            d
            for d in self._model.definitions
            if isinstance(d, Typedef | Struct | Union | Enum)
        ]
        self._sizes = {d.name: infinite for d in definitions}
        changed = True
        while changed:
            changed = False
            for d in definitions:
                if isinstance(d, Typedef):
                    size = self.min_size(d.type)
                elif isinstance(d, Struct):
                    size = sum(self.min_size(f.type) for f in d.fields)
                elif isinstance(d, Union):
                    size = 4 + min(
                        0 if a.type is None else self.min_size(a.type) for a in d.arms
                    )
                else:
                    size = 4
                size = min(size, infinite)
                if size < self._sizes[d.name]:
                    self._sizes[d.name] = size
                    changed = True
        if infinite in self._sizes.values():
            msg = "a type can't be encoded in finite size"
            raise GenerationError(msg)
