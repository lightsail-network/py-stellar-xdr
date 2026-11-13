"""The integers of XDR: the range of each, and what an error says of one outside it.

A constructor and the reading of JSON both check an integer against the range of its
type, and each raises an error of its own. What they check against, and what they say,
is here.
"""

from typing import Final

Bounds = tuple[int, int]
"""The lowest and the highest value of a type."""

INT32: Final[Bounds] = (-(2**31), 2**31 - 1)
UINT32: Final[Bounds] = (0, 2**32 - 1)
INT64: Final[Bounds] = (-(2**63), 2**63 - 1)
UINT64: Final[Bounds] = (0, 2**64 - 1)

# str() of an int with more than 4,300 digits raises ValueError, so a message only
# quotes an integer that is no longer than the longest XDR-JSON one, of 256 bits.
_MAX_SHOWN_BITS: Final = 256


def show(value: int) -> str:
    """Quote an integer in a message, which stays short whatever the integer."""
    return str(value) if value.bit_length() <= _MAX_SHOWN_BITS else "a huge number"


def out_of_range(value: int, name: str) -> str:
    """What an error says of an integer outside the range of its type."""
    return f"{show(value)} is out of range for {name}"
