# py-stellar-xdr

A Python library to encode and decode [Stellar](https://stellar.org) XDR, the binary
format of transactions, ledger entries, contract values and everything else on the
Stellar network, and its
[SEP-51](https://github.com/stellar/stellar-protocol/blob/master/ecosystem/sep-0051.md)
JSON form.

- **Complete.** Every type of the network's XDR definitions, generated from them, with a
  release for each protocol version; `stellar_xdr.PROTOCOL_VERSION` says which.
- **Strict.** Binary decoding accepts only the one canonical encoding of a value.
  Constructors check their arguments, so any value that exists can be encoded as XDR.
- **Typed.** Immutable classes, unions you can `match` on, and complete type hints that
  mypy and pyright check in strict mode.
- **Thoroughly tested.** Every type and union arm is tested with random values, and the
  tests cover 100% of the branches of the code. On top of that, real data from the
  public networks decodes and encodes back unchanged, and JSON matches the reference
  implementation value for value.

!!! warning

    Releases before 1.0 may still change the API. 1.0 will come with the next major
    version of the Python Stellar SDK, which will use this package for its XDR.

## Install

```shell
pip install stellar-xdr
```

## Example

```python
import stellar_xdr as xdr

value = xdr.SCVal.Vec([xdr.SCVal.Symbol("transfer"), xdr.SCVal.U32(7)])
encoded = value.to_xdr_base64()
assert xdr.SCVal.from_xdr_base64(encoded) == value
assert value.to_json_value() == {"vec": [{"symbol": "transfer"}, {"u32": 7}]}
```

The [guide](guide.md) explains values, unions, decoding, errors and JSON. The
[API reference](api/index.md) lists every type, grouped by the `.x` file that defines it.
