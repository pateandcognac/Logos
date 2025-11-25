# Logos/src/logos/utils.py

"""
Helper functions.
"""


from typing import Any
import io

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from ruamel.yaml.scalarstring import LiteralScalarString, SingleQuotedScalarString

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
            # Candidate for flow style, but only if:
            #   - none of the items contain spaces
            #   - estimated inline length is under max_flow_line
            if all(" " not in str(x) for x in seq):
                # rough inline length estimate; we don’t need it perfect
                inline_repr = "[ " + ", ".join(str(x) for x in seq) + " ]"
                if len(inline_repr) <= max_flow_line:
                    seq.fa.set_flow_style()
                else:
                    seq.fa.set_block_style()
            else:
                # Has spaces but no newlines -> block list, one per line.
                seq.fa.set_block_style()
        else:
            # Any multiline / blocky content -> block list.
            seq.fa.set_block_style()

        return seq

    # --- scalars ----------------------------------------------------------
    if isinstance(obj, str):
        # Long or multiline strings -> LITERAL block scalar (`|`)
        if "\n" in obj or len(obj) >= block_scalar_min:
            return LiteralScalarString(obj)

        # Otherwise, plain scalar if possible; single-quoted if necessary.
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
