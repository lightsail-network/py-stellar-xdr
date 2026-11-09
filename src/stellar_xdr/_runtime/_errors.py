"""Errors raised for input data.

Constructing a value with a wrong argument raises a plain `TypeError` or `ValueError`,
as for any Python function, so only errors about encoded input or nesting depth have
their own classes.
"""


class XdrError(ValueError):
    """Base class of the errors raised for XDR input data."""


class XdrDecodeError(XdrError):
    """Binary or base64 input is not a valid encoding of the requested type.

    This includes input nested more deeply than `max_depth` allows.
    """


class XdrJsonError(XdrError):
    """A conversion between a value and SEP-51 XDR-JSON failed.

    Usually the JSON is not a valid representation of the requested type, including
    JSON nested more deeply than `max_depth` allows. Converting a value to JSON raises
    it for the rare valid XDR value that SEP-51 can't represent: a signed payload signer
    with an empty payload.
    """


class XdrDepthError(XdrError):
    """A value is nested more deeply than `max_depth` allows, so it is not encoded."""
