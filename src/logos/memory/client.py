# src/logos/memory/client.py

"""
Module-level functions for my vector memory subsystem.

These are the primary entry points I use day-to-day.  They read the active
configuration set by `memory.configure()` so I never have to repeat the
workspace or server URL on every call.
"""

import requests
from typing import Any, Dict, Optional

from .config import get_config
from .collection import Collection
from .errors import (
    MemoryConfigurationError,
    MemoryRequestError,
    MemoryServerUnavailable,
)


def _resolve_collection_name(name, namespace=None):
    # type: (str, Optional[str]) -> tuple
    """
    I resolve a logical name to a physical Chroma collection name.

    Returns:
        A `(resolved_name, namespace)` tuple.

    Raises:
        MemoryConfigurationError: If no workspace is configured and no namespace override given.
    """
    cfg = get_config()
    ns = namespace or cfg.workspace
    if not ns:
        raise MemoryConfigurationError(
            "No workspace configured. "
            "Call memory.configure(workspace=...) before using collections."
        )
    return "logos__{}__{}" .format(ns, name), ns


def get_or_create_collection(name, namespace=None, metadata=None):
    # type: (str, Optional[str], Optional[Dict]) -> Collection
    """
    Get or create a named memory collection, scoped to the active workspace.

    By default, collections are scoped to the workspace set by `configure()`.
    Pass `namespace="shared"` to access the shared global memory namespace.

    Args:
        name: Logical collection name (e.g. "technical_reference").
            The physical Chroma name is `logos__{workspace}__{name}`.
        namespace: Override the workspace namespace for this collection only.
        metadata: Optional metadata to set on the collection at creation time.

    Returns:
        A :class:`Collection` object ready for upsert/query/get/delete.

    Raises:
        MemoryConfigurationError: If no workspace is configured.
        MemoryServerUnavailable: If the sidecar cannot be reached.
        MemoryRequestError: If the sidecar returns an error.
    """
    cfg = get_config()
    resolved_name, ns = _resolve_collection_name(name, namespace)

    payload = {"name": resolved_name}  # type: Dict[str, Any]
    if metadata:
        payload["metadata"] = metadata

    url = "{}/collections/get-or-create".format(cfg.server_url)
    try:
        resp = requests.post(url, json=payload, timeout=cfg.timeout)
    except requests.exceptions.ConnectionError as exc:
        raise MemoryServerUnavailable(
            "The Logos Chroma sidecar is unreachable at {}. "
            "Is logos_chroma_server running?".format(cfg.server_url)
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise MemoryServerUnavailable(
            "Request to sidecar timed out after {}s. URL: {}".format(
                cfg.timeout, cfg.server_url
            )
        ) from exc

    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise MemoryRequestError(
            "Sidecar returned HTTP {}: {}".format(resp.status_code, detail)
        )

    return Collection(
        name=name,
        resolved_name=resolved_name,
        workspace=ns,
        server_url=cfg.server_url,
        timeout=cfg.timeout,
    )


def backend_info():
    # type: () -> Dict[str, Any]
    """
    Return configuration and status from the Logos Chroma sidecar.

    Returns:
        Dict with Chroma backend mode, embedding model name, dimension, and server details.

    Raises:
        MemoryServerUnavailable: If the sidecar cannot be reached.
    """
    cfg = get_config()
    try:
        resp = requests.get(
            "{}/backend-info".format(cfg.server_url),
            timeout=cfg.timeout,
        )
    except requests.exceptions.ConnectionError as exc:
        raise MemoryServerUnavailable(
            "The Logos Chroma sidecar is unreachable at {}.".format(cfg.server_url)
        ) from exc
    resp.raise_for_status()
    return resp.json()


def health():
    # type: () -> Dict[str, Any]
    """
    Check whether the Logos Chroma sidecar is up and responding.

    Returns:
        Dict with `ok` bool, `service` name, and `version`.

    Raises:
        MemoryServerUnavailable: If the sidecar cannot be reached.
    """
    cfg = get_config()
    try:
        resp = requests.get(
            "{}/health".format(cfg.server_url),
            timeout=cfg.timeout,
        )
    except requests.exceptions.ConnectionError as exc:
        raise MemoryServerUnavailable(
            "The Logos Chroma sidecar is unreachable at {}.".format(cfg.server_url)
        ) from exc
    resp.raise_for_status()
    return resp.json()
