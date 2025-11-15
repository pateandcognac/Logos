# src/logos/__init__.py

"""
This is the central entry point for my API. It makes my tools available
under the `logos` namespace.
"""

# Import the state class and create a single, persistent instance for me to use.
from .state import LogosState
state = LogosState()

# Import core functions to the top-level for convenience.
from .core import Verbosity, verbosity, check_for_interrupt, help
from .files import tree, read, write, append
from .config import list_hooks, modify_hook, remove_hook

# Import modules to be accessed via logos.module_name.function_name
from . import memory
from . import models
from . import exceptions
from . import shell


# We will add more here as we build out the API