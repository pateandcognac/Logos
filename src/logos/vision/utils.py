# Logos/src/logos/vision/utils.py

"""
Helper functions for file naming and ID generation.
"""

import os
from datetime import datetime, timezone
import string
from pathlib import Path
from typing import Tuple

# Epoch for our custom ID generation (Jan 1, 2025)
EPOCH = datetime(2025, 1, 1, tzinfo=timezone.utc)
BASE36_ALPHABET = string.digits + string.ascii_lowercase

_last_second: int = 0
_seq_in_second: int = 0


def _base36_encode(number: int, min_length: int = 4) -> str:
    """Internal helper to convert integer to base36 string."""
    if number == 0:
        return '0' * min_length
    base36 = ''
    while number != 0:
        number, i = divmod(number, 36)
        base36 = BASE36_ALPHABET[i] + base36
    return base36.zfill(min_length)


def make_photo_id(now: datetime = None) -> str:
    """
    Generates a concise, time-ordered 7-char ID.
    Format: [6 chars seconds since 2025][1 char sequence]
    
    Args:
        now: Optional datetime object. Defaults to current UTC time.

    Returns:
        A string ID like "001a2z0".

    Note to self:
        This ensures my memories sort chronologically naturally.
    """
    global _last_second, _seq_in_second

    if now is None:
        now = datetime.now(timezone.utc)

    delta = now - EPOCH
    second = int(delta.total_seconds())

    # Update per-second sequence to handle bursts
    if second != _last_second:
        _last_second = second
        _seq_in_second = 0
    else:
        _seq_in_second = (_seq_in_second + 1) % len(BASE36_ALPHABET)

    ts_part = _base36_encode(second, min_length=6)
    seq_part = BASE36_ALPHABET[_seq_in_second]

    return ts_part + seq_part


def get_artifact_path(camera_name: str, photo_id: str, extension: str = ".jpg") -> Path:
    """
    Constructs the absolute path for saving an image artifact.
    Ensures the directory exists.
    """
    # Assuming CWD is workspace root
    base = Path("artifacts") / camera_name
    if not base.exists():
        base.mkdir(parents=True, exist_ok=True)
    
    return base / f"{photo_id}{extension}"