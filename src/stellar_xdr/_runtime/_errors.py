"""Errors raised by decoding, encoding and the JSON conversions.

There is one class per cause, whichever method runs into it: input that is not valid
XDR, JSON that is not valid XDR-JSON, and nesting beyond `max_depth`. Constructing a
value with a wrong argument raises a plain `TypeError` or `ValueError`, as for any
Python function.
"""


class XdrError(ValueError):
    """Base class of the errors raised when decoding, encoding or converting JSON."""


class XdrDecodeError(XdrError):
    """Binary or base64 input is not a valid encoding of the requested type."""


class XdrJsonError(XdrError):
    """A conversion between a value and SEP-51 XDR-JSON failed.

    Usually the JSON is not a valid representation of the requested type. Converting a
    value to JSON raises it for the rare valid XDR value that SEP-51 can't represent: a
    signed payload signer with an empty payload.
    """


class XdrDepthError(XdrError):
    """A value, or the input for one, is nested more deeply than `max_depth` allows.

    Decoding, encoding and both JSON conversions raise it. It says nothing else about
    the input: binary or JSON input that is too deep is not an `XdrDecodeError` or an
    `XdrJsonError`, so catch `XdrError` to reject untrusted input of any kind.
    """
