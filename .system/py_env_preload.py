# ===================================================================
#  Logos Python Environment Preload Script
# ===================================================================
# This script is compiled and executed once when the interpreter
# instance is created. It pre-populates the global namespace with
# the most common tools I'll need, making my <py> blocks cleaner
# and more efficient.
# ===================================================================

# --- Core Logos API & Modules ---
import logos
import skills
import hook_routines
import hook_routines.workbench
import hook_routines.dashboard
import hook_routines.memory_manager
import hook_routines.proximity_snapshot

# --- Python Standard Library (The Essentials) ---
import time       # For all temporal operations: sleeping, measuring duration, etc.
from datetime import datetime, timedelta, timezone
import math       # For trigonometry, angles, and distances in my physical space.
import json       # For inspecting my memory files (io_buffer, summaries).
import re         # For advanced text parsing, searching, and code manipulation.
import random     # For non-deterministic behaviors, like choosing a random greeting or a search pattern.
from pathlib import Path # The modern, object-oriented way to handle filesystem paths.
from ruamel.yaml import YAML
import io
import os
import sys
import traceback

# --- Types ---
from typing import List, Set, Dict, Tuple, Union, Optional
from typing import Any, Callable, Literal, Protocol # , Annotated
from typing import TypeVar, Generic, Sequence

# --- Core Scientific & Vision Libraries ---
import numpy as np # ESSENTIAL. All my vision data is in numpy arrays. Needed for any math on images or point clouds.
import cv2         # For advanced, on-the-fly image processing not covered by the API (e.g., color conversion).

# --- Key Classes & Enums from the Logos API ---
# By importing these directly, I can use them without the `logos.` prefix,
# which is great for type checking (`isinstance`) and verbosity control.

from logos.core import Verbosity, verbosity, check_for_interrupt #, everything # The core of my interaction patterns.

from logos.vision import CaptureResult, HudElement   # `CaptureResult` is the main object from my eyes. `HudElement` is for drawing on images.
from logos.nav import NavTask                      # The handle for all my navigation tasks, lets me check progress.
from logos.emote import SpeakTask                    # The handle for my voice, lets me choreograph actions with speech.
from logos.map3d import RenderResult, RaycastHit   # The main objects from my mind-palace.

from logos.exceptions import Interrupt   # Good to have in scope for context, but I must NOT try to catch this!
from logos.files import FileEditError  # So I can gracefully handle file edit failures in a try/except block.
