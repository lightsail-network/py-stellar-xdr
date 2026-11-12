"""Collect real XDR from the networks into `tests/vectors/network_values.json.gz`.

Usage:
    python scripts/fetch_network_vectors.py

It needs Python 3.14 or later, for `compression.zstd`.

The values come from two read-only sources, for mainnet and testnet:

- ledgers sampled across the whole history of each network, from the public ledger
  data lake on AWS. It has every ledger, but rebuilt with a recent stellar-core: the
  transactions of old protocols are there, but their metadata is in the current
  format, so older metadata formats aren't covered;
- recent transactions, with their metadata and events, and the latest ledger, from
  public RPC servers.

Every ledger, transaction, result, metadata, event, ledger entry and contract value
found in them is a candidate. Most are alike, so candidates are taken from the smallest
up, and one is kept only if it holds a type, union arm or enum member that no kept
value holds yet. A few whole ledgers are kept as well. Every kept value is checked to
encode back to the same bytes, so a failure here is already a bug report.
"""

# The script walks decoded values of any type, which type checkers can't follow.
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false

import base64
import gzip
import importlib
import json
import re
import sys
import typing
import urllib.error
import urllib.request
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "tests" / "vectors" / "network_values.json.gz"
sys.path.insert(0, str(ROOT / "src"))

import stellar_xdr as xdr  # noqa: E402
from stellar_xdr import typedefs  # noqa: E402
from stellar_xdr._runtime import UnionNamespace  # noqa: E402

NETWORKS = {
    "mainnet": {
        "rpc": "https://mainnet.sorobanrpc.com",
        "lake": "pubnet",
        "samples": 150,
        "pages": 3,
    },
    "testnet": {
        "rpc": "https://soroban-testnet.stellar.org",
        # Testnet is reset now and then; the data lake has a directory per reset.
        "lake": "testnet/*",
        "samples": 60,
        # Testnet has more contract deployments to find.
        "pages": 10,
    },
}
LAKE = "https://aws-public-blockchain.s3.us-east-2.amazonaws.com/v1.1/stellar/ledgers"
LEDGERS_PER_PARTITION = 64000
PAGE_SIZE = 200
# Beyond what adds coverage, this many values of every type are kept, spread over
# their sizes, so that large values are tested as well as small ones.
AT_LEAST = 25
# A whole ledger is only worth keeping when it holds more than its own header.
MIN_LEDGER_SIZE = 10_000
# Some servers reject urllib's default User-Agent.
HEADERS = {"User-Agent": "stellar-xdr-test-vectors", "Content-Type": "application/json"}

# The types that values are collected as: where one of these appears anywhere in a
# decoded value, it becomes a candidate of its own.
UNIONS = [
    "TransactionEnvelope",
    "TransactionMeta",
    "LedgerEntryChange",
    "LedgerUpgrade",
    "LedgerKey",
    "SCVal",
    "SCAddress",
]
STRUCTS = [
    "TransactionResult",
    "LedgerHeaderHistoryEntry",
    "SCPEnvelope",
    "SCPQuorumSet",
    "LedgerEntry",
    "ContractEvent",
    "DiagnosticEvent",
    "TransactionEvent",
    "UpgradeEntryMeta",
]


def rpc(url: str, method: str, params: dict[str, Any] | None = None) -> Any:  # noqa: ANN401
    """Call a JSON-RPC method."""
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    request = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(body).encode(), headers=HEADERS
    )
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        reply = json.load(response)
    if "error" in reply:
        sys.exit(f"{method}: {reply['error']}")
    return reply["result"]


def lake_directory(network: str) -> str:
    """The data lake directory of a network: its latest reset for `name/*`."""
    if not network.endswith("/*"):
        return network
    prefix = f"v1.1/stellar/ledgers/{network[:-1]}"
    url = (
        f"{LAKE.split('/v1.1', maxsplit=1)[0]}/?list-type=2&prefix={prefix}&delimiter=/"
    )
    request = urllib.request.Request(url, headers=HEADERS)  # noqa: S310
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        listing = response.read().decode()
    resets = re.findall(rf"<Prefix>{re.escape(prefix)}([^<]+)/</Prefix>", listing)
    return f"{network[:-2]}/{max(resets)}"


def lake_ledger(network: str, seq: int) -> bytes | None:
    """A ledger's `LedgerCloseMetaBatch` from the data lake, or None if it's missing."""
    zstd: Any = importlib.import_module("compression.zstd")
    start = seq // LEDGERS_PER_PARTITION * LEDGERS_PER_PARTITION
    end = start + LEDGERS_PER_PARTITION - 1
    url = (
        f"{LAKE}/{network}/{0xFFFFFFFF - start:08X}--{start}-{end}/"
        f"{0xFFFFFFFF - seq:08X}--{seq}.xdr.zst"
    )
    request = urllib.request.Request(url, headers=HEADERS)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            data: bytes = zstd.decompress(response.read())
    except urllib.error.HTTPError:
        return None
    return data


# --- Finding candidates and what they cover ---------------------------------------

