"""Vendor `xdr.json` from stellar/rs-stellar-xdr at a pinned commit.

Usage:
    python scripts/update_xdr.py COMMIT   download the file at COMMIT, report changes
    python scripts/update_xdr.py --check  check the vendored file against its commit

`xdr.json` describes every type in the network's `.x` files and is the generator's only
input. It is downloaded rather than linked as a submodule, so that the repository holds
exactly the file the code was generated from, and its provenance is recorded in
`xdr/source.toml`.
"""

import argparse
import hashlib
import json
import re
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XDR_JSON = ROOT / "xdr" / "xdr.json"
SOURCE = ROOT / "xdr" / "source.toml"

REPOSITORY = "stellar/rs-stellar-xdr"
UPSTREAM_PATH = "xdr-definitions-json/xdr.json"
# Holds the stellar/stellar-xdr commit of the .x files that xdr.json was generated from.
UPSTREAM_XDR_VERSION_PATH = "xdr-version"


def fetch(commit: str, path: str) -> bytes:
    """Download one file of the upstream repository at a commit."""
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{path}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data: bytes = response.read()
    return data


def definitions(data: bytes) -> dict[str, str]:
    """Map each definition's name to its `.x` source text."""
    document = json.loads(data)
    if document.get("version") != 1:
        sys.exit(f"unsupported xdr.json version: {document.get('version')!r}")
    return {d["name"]: d["source"] for d in document["definitions"]}


def report(old: dict[str, str], new: dict[str, str]) -> None:
    """Print the definitions that were added, removed or changed."""
    sections = {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(n for n in old.keys() & new.keys() if old[n] != new[n]),
    }
    for title, names in sections.items():
        print(f"{title}: {len(names)}")
        for name in names:
            print(f"  {name}")


def protocol(commit: str) -> int:
    """The protocol version of the definitions: the major version of the crate.

    rs-stellar-xdr releases its crate with the protocol version as major version.
    """
    manifest = tomllib.loads(fetch(commit, "Cargo.toml").decode())
    major: str = manifest["package"]["version"].split(".")[0]
    return int(major)


def update(commit: str) -> None:
    """Download xdr.json at a commit, record where it came from, and report changes."""
    data = fetch(commit, UPSTREAM_PATH)
    xdr_commit = fetch(commit, UPSTREAM_XDR_VERSION_PATH).decode().strip()
    new = definitions(data)
    old = definitions(XDR_JSON.read_bytes()) if XDR_JSON.exists() else {}
    XDR_JSON.write_bytes(data)
    SOURCE.write_text(
        "# Written by scripts/update_xdr.py; do not edit.\n"
        f'repository = "https://github.com/{REPOSITORY}"\n'
        f'commit = "{commit}"\n'
        "# The stellar/stellar-xdr commit of the .x files behind xdr.json.\n"
        f'xdr_commit = "{xdr_commit}"\n'
        "# The Stellar protocol version the definitions are for.\n"
        f"protocol = {protocol(commit)}\n"
        f'sha256 = "{hashlib.sha256(data).hexdigest()}"\n'
    )
    print(f"xdr.json at {REPOSITORY}@{commit} ({len(new)} definitions)")
    report(old, new)


def check() -> None:
    """Fail unless the vendored file is the upstream file at the pinned commit."""
    source = tomllib.loads(SOURCE.read_text())
    commit: str = source["commit"]
    data = XDR_JSON.read_bytes()
    if hashlib.sha256(data).hexdigest() != source["sha256"]:
        sys.exit("xdr/xdr.json does not match the sha256 in xdr/source.toml")
    if fetch(commit, UPSTREAM_PATH) != data:
        sys.exit(f"xdr/xdr.json differs from {REPOSITORY}@{commit}")
    xdr_commit = fetch(commit, UPSTREAM_XDR_VERSION_PATH).decode().strip()
    if xdr_commit != source["xdr_commit"]:
        sys.exit(f"xdr_commit in xdr/source.toml differs from {REPOSITORY}@{commit}")
    if protocol(commit) != source["protocol"]:
        sys.exit(f"protocol in xdr/source.toml differs from {REPOSITORY}@{commit}")
    print(f"xdr/xdr.json matches {REPOSITORY}@{commit}")


def main() -> None:
    """Parse the command line."""
    parser = argparse.ArgumentParser(description="Vendor xdr.json at a pinned commit.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("commit", nargs="?", help="full commit hash to vendor")
    group.add_argument("--check", action="store_true", help="verify the vendored file")
    args = parser.parse_args()
    if args.check:
        check()
    elif re.fullmatch(r"[0-9a-f]{40}", args.commit):
        update(args.commit)
    else:
        # A tag or branch could move, so only a full hash pins the file.
        parser.error("COMMIT must be a full 40-character commit hash")


if __name__ == "__main__":
    main()
