# API reference

Everything is importable from `stellar_xdr`. The types are also importable from the
module of their `.x` file, and each page below lists one of them.

Every struct, enum and union arm has `to_xdr_bytes`, `to_xdr_base64` and
`to_json_value`; every struct, enum and union has `from_xdr_bytes`, `from_xdr_base64`
and `from_json_value`. They are documented once, [below](#methods-of-every-type).

## Types

- [`stellar_xdr.scp`](scp.md): `Stellar-SCP.x`
- [`stellar_xdr.contract_config_setting`](contract_config_setting.md): `Stellar-contract-config-setting.x`
- [`stellar_xdr.contract_env_meta`](contract_env_meta.md): `Stellar-contract-env-meta.x`
- [`stellar_xdr.contract_meta`](contract_meta.md): `Stellar-contract-meta.x`
- [`stellar_xdr.contract_spec`](contract_spec.md): `Stellar-contract-spec.x`
- [`stellar_xdr.contract`](contract.md): `Stellar-contract.x`
- [`stellar_xdr.exporter`](exporter.md): `Stellar-exporter.x`
- [`stellar_xdr.internal`](internal.md): `Stellar-internal.x`
- [`stellar_xdr.ledger_entries`](ledger_entries.md): `Stellar-ledger-entries.x`
- [`stellar_xdr.ledger`](ledger.md): `Stellar-ledger.x`
- [`stellar_xdr.overlay`](overlay.md): `Stellar-overlay.x`
- [`stellar_xdr.transaction`](transaction.md): `Stellar-transaction.x`
- [`stellar_xdr.types`](types.md): `Stellar-types.x`
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
