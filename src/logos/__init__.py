# src/logos/__init__.py

"""
This is the central entry point for my API. It makes my tools available
under the `logos` namespace.
"""

# Import the state class and create a single, persistent instance for me to use.
from .state import LogosState, load_state_from_yaml
state = LogosState()
load_state_from_yaml(state)
import time

# Core convenience imports
from .core import Verbosity, verbosity, check_for_interrupt, help

# Submodules
from . import core, ros, files, hooks, memory, models, exceptions, shell, utils, vision, pantilt, leds, voice, base, nav, chora

# We will add more here as we build out the API

# voice.speak("Logos API is online! 👋", wait=False)