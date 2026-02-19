# Logos/src/logos/utils.py

"""
Internal (hidden) and other helper functions.

Includes LLM-friendly YAML formatting, base36 encoding, and the photo ID
system used by the vision module for artifact filenames.
"""

from datetime import datetime, timezone
from typing import Any, Optional
import io

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString, SingleQuotedScalarString


# ─── Base36 / Photo ID ───────────────────────────────────────────────

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"

# Epoch for photo IDs: 2025-01-01 UTC
PHOTO_ID_EPOCH = datetime(2025, 1, 1, tzinfo=timezone.utc)

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
        chars.append(ALPHABET[number % 36])
        number //= 36
    result = "".join(reversed(chars))
    return result.rjust(min_length, "0")


def make_photo_id(now: Optional[datetime] = None) -> str:
    """
    Generate a concise, chronologically-sortable 7-character photo ID.

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

    delta = now - PHOTO_ID_EPOCH
    second = int(delta.total_seconds())

    # Update per-second sequence counter
    if _last_second is None or second != _last_second:
        _last_second = second
        _seq_in_second = 0
    else:
        _seq_in_second = (_seq_in_second + 1) % len(ALPHABET)

    ts_part = base36_encode(second, min_length=6)
    seq_part = ALPHABET[_seq_in_second]

    return ts_part + seq_part


# ─── LLM-Friendly YAML Formatting ────────────────────────────────────

# Tunables for "LLM-friendly" YAML formatting
_MAX_FLOW_LINE = 240      # max length for a single-line flow sequence
_BLOCK_SCALAR_MIN = 240   # min length before a scalar becomes a | block

_yaml_llm = YAML()
# Let us control wrapping; don't let the dumper wrap aggressively on its own.
_yaml_llm.width = 4096
_yaml_llm.indent(mapping=2, sequence=2, offset=2)


_RESERVED_WORDS = {
    "null", "none", "true", "false",
    "yes", "no", "on", "off",
    "y", "n", "~",
}


def _needs_quotes(value: str) -> bool:
    """
    Decide if a scalar *must* be quoted to be valid / unambiguous YAML.

    We are intentionally lax: if we can get away with no quotes, we do,
    for token efficiency (e.g., .py, .yaml).
    """
    if value == "":
        return True

    # Any whitespace -> quote.
    if any(ch.isspace() for ch in value):
        return True

    # Leading characters that tend to confuse YAML parsers.
    if value[0] in "#&*?,[]{}|>!%@`":
        return True

    # Colon in plain scalars is asking for pain.
    if ":" in value:
        return True

    if value.lower() in _RESERVED_WORDS:
        return True

    return False


def _prepare_for_llm_yaml(
    obj: Any,
    *,
    max_flow_line: int,
    block_scalar_min: int,
) -> Any:
    """
    Walk a plain Python structure and wrap it in ruamel's Commented*
    containers + ScalarString subclasses so the dumper emits:

    - Flow style lists for short / simple sequences without spaces.
    - Block lists otherwise.
    - | block scalars for long or multiline strings.
    - Quotes only when YAML actually needs them.
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

        # Heuristic: consider flow style only if all elements are simple scalars
        # (no newlines). ScalarString subclasses are still `isinstance(str, ...)`.
        simple_scalars = all(
            isinstance(x, str) and ("\n" not in x) for x in seq
        )

        if simple_scalars:
            if all(" " not in str(x) for x in seq):
                inline_repr = "[ " + ", ".join(str(x) for x in seq) + " ]"
                if len(inline_repr) <= max_flow_line:
                    seq.fa.set_flow_style()
                else:
                    seq.fa.set_block_style()
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
        return obj

    # Numbers, bools, None, etc. -> let ruamel handle them.
    return obj


def dump_llm_yaml(
    data: Any,
    *,
    max_flow_line: int = _MAX_FLOW_LINE,
    block_scalar_min: int = _BLOCK_SCALAR_MIN,
) -> str:
    """
    Dump a Python structure to a YAML string optimized for LLM consumption.

    Heuristics:
      - Flow style lists for compact, whitespace-free items
        (e.g., [ .py, .yaml, .md ]).
      - Block lists for anything with spaces.
      - | block scalars for long/multiline text.
      - Quotes only when YAML requires them.
    """
    prepared = _prepare_for_llm_yaml(
        data,
        max_flow_line=max_flow_line,
        block_scalar_min=block_scalar_min,
    )
    buf = io.StringIO()
    _yaml_llm.dump(prepared, buf)
    return buf.getvalue()