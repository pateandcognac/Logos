# Logos/src/logos/shell.py

"""
Helpers for running non-interactive shell commands.

These are intended for quick, one-off operations like listing files,
checking system info, or invoking existing command-line tools.
"""

import subprocess
from pathlib import Path
from .core import api_call, Verbosity, check_for_interrupt
from typing import Optional 

__all__ = ["run"]


@api_call(default_verbosity=Verbosity.BRIEF)
def run(
    command: str,
    timeout: int = 30,
    cwd: Optional[str] = None,
) -> str:
    """
    Runs a non-interactive shell command. `print()`s and returns its combined stdout/stderr output.

    Args:
        command:
            The shell command to execute. This is passed to /bin/sh -c.
        timeout:
            Maximum number of seconds to wait before aborting the command.
        cwd:
            Optional working directory. Defaults to the current workspace root.

    Returns:
        The combined stdout and stderr of the command as a string.

    Note to self:
        - Prints *and* returns the output.
        - This is for non-interactive, one-shot commands.
        - If I want more control, I should use Python's subprocess module directly.
    """
    check_for_interrupt()

    if cwd is not None:
        cwd_path = Path(cwd)
    else:
        cwd_path = Path.cwd()

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        output += f"\n[Command timed out after {timeout} seconds]"
        print(output)
        return output

    output = result.stdout or ""
    print(output)
    return output
