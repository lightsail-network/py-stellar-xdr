# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/lightsail-network/py-stellar-xdr/compare/v0.1.0...v0.2.0) - 2026-11-13

This release settles much of the API before 1.0, so most of it changes code written for
0.1.0: each breaking change says what to do instead. The XDR definitions are still those
of protocol 30, and the JSON form of every value is unchanged.

### Breaking Changes

- Import every type from `stellar_xdr`. The modules of the `.x` files are private, such
  as `stellar_xdr._contract`, since upstream moves definitions between files ([#1](https://github.com/lightsail-network/py-stellar-xdr/pull/1))
- A typedef is a class that extends the type of its values: `Hash` and `ContractID`
  extend `bytes`, `SequenceNumber` extends `int`, `SCVec` extends `tuple`. Its values have
  the methods of every type, so `stellar_xdr.typedefs` is gone: call
  `xdr.LedgerEntryChanges.from_xdr_base64(...)` instead. Constructors still take the
  plain value, but a field of a typedef holds an instance of its class, so
  `type(value) is bytes` no longer holds for it; `isinstance` does ([#10](https://github.com/lightsail-network/py-stellar-xdr/pull/10))
- `AccountID` and `NodeID` are `PublicKey` itself, with its arms and its decoding.
  Annotate with `AccountID.Any` ([#10](https://github.com/lightsail-network/py-stellar-xdr/pull/10))
- `Uint32`, `Int32`, `Uint64` and `Int64` are type aliases, for annotations only: as other
  names for `int` they converted values, and `Uint32(1.9)` was `1`. Drop wrappers such as
  `Uint32(x)`, since a field takes the `int` itself. `typing.get_type_hints` gives the
  alias, whose `__value__` is `int`. On Python 3.11 the package now requires
  `typing-extensions` ([#15](https://github.com/lightsail-network/py-stellar-xdr/pull/15))
- Class names spell these words as the XDR type names do: `ID`, `IP`, `SCP`, `TTL`,
  `UDT`, `AlphaNum4`, `AlphaNum12`, `QuorumSet`, `TimePoint` and `TrustLine`. This
  renames 33 arm classes, such as `Asset.CreditAlphanum4` to `Asset.CreditAlphaNum4`,
  `LedgerKey.Ttl` to `LedgerKey.TTL`, `Memo.Id` to `Memo.ID` and `SCVal.Timepoint` to
  `SCVal.TimePoint`, and five types: `LedgerKeyTtl`, `PeerAddressIp` and the three
  `HashIDPreimage...Id` structs now end in `TTL`, `IP` and `ID` ([#12](https://github.com/lightsail-network/py-stellar-xdr/pull/12))
- Input nested more deeply than `max_depth` raises `XdrDepthError` when it is decoded
  from XDR or JSON too, not `XdrDecodeError` or `XdrJsonError`. Catch `XdrError` to
  reject untrusted input of any kind
- `decode_stream` takes the type by position only: `decode_stream(SCSpecEntry, data)`
  ([#11](https://github.com/lightsail-network/py-stellar-xdr/pull/11))
- Assigning to or deleting a field raises `AttributeError`, no longer its subclass
  `dataclasses.FrozenInstanceError`
- `stellar-strkey` 0.2 is required

### Features

- `stellar_xdr` exports the base classes of the generated types, for annotations and
  `isinstance` in code that handles values of more than one type: `XdrValue`, which
  every value is, and `XdrStruct`, `XdrArm`, `XdrEnum`, `XdrBytes`, `XdrInt` and
  `XdrArray`. The names of the fields of a struct or an arm are its class's
  `__match_args__`
- `encode_stream` encodes typedef values too, such as a `Hash`, and `decode_stream` takes
  a typedef class, such as `xdr.Hash` ([#10](https://github.com/lightsail-network/py-stellar-xdr/pull/10))
- A value is shown the way it is written: an arm with its value alone,
  `SCVal.U32(5)`, and an enum member by its name, `SCValType.SCV_U32`
- The guide explains how types are named, how to replace a field of a nested value and
  how to handle values of any type, and the API reference lists every typedef

### Bug Fixes

- Reading hex from JSON rejects a string longer than its type allows before reading it:
  hex for a million bytes, given for a 32-byte `Hash`, took about 117 MB before
- `replace` and `decode_stream` raise `TypeError` for an argument that isn't a value or a
  type of the package, rather than `AttributeError`
- The tests in the source distribution run: it shipped the code generator's tests
  without the generator, so pytest stopped while collecting them

Changes to the code generator, the tests and CI are left out; the comparison linked
above has every commit.

## [0.1.0](https://github.com/lightsail-network/py-stellar-xdr/releases/tag/v0.1.0) - 2026-11-10

### Features

- Add stellar-xdr, a typed library for the Stellar XDR of protocol 30, with binary XDR and SEP-51 XDR-JSON
