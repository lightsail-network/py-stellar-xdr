# Test vectors

The tests check the package against data it didn't produce itself. These files hold that
data. None of them is written by hand: a script in `scripts/` makes each one, and its
docstring has the details.

| File | Contents | Made by | Used by |
|---|---|---|---|
| `network_values.json.gz` | About 500 values from mainnet and testnet: ledgers, envelopes, results, fee changes, transaction metadata, events, ledger entries and contract values. They are picked from ledgers sampled across each network's whole history and from recent transactions, so that together they hold as many types, arms and enum members as possible. | `python scripts/fetch_network_vectors.py`, which only reads from the public ledger data lake on AWS and from public RPC servers, and keeps a value only if it decodes and encodes back to the same bytes. | `test_network.py` |
| `xdr_json_values.json.gz` | About 3,900 values with their XDR-JSON: the network values, and a few random values of every type. | `python scripts/make_json_vectors.py PATH_TO_CLI`, which converts each value with the reference implementation's `stellar-xdr` CLI. The random values are drawn with a fixed seed, so running it again writes the same file. | `test_json_vectors.py` |
| `xdr_json_names.json` | The SEP-51 names of every enum member, union arm and struct field. | `python scripts/make_json_names.py PATH_TO_CHECKOUT`, which reads the reference implementation's JSON schemas. | `test_generator.py` |

The reference implementation is [rs-stellar-xdr](https://github.com/stellar/rs-stellar-xdr),
at the commit in `xdr/source.toml`. `make_json_names.py` reads a checkout of it, and
`make_json_vectors.py` runs its CLI, built in that checkout with
`cargo build --features cli`.

Where the reference implementation differs from SEP-51, `make_json_vectors.py` records
what SEP-51 specifies, keeps the reference output next to it, and `test_json_vectors.py`
checks that only the known differences were changed. The only one is that v30.0.0
writes inline fixed-length opaque fields as arrays of integers instead of hex
([stellar/rs-stellar-xdr#618](https://github.com/stellar/rs-stellar-xdr/issues/618)).
Once a release fixes it, the normalization can go.

## After updating `xdr/xdr.json`

Run `make update-xdr` and `make generate` first, then:

1. `make_json_names.py`, since new or renamed definitions have new names.
2. `make_json_vectors.py`, so that new types have vectors too. It also takes the network
   values, so if you refresh those, do that first:
3. `fetch_network_vectors.py`, once the networks run the new protocol, so that real data
   covers the new types. Until then, the old values still apply. It needs Python 3.14,
   for zstd, and takes a few minutes.

Then run `make check`.

Real data can't hold everything. The data lake rebuilds old ledgers with a recent
stellar-core, so transaction metadata is only in its current format, and some types never
reach a ledger at all, such as the messages between nodes or the results of transactions
that were rejected. The random values of `test_roundtrip.py` cover every type and arm.
