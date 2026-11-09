"""Record the reference SEP-51 names into `tests/vectors/xdr_json_names.json`.

Usage:
    python scripts/make_json_names.py PATH_TO_RS_STELLAR_XDR

The path is a checkout of stellar/rs-stellar-xdr at the commit in `xdr/source.toml`.
Its `xdr-json/` directory has a JSON schema per type; this keeps only the names: the
members of every enum, the keys of every union and the fields of every struct, so that
the generator's naming rules can be tested against them without the checkout.
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "tests" / "vectors" / "xdr_json_names.json"


def names(schema: dict[str, Any]) -> list[str] | None:
    """The names a schema allows: enum strings, union keys or struct fields."""
    if schema.get("type") == "string" and "enum" in schema:
        return sorted(schema["enum"])
    if "oneOf" in schema:
        keys: list[str] = []
        for alternative in schema["oneOf"]:
            if alternative.get("type") == "string":
                keys += alternative.get("enum", [])
            elif alternative.get("type") == "object":
                keys += alternative.get("required", [])
        return sorted(keys)
    if schema.get("type") == "object" and "properties" in schema:
        return sorted(k for k in schema["properties"] if k != "$schema")
    # Types written as strings, such as strkeys and big integers.
    return None


def main() -> None:
    """Read every schema and write the names of every type."""
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted((Path(sys.argv[1]) / "xdr-json").glob("*.json")):
        document = json.loads(path.read_text())
        schemas[document["title"]] = document
        for name, definition in document.get("definitions", {}).items():
            schemas.setdefault(name, definition)
    result = {
        name: found
        for name, schema in sorted(schemas.items())
        if (found := names(schema)) is not None
    }
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"names of {len(result)} types")


if __name__ == "__main__":
    main()
