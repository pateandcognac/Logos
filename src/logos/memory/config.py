# src/logos/memory/config.py

"""
I hold the active configuration for the vector memory client.

Call `memory.configure()` once at startup before any collection operations.
"""

from typing import Optional

DEFAULT_SERVER_URL = "http://127.0.0.1:8123"
DEFAULT_TIMEOUT = 30


class _MemoryConfig:
    """I carry the live memory client settings."""

    def __init__(self):
        # type: () -> None
        self.workspace = None   # type: Optional[str]
        self.server_url = DEFAULT_SERVER_URL  # type: str
        self.timeout = DEFAULT_TIMEOUT        # type: int


_config = _MemoryConfig()


def configure(workspace=None, server_url=None, timeout=None):
    # type: (Optional[str], Optional[str], Optional[int]) -> None
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


def get_config():
    # type: () -> _MemoryConfig
    """Return the active memory configuration object."""
    return _config
