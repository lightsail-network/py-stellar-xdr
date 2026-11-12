# API reference

Everything is importable from `stellar_xdr`, and that is the only place to import a type
from. The pages below group the types by the `.x` file that defines them, to make them
easier to find: the file is not part of a type's import path, and a definition can move
to another file between releases.

Every struct, enum and union arm has `to_xdr_bytes`, `to_xdr_base64` and
`to_json_value`; every struct, enum and union has `from_xdr_bytes`, `from_xdr_base64`
and `from_json_value`. They are documented once, [below](#methods-of-every-type).

## Types

- [`Stellar-SCP.x`](scp.md)
- [`Stellar-contract-config-setting.x`](contract_config_setting.md)
- [`Stellar-contract-env-meta.x`](contract_env_meta.md)
- [`Stellar-contract-meta.x`](contract_meta.md)
- [`Stellar-contract-spec.x`](contract_spec.md)
- [`Stellar-contract.x`](contract.md)
- [`Stellar-exporter.x`](exporter.md)
- [`Stellar-internal.x`](internal.md)
- [`Stellar-ledger-entries.x`](ledger_entries.md)
- [`Stellar-ledger.x`](ledger.md)
- [`Stellar-overlay.x`](overlay.md)
- [`Stellar-transaction.x`](transaction.md)
- [`Stellar-types.x`](types.md)
- [`stellar_xdr.typedefs`](typedefs.md): the codecs of the typedefs

## Methods of every type

A union's decoding methods, such as `SCVal.from_xdr_bytes`, return the union's `Any`.

::: stellar_xdr.UInt128Parts
    options:
      inherited_members: true
      members:
        - to_xdr_bytes
        - to_xdr_base64
        - to_json_value
        - from_xdr_bytes
        - from_xdr_base64
        - from_json_value
      show_root_heading: true
      show_root_full_path: true

## Functions

::: stellar_xdr.replace

::: stellar_xdr.decode_stream

::: stellar_xdr.encode_stream

## Errors

::: stellar_xdr.XdrError

::: stellar_xdr.XdrDecodeError

::: stellar_xdr.XdrJsonError

::: stellar_xdr.XdrDepthError
