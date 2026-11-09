# Security policy

## Supported versions

Security fixes are released for the latest version only. Upgrade to it before reporting
an issue.

## Reporting a vulnerability

Please report vulnerabilities privately, not in a public issue:

- Preferably through
  [GitHub's private vulnerability reporting](https://github.com/lightsail-network/py-stellar-xdr/security/advisories/new).
- Or by email to hi@overcat.dev. For GPG, see https://keybase.io/overcat.

Include the version, a minimal reproduction and what you think the impact is. Don't
include real secret seeds or other private data.

## Scope

Examples of what counts as a vulnerability:

- Input that doesn't conform to the XDR definitions or to SEP-51 being accepted, or
  valid input being decoded to the wrong value.
- A value that encodes differently from how it was decoded.
- Input that makes decoding take much more time or memory than its length justifies.
- Input that makes decoding raise anything other than the library's documented errors,
  such as `RecursionError` or `MemoryError`.
