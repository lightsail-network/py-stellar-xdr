"""Record reference XDR-JSON into `tests/vectors/xdr_json_values.json.gz`.

Usage:
    python scripts/make_json_vectors.py PATH_TO_STELLAR_XDR_CLI

The CLI is the `stellar-xdr` binary of stellar/rs-stellar-xdr at the commit in
`xdr/source.toml`, built with `cargo build --features cli`. The values are the network
vectors and a few random values of every type. Where the reference differs from
SEP-51, its output is changed to what SEP-51 specifies before it is recorded; see
`normalize`, and the reference output is recorded alongside.
"""

import base64
import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import stellar_xdr  # noqa: E402
from generator.names import upper_camel  # noqa: E402
from tests.strategies import STRATEGIES  # noqa: E402

OUTPUT = ROOT / "tests" / "vectors" / "xdr_json_values.json.gz"
NETWORK = ROOT / "tests" / "vectors" / "network_values.json.gz"
RANDOM_VALUES = 8
# Values longer than this, in base64, are passed one at a time on stdin.
LARGE = 2000

# The reference writes inline fixed-length opaque fields (PeerAddressIp.ipv4/ipv6,
# Curve25519Public.key, Curve25519Secret.key, HmacSha256Key.key, HmacSha256Mac.mac and
# ShortHashSeed.seed) as arrays of integers; SEP-51 writes all opaque data as hex.
_INLINE_OPAQUE_KEYS = frozenset({"i_pv4", "i_pv6", "key", "mac", "seed"})


def normalize(value: Any) -> Any:  # noqa: ANN401 - JSON
    """Change the reference output to SEP-51 where they differ."""
    if isinstance(value, dict):
        obj: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
        return {k: _normalize_field(k, v) for k, v in obj.items()}
    if isinstance(value, list):
        items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        return [normalize(v) for v in items]
    return value


def _normalize_field(key: str, value: Any) -> Any:  # noqa: ANN401 - JSON
    if key in _INLINE_OPAQUE_KEYS and isinstance(value, list):
        items: list[Any] = value  # pyright: ignore[reportUnknownVariableType]
        if all(isinstance(b, int) for b in items):
            return bytes(items).hex()
    return normalize(value)


# The reference names types in UpperCamel case (SCVal is ScVal), except where that
# collides with a name of its own.
_CLI_NAMES = {"Error": "SError"}


def reference(cli: str, type_name: str, values: list[str]) -> list[Any]:
    """Decode values with the reference CLI, one JSON document per value."""
    cli_name = _CLI_NAMES.get(type_name, upper_camel(type_name))
    command = [cli, "decode", "--type", cli_name, "--input", "single-base64"]
    if len(values) == 1:
        # A large value, such as a whole ledger, doesn't fit on a command line.
        result = subprocess.run(  # noqa: S603 - the CLI given on the command line
            command, input=values[0], capture_output=True, text=True, check=True
        )
    else:
        result = subprocess.run(  # noqa: S603 - the CLI given on the command line
            [*command, *values], capture_output=True, text=True, check=True
        )
    lines = result.stdout.splitlines()
    if len(lines) != len(values):
        sys.exit(f"{type_name}: expected {len(values)} documents, got {len(lines)}")
    return [json.loads(line) for line in lines]


def main() -> None:
    """Collect values, convert them with the reference CLI and write the vectors."""
    cli = sys.argv[1]
    by_type: dict[str, list[str]] = {}
    for v in json.loads(gzip.decompress(NETWORK.read_bytes())):
        if hasattr(stellar_xdr, v["type"]) and not hasattr(
            stellar_xdr.typedefs, v["type"]
        ):
            by_type.setdefault(v["type"], []).append(v["xdr"])
    for name, strategy in STRATEGIES.items():
        examples = {strategy.example().to_xdr_base64() for _ in range(RANDOM_VALUES)}
        by_type.setdefault(name, []).extend(sorted(examples))
    vectors: list[dict[str, Any]] = []
    for name, values in sorted(by_type.items()):
        # Keep the command lines short: small values in groups, large ones alone.
        small = [v for v in values if len(v) < LARGE]
        chunks = [small[i : i + 50] for i in range(0, len(small), 50)]
        chunks += [[v] for v in values if len(v) >= LARGE]
        for chunk in chunks:
            for xdr, document in zip(chunk, reference(cli, name, chunk), strict=True):
                vector = {"type": name, "xdr": xdr, "json": normalize(document)}
                # Where SEP-51 changed it, the reference output is kept too, so that
                # the tests can check that nothing else was changed.
                if vector["json"] != document:
                    vector["reference"] = document
                vectors.append(vector)
    data = json.dumps(vectors, indent=2, sort_keys=True).encode()
    OUTPUT.write_bytes(gzip.compress(data, mtime=0))
    raw = sum(len(base64.b64decode(v["xdr"])) for v in vectors)
    print(f"{len(vectors)} vectors of {len(by_type)} types, {raw} bytes of XDR")


if __name__ == "__main__":
    main()
