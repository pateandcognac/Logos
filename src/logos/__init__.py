# src/logos/__init__.py

"""
This is the central entry point for my API. It makes my tools available
under the `logos` namespace.
"""

# Import the state class and create a single, persistent instance for me to use.
from .config import LogosConfig, load_state_from_yaml
config = LogosConfig()
load_state_from_yaml(config)
import time

# Core convenience imports
from .core import Verbosity, verbosity, check_for_interrupt, help, _ALL_SENTINEL as everything

# Submodules
from . import core, emote, ros, files, hooks, memory, models, exceptions, shell, utils, vision, pantilt, leds, base, nav, map3d

# We will add more here as we build out the API

# TODO: cron style jobs (obvi Chronos inspo) that triggers an automated <py> block publish, or, prompts myself as a <!-- system: style prompt. -->



