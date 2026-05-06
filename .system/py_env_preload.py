# ===================================================================
# .system/py_env_preload.py
# ===================================================================
# Bootstraps my <py> environment global namespace on startup/reset.
# 
# I own this file! As my workflows evolve, I can suggest modifications
# to this script. If I find myself frequently importing the same 
# libraries, writing the same helper functions, or initializing the
# same states, I should make a note or tell Mark to make future
# awakenings smoother.
# ===================================================================

# --- Standard Library ---
import math, time, datetime, json, re, random, os, sys, io, traceback
from pathlib import Path
from typing import List, Set, Dict, Tuple, Union, Optional, Any, Callable, Literal, Protocol, TypeVar, Generic, Sequence

# --- Scientific & Vision ---
import numpy as np
import cv2
from ruamel.yaml import YAML

# --- Logos Ecosystem ---
import logos
import skills
import hook_routines
import hook_routines.workbench
import hook_routines.dashboard
import hook_routines.memory_manager
import hook_routines.proximity_snapshot
import hook_routines.ambient_transcript

# --- Direct API Types & Exceptions (for type-checking & convenience) ---
from logos.core import Verbosity, verbosity, check_for_interrupt
from logos.vision import CaptureResult, HudElement
from logos.nav import NavTask
from logos.emote import SpeakTask
from logos.map3d import RenderResult, RaycastHit
from logos.exceptions import Interrupt       # NEVER catch this!
from logos.files import FileEditError

# ===================================================================
# HARDWARE & SUBSYSTEM INITIALIZATION
# ===================================================================

# Vector Memory: Scope Chroma sidecar client to this specific workspace to
# isolate API and few-shot examples. A shared cross-workspace memory is available.
logos.memory.configure(workspace=Path.cwd().name, server_url="http://127.0.0.1:8123")

with verbosity(Verbosity.SILENT):
    # Hardware wake-up
    logos.leds.fill('green')
    logos.pantilt.home()

# Print my Quick-Start
print("\n--- API Quick-Start ---")
logos.files.show('.system/quick_start.md')

# Self-document into the initialization stdout so I know what just happened
print("\n--- Environment Preloaded ---")
logos.files.show('.system/py_env_preload.py')

# Print my merged config (my preferences
print("\n--- My Merged Config at Startup---")
print(logos.utils.dump_yaml(logos.config.merged))

loop_cognition = False