UNITS: dict[type, str] = {}
for _union in UNIONS:
    for _arm in typing.get_args(getattr(xdr, _union).Any) or (
        getattr(xdr, _union).Any,
    ):
        UNITS[_arm] = _union
for _struct in STRUCTS:
    UNITS[getattr(xdr, _struct)] = _struct
# The structs that hold a transaction's fee changes, a LedgerEntryChanges.
FEE_CHANGES = {xdr.TransactionResultMeta, xdr.TransactionResultMetaV1}


def parts(value: Any) -> Iterator[tuple[str, Any]]:  # noqa: ANN401 - any XDR value
    """Every value of a collected type inside a value, including the value itself."""
    name = UNITS.get(type(value))
    if name is not None:
        yield name, value
    if type(value) in FEE_CHANGES:
        # A typedef has no class to recognize it by, so its one use is named here.
        yield "LedgerEntryChanges", value.fee_processing
    if isinstance(value, tuple):
        for item in value:
            yield from parts(item)
    elif hasattr(value, "_fields"):
        for field in value._fields:
            yield from parts(getattr(value, field))


def coverage(value: Any, found: set[str]) -> set[str]:  # noqa: ANN401 - any XDR value
    """The classes and enum members a value holds."""
    if isinstance(value, Enum):
        found.add(f"{type(value).__qualname__}.{value.name}")
    elif isinstance(value, tuple):
        for item in value:
            coverage(item, found)
    elif hasattr(value, "_fields"):
        found.add(type(value).__qualname__)
        for field in value._fields:
            coverage(getattr(value, field), found)
    return found


