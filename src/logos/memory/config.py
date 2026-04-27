# src/logos/memory/config.py

"""
Holds the active configuration for the vector memory client.

Call `memory.configure()` once at startup before any collection operations.
"""

from typing import Optional

from ..core import Verbosity, api_call

DEFAULT_SERVER_URL = "http://127.0.0.1:8123"
DEFAULT_TIMEOUT = 30


class _MemoryConfig:
    """I carry the live memory client settings."""

    def __init__(self) -> None:
        self.workspace: Optional[str] = None
        self.server_url: str = DEFAULT_SERVER_URL
        self.timeout: int = DEFAULT_TIMEOUT


_config = _MemoryConfig()


@api_call(default_verbosity=Verbosity.BRIEF)
def configure(
    workspace: Optional[str] = None,
    server_url: Optional[str] = None,
    timeout: Optional[int] = None,
) -> None:
    """
    Configure the vector memory client.

    I should be called once during startup before any memory operations.
    Only the arguments that are not None are updated; the rest keep their
    current values (or defaults).

    Args:
        workspace: Namespace slug for workspace-scoped collections (e.g. "123_Logos").
            This becomes the middle segment of the physical collection name:
            `logos__{workspace}__{kind}`.
        server_url: Base URL of the Logos Chroma sidecar.
            Defaults to `http://127.0.0.1:8123`.
        timeout: HTTP request timeout in seconds. Defaults to 30.

    Note to self:
        Passing `namespace="shared"` to `get_or_create_collection` overrides
        the workspace for that single call — useful for global shared collections.
    """
    if workspace is not None:
        _config.workspace = workspace
    if server_url is not None:
        _config.server_url = server_url
    if timeout is not None:
        _config.timeout = timeout


def get_config() -> _MemoryConfig:
    """Return the active memory configuration object."""
    return _config
