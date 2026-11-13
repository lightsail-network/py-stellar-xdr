# API reference

Everything is importable from `stellar_xdr`, and that is the only place to import a type
from. The pages below group the types by the `.x` file that defines them, to make them
easier to find: the file is not part of a type's import path, and a definition can move
to another file between releases.

Every struct, enum, typedef and union arm has `to_xdr_bytes`, `to_xdr_base64` and
`to_json_value`; every struct, enum, typedef and union has `from_xdr_bytes`,
`from_xdr_base64` and `from_json_value`. They are documented once, on the
[base classes](#base-classes).

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

## Base classes

Every generated class extends one of these. They are for annotations and `isinstance`,
in code that handles values of more than one type; see the
[guide](../guide.md#values-of-any-type).

::: stellar_xdr.XdrValue
    options:
      members:
        - to_xdr_bytes
        - to_xdr_base64
        - to_json_value

A union's decoding methods, such as `SCVal.from_xdr_bytes`, are those of a struct, and
return the union's `Any`. A typedef's are those of a struct too.

::: stellar_xdr.XdrStruct
    options:
      members:
        - from_xdr_bytes
        - from_xdr_base64
        - from_json_value

::: stellar_xdr.XdrArm
    options:
      members: false

::: stellar_xdr.XdrEnum
    options:
      members:
        - from_xdr_bytes
        - from_xdr_base64
        - from_json_value

::: stellar_xdr.XdrBytes
    options:
      members: false

::: stellar_xdr.XdrInt
    options:
      members: false

::: stellar_xdr.XdrArray
    options:
      members: false

## Functions

::: stellar_xdr.replace

::: stellar_xdr.decode_stream

::: stellar_xdr.encode_stream

## Errors

::: stellar_xdr.XdrError

::: stellar_xdr.XdrDecodeError

::: stellar_xdr.XdrJsonError

::: stellar_xdr.XdrDepthError
