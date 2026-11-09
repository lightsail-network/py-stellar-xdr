"""Real values from the public networks decode and encode back to the same bytes.

`scripts/fetch_network_vectors.py` collects them from ledgers across the history of
mainnet and testnet and from recent transactions; see `tests/vectors/README.md`.
"""

import gzip
import json
from pathlib import Path
from typing import Any

import pytest

import stellar_xdr as xdr
from stellar_xdr import typedefs

VECTORS = json.loads(
    gzip.decompress(
        (Path(__file__).parent / "vectors" / "network_values.json.gz").read_bytes()
    )
)


def round_trip(name: str, text: str) -> str:
    """Decode and encode again, with the class, union or typedef codec of a type."""
    codec: Any = getattr(typedefs, name, None)
    if codec is not None:
        encoded: str = codec.to_xdr_base64(codec.from_xdr_base64(text))
    else:
        encoded = getattr(xdr, name).from_xdr_base64(text).to_xdr_base64()
    return encoded


@pytest.mark.parametrize(
    "vector",
    VECTORS,
    ids=[f"{v['network']}-{v['type']}-{i}" for i, v in enumerate(VECTORS)],
)
def test_network_value(vector: dict[str, str]) -> None:
    assert round_trip(vector["type"], vector["xdr"]) == vector["xdr"]
