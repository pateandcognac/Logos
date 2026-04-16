# Logos/src/hook_routines/__init__.py

"""
My library of broadly reusable cognitive hook routines. 🧠

This `__init__.py` file auto-discovers and imports all hook_routine modules
in this directory, making them available under the `hook_routines` namespace.
"""

import pkgutil
import importlib
import os
import sys
import inspect

# ----------------------------------------------------------------------------
# SECTION 1: AUTO-MAGIC SKILL LOADER
# ----------------------------------------------------------------------------
# This loop iterates through all .py files in this directory and imports them.
# This way, I never have to manually update this file when I write a new skill.
# One broken skill file won't crash my whole brain, it will just print a warning.
# ----------------------------------------------------------------------------

# The path to this 'skills' package
package_path = os.path.dirname(__file__)

for _, modname, _ in pkgutil.iter_modules([package_path]):
    # Skip any files starting with an underscore (e.g., _helpers.py)
    if modname.startswith('_'):
        continue
    try:
        # Perform a relative import of the discovered module
        importlib.import_module(f".{modname}", __name__)
    except Exception as e:
        # Gracefully handle errors in a skill file so it doesn't crash me
        print(f"WARN: Could not load hook_routine module '{modname}': {e}")