class Collector:
    """Candidates from every source, and the whole ledgers worth keeping."""

    def __init__(self) -> None:
        self.candidates: dict[tuple[str, str], tuple[str, set[str]]] = {}
        self.ledgers: dict[str, tuple[str, str, int]] = {}

    def add(self, network: str, value: Any) -> None:  # noqa: ANN401
        """Add a decoded value and every collected value inside it."""
        for part_name, part in parts(value):
            codec = getattr(typedefs, part_name, None)
            if codec is not None:
                self._candidate(network, part_name, codec.to_xdr_base64(part), part)
            else:
                self._candidate(network, part_name, part.to_xdr_base64())

    def add_xdr(self, network: str, name: str, text: str | None) -> None:
        """Add a value given as base64, of a type or a typedef."""
        if not text:
            return
        codec = getattr(typedefs, name, None)
        if codec is not None:
            # A typedef has no class; keep it as it is, and its parts too.
            self._candidate(network, name, text, codec.from_xdr_base64(text))
            for item in codec.from_xdr_base64(text):
                self.add(network, item)
            return
        self.add(network, getattr(xdr, name).from_xdr_base64(text))
        if name not in UNITS.values():
            self._candidate(network, name, text)

    def add_ledger(self, network: str, meta: Any, size: int) -> None:  # noqa: ANN401
        """Add a whole ledger; the smallest non-trivial one of each version is kept."""
        version = type(meta).__qualname__
        text = meta.to_xdr_base64()
        kept = self.ledgers.get(version)
        if size > MIN_LEDGER_SIZE and (kept is None or size < kept[2]):
            self.ledgers[version] = (network, text, size)
        self.add(network, meta)

    def _candidate(
        self, network: str, name: str, text: str, value: object = None
    ) -> None:
        if (name, text) in self.candidates:
            return
        if value is None:
            value = getattr(xdr, name).from_xdr_base64(text)
        self.candidates[(name, text)] = (network, coverage(value, set()))

    def select(self) -> list[dict[str, str]]:
        """The smallest set of candidates that holds everything any of them holds."""
        covered: set[str] = set()
        ordered = sorted(self.candidates.items(), key=lambda item: len(item[0][1]))
        chosen: dict[tuple[str, str], str] = {}
        for key, (network, found) in ordered:
            if found - covered:
                covered |= found
                chosen[key] = network
        by_type: dict[str, list[tuple[tuple[str, str], str]]] = {}
        for key, (network, _) in ordered:
            by_type.setdefault(key[0], []).append((key, network))
        for values in by_type.values():
            step = max(1, len(values) // AT_LEAST)
            for key, network in values[::step][:AT_LEAST]:
                chosen.setdefault(key, network)
        kept = [
            {"network": network, "type": name, "xdr": text}
            for (name, text), network in chosen.items()
        ]
        for network, text, _ in self.ledgers.values():
            kept.append({"network": network, "type": "LedgerCloseMeta", "xdr": text})
        return kept


# --- Sources ----------------------------------------------------------------------


def from_lake(collector: Collector, network: str, settings: dict[str, Any]) -> None:
    """Ledgers sampled evenly across a network's history."""
    latest = rpc(settings["rpc"], "getLatestLedger")["sequence"] - 1000
    samples: int = settings["samples"]
    directory = lake_directory(settings["lake"])
    for i in range(samples):
        seq = 2 + (latest - 2) * i // (samples - 1)
        data = lake_ledger(directory, seq)
        if data is None:
            print(f"  {network} ledger {seq}: not in the data lake")
            continue
        batch = xdr.LedgerCloseMetaBatch.from_xdr_bytes(data)
        if batch.to_xdr_bytes() != data:
            sys.exit(f"{network} ledger {seq} does not re-encode")
        for meta in batch.ledger_close_metas:
            collector.add_ledger(network, meta, len(data))
        print(f"  {network} ledger {seq}: {len(data)} bytes")


def add_transaction(collector: Collector, network: str, t: dict[str, Any]) -> None:
    """A transaction from RPC, with its result, metadata and events."""
    collector.add_xdr(network, "TransactionEnvelope", t["envelopeXdr"])
    collector.add_xdr(network, "TransactionResult", t["resultXdr"])
    collector.add_xdr(network, "TransactionMeta", t["resultMetaXdr"])
    for event in t.get("diagnosticEventsXdr", []):
        collector.add_xdr(network, "DiagnosticEvent", event)
    events = t.get("events", {})
    for event in events.get("transactionEventsXdr", []):
        collector.add_xdr(network, "TransactionEvent", event)
    for operation in events.get("contractEventsXdr", []):
        for event in operation:
            collector.add_xdr(network, "ContractEvent", event)


def from_rpc(collector: Collector, network: str, settings: dict[str, Any]) -> None:
    """Recent transactions, events and the latest ledger."""
    url: str = settings["rpc"]
    latest = rpc(url, "getLatestLedger")["sequence"]
    start = latest - 100
    cursor: str | None = None
    pages: int = settings["pages"]
    for _ in range(pages):
        params: dict[str, Any] = {"pagination": {"limit": PAGE_SIZE}}
        if cursor is None:
            params["startLedger"] = start
        else:
            params["pagination"]["cursor"] = cursor
        page = rpc(url, "getTransactions", params)
        cursor = page.get("cursor")
        transactions: list[dict[str, Any]] = page["transactions"]
        for t in transactions:
            add_transaction(collector, network, t)
    events = rpc(
        url, "getEvents", {"startLedger": start, "pagination": {"limit": PAGE_SIZE}}
    )["events"]
    for event in events:
        for topic in event["topic"]:
            collector.add_xdr(network, "SCVal", topic)
        collector.add_xdr(network, "SCVal", event["value"])
    ledger = rpc(
        url, "getLedgers", {"startLedger": latest - 5, "pagination": {"limit": 1}}
    )
    for entry in ledger["ledgers"]:
        collector.add_xdr(network, "LedgerHeaderHistoryEntry", entry["headerXdr"])
        meta = xdr.LedgerCloseMeta.from_xdr_base64(entry["metadataXdr"])
        collector.add_ledger(network, meta, len(base64.b64decode(entry["metadataXdr"])))


def check(vectors: list[dict[str, str]]) -> None:
    """Every kept value encodes back to the same bytes."""
    for v in vectors:
        codec = getattr(typedefs, v["type"], None)
        if codec is not None:
            encoded = codec.to_xdr_base64(codec.from_xdr_base64(v["xdr"]))
        else:
            encoded = getattr(xdr, v["type"]).from_xdr_base64(v["xdr"]).to_xdr_base64()
        if encoded != v["xdr"]:
            sys.exit(f"{v['type']} does not re-encode: {v['xdr'][:60]}...")


def report(vectors: list[dict[str, str]]) -> None:
    """Print how much of the definitions the vectors hold."""
    found: set[str] = set()
    for v in vectors:
        codec = getattr(typedefs, v["type"], None) or getattr(xdr, v["type"])
        coverage(codec.from_xdr_base64(v["xdr"]), found)
    arms: set[str] = set()
    for name in xdr.__all__:
        if isinstance(getattr(xdr, name), UnionNamespace):
            namespace: Any = getattr(xdr, name)
            members = typing.get_args(namespace.Any) or (namespace.Any,)
            arms |= {arm.__qualname__ for arm in members}
    structs = {
        name
        for name in xdr.__all__
        if isinstance(getattr(xdr, name), type)
        and hasattr(getattr(xdr, name), "_fields")
    }
    print(f"union arms: {len(arms & found)} of {len(arms)}")
    print(f"structs: {len(structs & found)} of {len(structs)}")
    print(f"enum members: {sum('.' in f and f not in arms for f in found)}")


def main() -> None:
    """Fetch, select, check and write the vectors."""
    collector = Collector()
    for network, settings in NETWORKS.items():
        print(f"{network}: data lake")
        from_lake(collector, network, settings)
        print(f"{network}: RPC")
        from_rpc(collector, network, settings)
    vectors = collector.select()
    check(vectors)
    data = json.dumps(vectors, indent=2).encode()
    OUTPUT.write_bytes(gzip.compress(data, mtime=0))
    sizes: dict[str, int] = {}
    for v in vectors:
        sizes[v["type"]] = sizes.get(v["type"], 0) + 1
    raw = sum(len(base64.b64decode(v["xdr"])) for v in vectors)
    print(f"{len(vectors)} values, {raw} bytes of XDR, {OUTPUT.stat().st_size} gzipped")
    for name, count in sorted(sizes.items()):
        print(f"  {name}: {count}")
    report(vectors)


if __name__ == "__main__":
    main()
