"""The vendored `xdr.json` is intact and recorded in `xdr/source.toml`."""

import hashlib
import json
import tomllib
from pathlib import Path

import stellar_xdr

XDR = Path(__file__).resolve().parent.parent / "xdr"


def test_xdr_json_matches_its_recorded_sha256() -> None:
    source = tomllib.loads((XDR / "source.toml").read_text())
    data = (XDR / "xdr.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == source["sha256"]


def test_xdr_json_is_a_supported_version() -> None:
    document = json.loads((XDR / "xdr.json").read_bytes())
    assert document["version"] == 1
    assert document["resolved_features"] == []


def test_the_package_states_the_protocol_of_its_definitions() -> None:
    source = tomllib.loads((XDR / "source.toml").read_text())
    assert stellar_xdr.PROTOCOL_VERSION == source["protocol"] == 30
