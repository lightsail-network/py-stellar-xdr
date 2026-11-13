# Guide

Every type of the network's XDR definitions is importable from `stellar_xdr`, under the
name it has in the `.x` files: `SCVal`, `TransactionEnvelope`, `LedgerEntry`. Import
types from there only. The modules behind it are private, because a definition can move
from one `.x` file to another between releases.

Two kinds of types get a name that the `.x` files don't spell out:

- A struct or union defined inside another type is named after that type and its own
  field: the `ext` of an `AccountEntry` is an `AccountEntryExt`, and the `result` of a
  `TransactionResult` is a `TransactionResultResult`.
- A typedef that starts with a lower-case letter is capitalized: `uint32` is `Uint32`.

The package's version follows semantic versioning of its API. The protocol version of
its definitions is `stellar_xdr.PROTOCOL_VERSION`:

```python
import stellar_xdr as xdr

assert xdr.PROTOCOL_VERSION >= 30
```

## Structs

A struct is a class with one field per XDR field, in snake case. Fields can be given by
position, in XDR order, or by keyword:

```python
import stellar_xdr as xdr

parts = xdr.UInt128Parts(hi=0, lo=100)
assert parts == xdr.UInt128Parts(0, 100)
assert repr(parts) == "UInt128Parts(hi=0, lo=100)"
```

Constructors check their arguments, so that any value that exists can be encoded. A value
of the wrong type raises `TypeError`, and a value XDR can't hold raises `ValueError`:

```python
import stellar_xdr as xdr

try:
    xdr.UInt128Parts(hi=-1, lo=0)
except ValueError as error:
    message = str(error)
assert message == "UInt128Parts.hi: -1 is out of range for uint64"

try:
    xdr.UInt128Parts(hi="1", lo=0)
except TypeError as error:
    message = str(error)
assert message == "UInt128Parts.hi: expected int, got str"
```

Some arguments are converted on the way in:

- Arrays accept any sequence, such as a list, and are stored as tuples. Strings and
  bytes are not sequences of XDR values and are rejected.
- XDR strings, such as `SCVal.Symbol` and `Memo.Text`, accept `str`, which is encoded
  as UTF-8, and are stored as `bytes`, since an XDR string can hold any bytes.
