"""The types SEP-51 writes in a form of their own, rather than as structs and unions.

Addresses and keys become strkeys, 128 and 256-bit integers one integer string, and
asset codes a string. Each rule here names the runtime functions in `xdr_json` that
do the conversion; the generator emits the calls.
"""

from typing import Final

# Typedefs: (to JSON, from JSON).
TYPEDEFS: Final = {
    "ContractID": ("contract", "read_contract"),
    "PoolID": ("liquidity_pool", "read_liquidity_pool"),
    "AssetCode4": ("asset_code4", "read_asset_code4"),
    "AssetCode12": ("asset_code12", "read_asset_code12"),
}

# Structs: (to JSON, the fields it takes, from JSON, the fields it returns).
STRUCTS: Final = {
    "Int128Parts": ("join128", ("hi", "lo"), "int128", ("hi", "lo")),
    "UInt128Parts": ("join128", ("hi", "lo"), "uint128", ("hi", "lo")),
    "Int256Parts": (
        "join256",
        ("hi_hi", "hi_lo", "lo_hi", "lo_lo"),
        "int256",
        ("hi_hi", "hi_lo", "lo_hi", "lo_lo"),
    ),
    "UInt256Parts": (
        "join256",
        ("hi_hi", "hi_lo", "lo_hi", "lo_lo"),
        "uint256",
        ("hi_hi", "hi_lo", "lo_hi", "lo_lo"),
    ),
    "MuxedAccountMed25519": (
        "muxed_account",
        ("ed25519", "id"),
        "read_muxed_account",
        ("ed25519", "id"),
    ),
    "MuxedEd25519Account": (
        "muxed_account",
        ("ed25519", "id"),
        "read_muxed_account",
        ("ed25519", "id"),
    ),
    "MuxedContract": (
        "muxed_contract",
        ("contract_id", "id"),
        "read_muxed_contract",
        ("contract_id", "id"),
    ),
    "SignerKeyEd25519SignedPayload": (
        "signed_payload",
        ("ed25519", "payload"),
        "read_signed_payload",
        ("ed25519", "payload"),
    ),
}

# Unions written as the bare value of their arm, a string, instead of an object
# keyed by the arm. Their arms are told apart by the kind of strkey (or, for
# AssetCode, by the length).
TRANSPARENT_UNIONS: Final = frozenset(
    {
        "PublicKey",
        "ClaimableBalanceID",
        "MuxedAccount",
        "SCAddress",
        "SignerKey",
        "AssetCode",
    }
)

# Arms whose payload is plain bytes that become a strkey: (union, arm) -> to JSON.
ARMS: Final = {
    ("PublicKey", "Ed25519"): "account",
    ("MuxedAccount", "Ed25519"): "account",
    ("ClaimableBalanceID", "V0"): "claimable_balance",
    ("SignerKey", "Ed25519"): "account",
    ("SignerKey", "PreAuthTx"): "pre_auth_tx",
    ("SignerKey", "HashX"): "hash_x",
}

# Reading a transparent union: for each kind of strkey, the arm it becomes and how its
# payload is built. A payload is either an attribute of the parsed strkey, or a
# struct or arm built from such attributes: (class, {field: payload}).
Payload = str | tuple[str, dict[str, "Payload"]]

STRKEY_ARMS: Final[dict[str, list[tuple[str, str, str, Payload]]]] = {
    "PublicKey": [("Ed25519PublicKey", "Ed25519", "ed25519", "key")],
    "ClaimableBalanceID": [("ClaimableBalance", "V0", "v0", "hash")],
    "MuxedAccount": [
        ("Ed25519PublicKey", "Ed25519", "ed25519", "key"),
        (
            "MuxedEd25519Account",
            "MuxedEd25519",
            "med25519",
            ("MuxedAccountMed25519", {"id": "id", "ed25519": "key"}),
        ),
    ],
    "SignerKey": [
        ("Ed25519PublicKey", "Ed25519", "ed25519", "key"),
        ("PreAuthTx", "PreAuthTx", "pre_auth_tx", "hash"),
        ("HashX", "HashX", "hash_x", "hash"),
        (
            "Ed25519SignedPayload",
            "Ed25519SignedPayload",
            "ed25519_signed_payload",
            ("SignerKeyEd25519SignedPayload", {"ed25519": "key", "payload": "payload"}),
        ),
    ],
    "SCAddress": [
        (
            "Ed25519PublicKey",
            "Account",
            "account_id",
            ("PublicKey.Ed25519", {"ed25519": "key"}),
        ),
        ("Contract", "Contract", "contract_id", "hash"),
        (
            "MuxedEd25519Account",
            "MuxedAccount",
            "muxed_account",
            ("MuxedEd25519Account", {"id": "id", "ed25519": "key"}),
        ),
        (
            "ClaimableBalance",
            "ClaimableBalance",
            "claimable_balance_id",
            ("ClaimableBalanceID.V0", {"v0": "hash"}),
        ),
        ("LiquidityPool", "LiquidityPool", "liquidity_pool_id", "hash"),
        (
            "MuxedContract",
            "MuxedContract",
            "muxed_contract",
            ("MuxedContract", {"id": "id", "contract_id": "hash"}),
        ),
    ],
}
