# Logos/src/logos/utils.py

"""
Internal and other helper functions.

Includes LLM-friendly YAML formatting, base36 encoding, list to tuple, and the temporal ID
system used for artifact filenames.
"""

from datetime import datetime, timezone
from typing import Any, Optional, List, Tuple, Dict, Union
import io
import re
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString, SingleQuotedScalarString, PlainScalarString


# ─── Base36 / Photo ID ───────────────────────────────────────────────

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Epoch for photo IDs: Feb 8, 1977 --- Mark's B'day
_ID_EPOCH = datetime(1977, 2, 8, tzinfo=timezone.utc)

# Module-level state for per-second sequencing
_last_second: Optional[int] = None
_seq_in_second: int = 0


def base36_encode(number: int, min_length: int = 4) -> str:
    """
    Encode a non-negative integer as a zero-padded base36 string.

    Args:
        number: The integer to encode. Must be >= 0.
        min_length: Minimum length of the returned string, left-padded
            with '0' characters.

    Returns:
        A lowercase base36 string, at least `min_length` characters long.
        Lexicographic sort == numeric sort when strings are same length.
    """
    if number < 0:
        raise ValueError("Cannot encode negative numbers")
    if number == 0:
        return "0" * min_length

    chars = []
    while number:
        chars.append(_ALPHABET[number % 36])
        number //= 36
    result = "".join(reversed(chars))
    return result.rjust(min_length, "0")


def make_time_id(prefix: str = "", now: Optional[datetime] = None) -> str:
    """
    Generate a time-based, 7-character, base36 ID with optional prefix, e.g. "sum-", "msg-"

    Format: 6 chars of seconds-since-epoch (base36) + 1 char burst sequence.
    Lexicographic sort == chronological sort, including bursts within the
    same second.

    Args:
        now: Optional datetime for testing. Defaults to UTC now.

    Returns:
        A 7-character string like "0a3f2x0".

    Note to self:
        6 base36 chars covers ~69 years from the 2025-01-01 epoch.
        The burst digit supports up to 36 captures per second before
        wrapping. More than enough for our camera cadence.
    """
    global _last_second, _seq_in_second

    if now is None:
        now = datetime.now(timezone.utc)

    delta = now - _ID_EPOCH
    second = int(delta.total_seconds())

    # Update per-second sequence counter
    if _last_second is None or second != _last_second:
        _last_second = second
        _seq_in_second = 0
    else:
        _seq_in_second = (_seq_in_second + 1) % len(_ALPHABET)

    ts_part = base36_encode(second, min_length=6)
    seq_part = _ALPHABET[_seq_in_second]

    return f"{prefix}{ts_part}{seq_part}"


# ─── LLM-Friendly YAML Formatting ────────────────────────────────────

# Tunables for "LLM-friendly" YAML formatting
_MAX_FLOW_LINE = 240      # max length for a single-line flow sequence
_BLOCK_SCALAR_MIN = 80    # Lowered: LLMs prefer | blocks for readability over long single lines

_yaml_llm = YAML()
_yaml_llm.default_flow_style = None 
_yaml_llm.width = 4096
_yaml_llm.indent(mapping=2, sequence=4, offset=2)


_RESERVED_WORDS = {
    "null", "none", "true", "false",
    "yes", "no", "on", "off",
    "y", "n", "~",
}

# Regex to detect strings that YAML would misinterpret as numbers
_RE_NUMBER = re.compile(
    r'^[+-]?(\.?[0-9]+|[0-9]+\.?[0-9]*)([eE][+-]?[0-9]+)?$'
)

def _needs_quotes(value: str) -> bool:
    """
    Decide if a scalar *must* be quoted to be valid / unambiguous YAML.
    """
    if not value:
        return True

    # 1. Reserved words/symbols
    if value.lower() in _RESERVED_WORDS:
        return True

    # 2. Starts with special characters that trigger YAML parsing
    if value[0] in "@`!|>&*%,#[]{}?-" or value[0] in "'\"":
        return True
    
    # 3. Contains characters that break plain scalars
    # We allow internal spaces! Just not colons followed by space or newlines
    if ": " in value or " #" in value:
        return True
    
    # 4. Leading/Trailing whitespace requires quotes to be preserved
    if value.strip() != value:
        return True

    # 5. Looks like a number? Quote it to keep it a string.
    if _RE_NUMBER.match(value):
        return True

    return False