- A field of a [typedef](#typedefs), such as a `Hash`, accepts the plain value, here
  `bytes`, and stores it as a `Hash`.
- Enum fields need a member of the enum, not a plain integer.

```python
import stellar_xdr as xdr

memo = xdr.Memo.Text("coffee")
assert memo.text == b"coffee"

symbols = xdr.SCVal.Vec([xdr.SCVal.Symbol("a"), xdr.SCVal.Symbol("b")])
assert symbols.vec == (xdr.SCVal.Symbol("a"), xdr.SCVal.Symbol("b"))
```

Values are immutable. To change a field, make a copy with `replace`, which checks the
new value like a constructor. On Python 3.13 and later, `copy.replace` does the same.

```python
import stellar_xdr as xdr

parts = xdr.UInt128Parts(0, 100)
more = xdr.replace(parts, lo=200)
assert (parts.lo, more.lo) == (100, 200)
```

To change a field of a nested value, replace from the inside out. Each `replace` copies
one level, and the copy shares every value that didn't change:

```python
import stellar_xdr as xdr

data = xdr.SorobanTransactionData(
    ext=xdr.SorobanTransactionDataExt.V0(),
    resources=xdr.SorobanResources(
        footprint=xdr.LedgerFootprint(read_only=[], read_write=[]),
        instructions=100_000,
        disk_read_bytes=0,
        write_bytes=0,
    ),
    resource_fee=5_000,
)
raised = xdr.replace(
    data,
    resources=xdr.replace(data.resources, instructions=150_000),
    resource_fee=7_500,
)
assert raised.resources.instructions == 150_000
assert raised.resources.footprint is data.resources.footprint
assert data.resources.instructions == 100_000
```

Values compare by type and fields, can be hashed, and can be pickled and copied. A
pickle only works within one version of the package, since names and the order of fields
can change between versions: to store values or send them elsewhere, use XDR or JSON.

!!! note

    Type checkers treat these classes as frozen dataclasses, but they aren't
    dataclasses: `dataclasses.replace`, `dataclasses.fields` and `dataclasses.asdict`
    don't work on them. Use `replace` or `copy.replace` instead, and `to_json_value`
    for a dictionary. Being plain classes makes importing the package several times
    faster.

## Unions

A union, such as `SCVal`, groups one class per arm: `SCVal.U32`, `SCVal.Symbol`,
`SCVal.Vec`. An arm holds the arm's value, if it has one, in a field named as in the
XDR definition. Since it holds one value at most, an arm is written, and shown, with the
value alone:

```python
import stellar_xdr as xdr

value = xdr.SCVal.U32(7)
assert value.u32 == 7
assert repr(value) == "SCVal.U32(7)"
assert repr(xdr.SCVal.Void()) == "SCVal.Void()"
```

`match` tells the arms apart:

```python
import stellar_xdr as xdr


def describe(value: xdr.SCVal.Any) -> str:
    match value:
        case xdr.SCVal.U32(number):
            return f"u32 {number}"
        case xdr.SCVal.Symbol(symbol):
            return f"symbol {symbol.decode()}"
        case xdr.SCVal.Vec(items):
            return f"vector of {len(items or ())}"
        case xdr.SCVal.Void():
            return "void"
        case _:
            return "something else"


assert describe(xdr.SCVal.U32(7)) == "u32 7"
assert describe(xdr.SCVal.Symbol("transfer")) == "symbol transfer"
assert describe(xdr.SCVal.Vec([xdr.SCVal.Void()])) == "vector of 1"
assert describe(xdr.SCVal.Void()) == "void"
```

`SCVal.Any` is the union of the arm classes: use it in annotations and with
`isinstance`. `SCVal` itself is not a type, so `isinstance(value, xdr.SCVal)` raises
`TypeError` rather than always returning `False`, and so do `xdr.SCVal()` and the
pattern `case xdr.SCVal():`.

```python
import stellar_xdr as xdr

value = xdr.SCVal.U32(7)
assert isinstance(value, xdr.SCVal.Any)
assert isinstance(value, xdr.SCVal.U32)
```

Each arm also has its discriminant as a class attribute, named as in XDR: `type` for
`SCVal`, `v` for the extension unions, `code` for results. Type checkers narrow the
value when you compare it.

```python
import stellar_xdr as xdr

value = xdr.SCVal.U32(7)
assert value.type is xdr.SCValType.SCV_U32
assert xdr.TransactionExt.V0().v == 0
```

Arms are named after their case in the discriminant's enum, without the prefix its
members share: `SCV_U32` is `SCVal.U32` and `ASSET_TYPE_CREDIT_ALPHANUM4` is
`Asset.CreditAlphanum4`. Unions that switch on an integer, such as the `ext` unions,
name their arms after the value: `TransactionExt.V0`.

## Enums

Enums are `IntEnum` classes whose members keep their names from the `.x` files:

```python
import stellar_xdr as xdr

assert xdr.SCValType.SCV_U32 == 3
assert xdr.SCValType(3) is xdr.SCValType.SCV_U32
assert repr(xdr.SCValType.SCV_U32) == "SCValType.SCV_U32"
```

## Typedefs

A typedef is a class that extends the Python type of its values: `bytes` for opaque
data and strings, `int` for integers, `tuple` for arrays. A `Hash` is a `bytes`, a
`SequenceNumber` is an `int` and an `SCVec` is a `tuple`, and each can be used as one:

```python
import stellar_xdr as xdr

key = xdr.Hash(bytes(32))
assert key == bytes(32)
assert key.hex() == "00" * 32

items = xdr.SCVec([xdr.SCVal.U32(1), xdr.SCVal.Void()])
assert len(items) == 2
assert items[0] == xdr.SCVal.U32(1)

assert xdr.SequenceNumber(5) + 1 == 6
```

The class checks the value, and gives it the methods every type has:

```python
import stellar_xdr as xdr

try:
    xdr.Hash(b"too short")
except ValueError as error:
    message = str(error)
assert message == "Hash: expected 32 bytes, got 9"

changes = xdr.LedgerEntryChanges.from_xdr_base64("AAAAAA==")
assert changes == ()
assert xdr.SCVec([xdr.SCVal.Void()]).to_xdr_base64() == "AAAAAQAAAAE="
```

A constructor takes the plain value and stores it as the type of its field. The value
then knows how it is written: a `ContractID` and a `PoolID` are both 32 bytes, but one
is a `C...` address in JSON and the other an `L...`.

```python
import stellar_xdr as xdr

address = xdr.SCAddress.Contract(bytes(32))
assert type(address.contract_id) is xdr.ContractID
assert address.contract_id.to_json_value() == (
    "CAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABSC4"
)
assert repr(address.contract_id) == f"ContractID({bytes(32)!r})"
```

What an operation on a value returns is a plain value again: `key[:4]` is a `bytes` and
`number + 1` an `int`. Pass it to a constructor like any other plain value.

Three kinds of typedef are not classes of their own, but other names:

- `Uint32`, `Int32`, `Uint64` and `Int64` are `int`. Every integer field would
  otherwise hold an object of its own.
- A typedef of a union is the union: `AccountID` and `NodeID` are `PublicKey`, with its
  arms and its decoding. Annotate with `AccountID.Any`.
- `SponsorshipDescriptor` is an optional account ID, and `None` can't be a value of a
  class of its own.

```python
import stellar_xdr as xdr

assert xdr.Uint32 is int
assert xdr.AccountID is xdr.PublicKey

account: xdr.AccountID.Any = xdr.AccountID.Ed25519(bytes(32))
assert xdr.AccountID.from_xdr_bytes(account.to_xdr_bytes()) == account
```

## Encoding and decoding

Every value encodes to bytes or to base64, the form Stellar's APIs use:

```python
import stellar_xdr as xdr

value = xdr.SCVal.U64(1)
assert value.to_xdr_bytes() == bytes.fromhex("000000050000000000000001")
assert value.to_xdr_base64() == "AAAABQAAAAAAAAAB"
```

Decoding starts from the type: a struct's class, an enum, a typedef, or a union such
as `SCVal`, which returns the arm the data holds.

```python
import stellar_xdr as xdr

assert xdr.SCVal.from_xdr_base64("AAAABQAAAAAAAAAB") == xdr.SCVal.U64(1)
assert xdr.UInt128Parts.from_xdr_bytes(bytes(15) + b"\x01") == xdr.UInt128Parts(0, 1)
```

Decoding is strict. Anything other than the canonical encoding of a value raises
`XdrDecodeError`, which says what is wrong and where:

- an enum value or union discriminant that the definitions don't have;
- a boolean or optional flag other than 0 or 1;
- padding that is not zero;
- an array, string or opaque value longer than its maximum, or than the rest of the
  input;
- bytes left after the value;
- base64 that is not canonical, padded standard base64.

```python
import stellar_xdr as xdr

try:
    xdr.SCVal.from_xdr_bytes(bytes.fromhex("00000063"))
except xdr.XdrDecodeError as error:
    message = str(error)
assert message == "unknown SCVal discriminant 99 at offset 0"
```

### Depth

Recursive types, such as `SCVal`, can nest without limit in XDR. Decoding and encoding
stop at 200 levels of such types by default, which is above what the network accepts.
Pass `max_depth` to change the limit. Going over it raises `XdrDepthError`, whether a
value is being decoded, encoded or converted to or from JSON:

```python
import stellar_xdr as xdr

nested = xdr.SCVal.Vec([xdr.SCVal.Vec([xdr.SCVal.Void()])])
data = nested.to_xdr_bytes()
try:
    xdr.SCVal.from_xdr_bytes(data, max_depth=2)
except xdr.XdrDepthError as error:
    message = str(error)
assert message.startswith("nesting deeper than max_depth=2")
```

Input that is too deep may be valid XDR otherwise, so `XdrDepthError` is not an
`XdrDecodeError`, nor an `XdrJsonError`. Every error derives from `XdrError`: catch that
one to reject untrusted input, whatever is wrong with it.

```python
import stellar_xdr as xdr


def parse(data: bytes) -> xdr.SCVal.Any | None:
    try:
        return xdr.SCVal.from_xdr_bytes(data)
    except xdr.XdrError:
        return None


deep: xdr.SCVal.Any = xdr.SCVal.Void()
for _ in range(300):
    deep = xdr.SCVal.Vec([deep])

assert parse(deep.to_xdr_bytes(max_depth=400)) is None
assert parse(b"not XDR") is None
assert parse(xdr.SCVal.Void().to_xdr_bytes()) == xdr.SCVal.Void()
```

Equality, hashing, `repr` and pickling recurse without such a limit.

### Streams

`decode_stream` reads values of one type written back to back, with no count in front and
nothing between them, and `encode_stream` writes values that way. The custom sections of a
Soroban contract's Wasm file, such as its metadata (SEP-46) and its interface spec (SEP-48),
are stored like this. Files that put a length before each value, such as those in history
archives, are not.

```python
import stellar_xdr as xdr

entries = [
    xdr.SCMetaEntry.V0(xdr.SCMetaV0("rsver", "1.80.0")),
    xdr.SCMetaEntry.V0(xdr.SCMetaV0("rssdkver", "22.0.0")),
]
data = xdr.encode_stream(entries)
assert list(xdr.decode_stream(xdr.SCMetaEntry, data)) == entries
```

## JSON

`to_json_value` converts a value to [SEP-51](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0051.md)
XDR-JSON, as the JSON value `json.dumps` takes, and `from_json_value` converts back from
what `json.loads` returns:

```python
import json

import stellar_xdr as xdr

value = xdr.SCVal.Map(
    [
        xdr.SCMapEntry(
            xdr.SCVal.Symbol("amount"), xdr.SCVal.I128(xdr.Int128Parts(0, 100))
        )
    ]
)
text = json.dumps(value.to_json_value())
assert text == '{"map": [{"key": {"symbol": "amount"}, "val": {"i128": "100"}}]}'
assert xdr.SCVal.from_json_value(json.loads(text)) == value
```

SEP-51 writes:

- structs as objects, and unions as `{"arm": value}`, or as the arm's name when it holds
  no value;
- enums as names, such as `"u32"`;
- 64-bit integers, and the 128 and 256-bit integers of contract values, as strings of
  digits;
- opaque data as hex;
- strings as ASCII, with every other byte escaped, such as `"\\xc3\\xa9"` for `é`;
- accounts, contracts and other addresses as strkeys, such as `G...`.

Reading is strict: anything else, including integer strings that are not canonical such
as `"+5"`, `"007"` and `"-0"`, raises `XdrJsonError`, which names the type and field.
Unlike binary XDR, a value has more than one accepted JSON form, and `to_json_value`
always writes the same one. It also accepts what SEP-51 allows on input: a `$schema` key in any
object, numbers for 64-bit integers, and text outside ASCII as it is. Like the reference
implementation, it accepts `{"arm": null}` for an arm without a value, and reads an
optional field that is left out as null.

```python
import stellar_xdr as xdr

account = xdr.MuxedAccount.Ed25519(bytes(32))
assert account.to_json_value() == (
    "GAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWHF"
)
assert xdr.SCVal.from_json_value({"string": "café"}) == xdr.SCVal.String("café")

try:
    xdr.SCVal.from_json_value({"u32": "5"})
except xdr.XdrJsonError as error:
    message = str(error)
assert message == "SCVal.U32.u32: expected an integer, got a string"
```

A signed payload signer with an empty payload is valid XDR but has no strkey, so
`to_json_value` raises `XdrJsonError` for it.
