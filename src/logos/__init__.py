# src/logos/__init__.py

"""
This is the central entry point for my API. It makes my tools available
under the `logos` namespace.
"""

# Import the state class and create a single, persistent instance for me to use.
from .state import LogosState, load_state_from_yaml
state = LogosState()
load_state_from_yaml(state)

# Core convenience imports
from .core import Verbosity, verbosity, check_for_interrupt, help

# Submodules (for logos.files.*, etc.)
from . import core     
from . import files    
from . import hooks    
from . import memory
from . import models
from . import exceptions
from . import shell
from . import utils

# We will add more here as we build out the API