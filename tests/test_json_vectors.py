"""XDR-JSON matches the reference implementation, value for value.

`scripts/make_json_vectors.py` records the reference output for network values and
random values of every type, changed to SEP-51 where the reference differs from it.
"""

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

import stellar_xdr as xdr

from .strategies import STRATEGIES

VECTORS = json.loads(
    gzip.decompress(
        (Path(__file__).parent / "vectors" / "xdr_json_values.json.gz").read_bytes()
    )
)


def test_every_type_has_vectors() -> None:
    # A type added upstream, until the vectors are made again, has none.
    assert set(STRATEGIES) - {v["type"] for v in VECTORS} == set()


@pytest.mark.parametrize(
    "vector", VECTORS, ids=[f"{v['type']}-{i}" for i, v in enumerate(VECTORS)]
)
def test_json_matches_the_reference(vector: dict[str, Any]) -> None:
    decoder: Any = getattr(xdr, vector["type"])
    value = decoder.from_xdr_base64(vector["xdr"])
    assert value.to_json_value() == vector["json"]
    assert decoder.from_json_value(vector["json"]) == value


# The fields the reference writes as arrays of integers, where SEP-51 uses hex.
INLINE_OPAQUE_KEYS = frozenset({"i_pv4", "i_pv6", "key", "mac", "seed"})


def differences(reference: Any, expected: Any, key: str | None = None) -> list[str]:
    """Where the expected JSON differs from the reference, other than inline opaque."""
    if (
        key in INLINE_OPAQUE_KEYS
        and isinstance(reference, list)
        and isinstance(expected, str)
        and bytes(reference).hex() == expected  # pyright: ignore[reportUnknownArgumentType]
    ):
        return []
    if isinstance(reference, dict) and isinstance(expected, dict):
        ref: dict[str, Any] = reference  # pyright: ignore[reportUnknownVariableType]
        exp: dict[str, Any] = expected  # pyright: ignore[reportUnknownVariableType]
        if ref.keys() != exp.keys():
            return [f"keys {sorted(ref)} != {sorted(exp)}"]
        return [d for k in ref for d in differences(ref[k], exp[k], k)]
    if isinstance(reference, list) and isinstance(expected, list):
        ref_items: list[Any] = reference  # pyright: ignore[reportUnknownVariableType]
        exp_items: list[Any] = expected  # pyright: ignore[reportUnknownVariableType]
        if len(ref_items) != len(exp_items):
            return ["lengths differ"]
        return [
            d
            for r, e in zip(ref_items, exp_items, strict=True)
            for d in differences(r, e)
        ]
    return [] if reference == expected else [f"{reference!r} != {expected!r}"]


CHANGED = [v for v in VECTORS if "reference" in v]


@pytest.mark.parametrize(
    "vector", CHANGED, ids=[f"{v['type']}-{i}" for i, v in enumerate(CHANGED)]
)
def test_only_the_known_differences_are_changed(vector: dict[str, Any]) -> None:
    assert differences(vector["reference"], vector["json"]) == []