def _prepare_for_llm_yaml(
    obj: Any,
    *,
    max_flow_line: int,
    block_scalar_min: int,
) -> Any:
    """
    Recursive walker that wraps Python objects in ruamel structures.
    """
    # --- mappings ---------------------------------------------------------
    if isinstance(obj, dict):
        cm = CommentedMap()
        for key, value in obj.items():
            cm[key] = _prepare_for_llm_yaml(
                value,
                max_flow_line=max_flow_line,
                block_scalar_min=block_scalar_min,
            )
        return cm

    # --- sequences --------------------------------------------------------
    if isinstance(obj, (list, tuple)):
        seq = CommentedSeq()
        for item in obj:
            seq.append(
                _prepare_for_llm_yaml(
                    item,
                    max_flow_line=max_flow_line,
                    block_scalar_min=block_scalar_min,
                )
            )

        # Heuristic: Flow style if items are scalars, no newlines, and fits width.
        # We allow spaces in items (e.g. ["file a", "file b"]).
        is_simple = all(
            isinstance(x, (str, int, float, bool)) and 
            not (isinstance(x, str) and "\n" in x)
            for x in obj
        )

        if is_simple:
            # Estimate flow length: sum of stringified items + ", " overhead + "[]"
            # Note: This is an estimate; ruamel adds quotes to some items.
            est_len = sum(len(str(x)) for x in obj) + (2 * len(obj)) + 2
            
            if est_len <= max_flow_line:
                seq.fa.set_flow_style()
            else:
                seq.fa.set_block_style()
        else:
            seq.fa.set_block_style()

        return seq

    # --- scalars ----------------------------------------------------------
    if isinstance(obj, str):
        if "\n" in obj or len(obj) >= block_scalar_min:
            return LiteralScalarString(obj)
        
        if _needs_quotes(obj):
            return SingleQuotedScalarString(obj)
        
        # Explicitly return a PlainScalarString. 
        # This tells ruamel: "We checked, this is safe to be bare."
        return PlainScalarString(obj)

    # Let ruamel handle int, float, None, etc.
    return obj

def get_box_center(box_2d: List[float]) -> Tuple[float, float]:
    """
    Calculates the [y, x] center point of a normalized 0-1000 bounding box.
    
    Args:
        box_2d: A list of 4 floats [y_min, x_min, y_max, x_max].
                If a list of 2 floats [y, x] is passed, it returns them as-is.
    
    Returns:
        A tuple of (center_y, center_x) in 0-1000 coordinates.
    """
    if len(box_2d) == 2:
        return (box_2d[0], box_2d[1])
    
    y_min, x_min, y_max, x_max = box_2d
    center_y = (y_min + y_max) / 2.0
    center_x = (x_min + x_max) / 2.0
    return (center_y, center_x)


def dump_yaml(
    data: Any,
    *,
    max_flow_line: int = _MAX_FLOW_LINE,
    block_scalar_min: int = _BLOCK_SCALAR_MIN,
) -> str:
    """Creates a token optimized YAML of Python objects for my consumption."""
    prepared = _prepare_for_llm_yaml(
        data,
        max_flow_line=max_flow_line,
        block_scalar_min=block_scalar_min,
    )
    buf = io.StringIO()
    _yaml_llm.dump(prepared, buf)
    return buf.getvalue()


def to_3tuple(
    value: Optional[Union[List[float], Tuple[float, float, float]]]
) -> Optional[Tuple[float, float, float]]:
    """List to 3 tuple of floats."""
    if value is None:
        return None

    if len(value) != 3:
        raise ValueError(f"Expected 3 values, got {len(value)}: {value}")

    return float(value[0]), float(value[1]), float(value[2])


def to_2tuple_int(
    value: Optional[Union[List[int], Tuple[int, int]]]
) -> Optional[Tuple[int, int]]:
    """List to 2 tuple of ints."""
    if value is None:
        return None

    if len(value) != 2:
        raise ValueError(f"Expected 2 values, got {len(value)}: {value}")

    return int(value[0]), int(value[1])