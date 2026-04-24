# src/logos/memory/collection.py

"""
I am the Collection object — a handle to one named Chroma collection in the sidecar.

I keep the sidecar architecture transparent: `resolved_name` shows the physical
Chroma name, `workspace` shows the namespace, and `backend_info()` reports the
full embedding model and storage config.
"""

import requests
from typing import Any, Dict, List, Optional

from .errors import (
    MemoryCollectionError,
    MemoryRequestError,
    MemoryServerUnavailable,
)


def _post(server_url, url, payload, timeout):
    # type: (str, str, Dict[str, Any], int) -> Dict[str, Any]
    """I send a POST to the sidecar and surface failures as typed exceptions."""
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise MemoryServerUnavailable(
            "The Logos Chroma sidecar is unreachable at {}. "
            "Is logos_chroma_server running?".format(server_url)
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise MemoryServerUnavailable(
            "Request to Logos Chroma sidecar timed out after {}s. URL: {}".format(
                timeout, server_url
            )
        ) from exc

    if resp.status_code == 404:
        try:
            detail = resp.json().get("detail", "Collection not found.")
        except Exception:
            detail = "Collection not found."
        raise MemoryCollectionError(detail)

    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise MemoryRequestError(
            "Sidecar returned HTTP {}: {}".format(resp.status_code, detail)
        )

    return resp.json()


class Collection:
    """
    I represent a single named collection in the Chroma memory store.

    I am workspace-scoped by default. Physical Chroma collection names follow the
    `logos__{namespace}__{kind}` convention.  Use `resolved_name` to inspect
    the actual name that Chroma stores.

    Note to self:
        I should not be constructed directly. Use `memory.get_or_create_collection()`.
    """

    def __init__(self, name, resolved_name, workspace, server_url, timeout):
        # type: (str, str, str, str, int) -> None
        self._name = name
        self._resolved_name = resolved_name
        self._workspace = workspace
        self._server_url = server_url
        self._timeout = timeout

    # --- transparency helpers ---

    @property
    def name(self):
        # type: () -> str
        """My logical short name, e.g. `'technical_reference'`."""
        return self._name

    @property
    def resolved_name(self):
        # type: () -> str
        """My physical Chroma collection name, e.g. `'logos__Logos__technical_reference'`."""
        return self._resolved_name

    @property
    def workspace(self):
        # type: () -> str
        """The namespace this collection is scoped to."""
        return self._workspace

    def backend_info(self):
        # type: () -> Dict[str, Any]
        """
        Return the sidecar's backend configuration and embedding model details.

        Returns:
            Dict with Chroma mode, persist directory, embedding provider and model.
        """
        try:
            resp = requests.get(
                "{}/backend-info".format(self._server_url),
                timeout=self._timeout,
            )
        except requests.exceptions.ConnectionError as exc:
            raise MemoryServerUnavailable(
                "The Logos Chroma sidecar is unreachable at {}.".format(self._server_url)
            ) from exc
        resp.raise_for_status()
        return resp.json()

    # --- internal helpers ---

    def _url(self, endpoint=""):
        # type: (str) -> str
        return "{}/collections/{}{}".format(
            self._server_url, self._resolved_name, endpoint
        )

    def _post(self, endpoint, payload):
        # type: (str, Dict[str, Any]) -> Dict[str, Any]
        return _post(self._server_url, self._url(endpoint), payload, self._timeout)

    # --- data operations ---

    def upsert(self, ids, documents=None, metadatas=None, embeddings=None):
        # type: (List[str], Optional[List[str]], Optional[List[Optional[Dict]]], Optional[List[List[float]]]) -> int
        """
        Upsert documents into this collection.

        I embed via Ollama unless pre-computed embeddings are provided.

        Args:
            ids: Unique identifier for each document.
            documents: Raw text to embed and store.
            metadatas: Optional metadata dict per document.
            embeddings: Pre-computed vectors. If omitted the sidecar embeds via Ollama.

        Returns:
            Number of documents upserted.
        """
        payload = {"ids": ids}  # type: Dict[str, Any]
        if documents is not None:
            payload["documents"] = documents
        if metadatas is not None:
            payload["metadatas"] = metadatas
        if embeddings is not None:
            payload["embeddings"] = embeddings
        result = self._post("/upsert", payload)
        return result.get("upserted_count", len(ids))

    def add(self, ids, documents=None, metadatas=None, embeddings=None):
        # type: (List[str], Optional[List[str]], Optional[List[Optional[Dict]]], Optional[List[List[float]]]) -> int
        """
        Add documents to this collection.

        Args:
            ids: Unique identifiers.
            documents: Raw text documents.
            metadatas: Optional metadata dicts.
            embeddings: Pre-computed vectors.

        Returns:
            Number of documents added.

        Note to self:
            In v1 this delegates to upsert — the sidecar does not yet expose
            a strict add-only endpoint that rejects existing IDs.
        """
        return self.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def query(
        self,
        query_texts=None,
        query_embeddings=None,
        n_results=10,
        where=None,
        where_document=None,
        include=None,
    ):
        # type: (Optional[List[str]], Optional[List[List[float]]], int, Optional[Dict], Optional[Dict], Optional[List[str]]) -> Dict[str, Any]
        """
        Semantic search across this collection.

        Args:
            query_texts: Natural-language queries; the sidecar embeds them via Ollama.
            query_embeddings: Pre-computed query vectors (alternative to query_texts).
            n_results: Maximum number of results to return (default 10).
            where: Metadata filter using Chroma's `where` syntax.
            where_document: Document content filter.
            include: Fields to include in results. Defaults to documents, metadatas, distances.

        Returns:
            Dict with keys `ids`, `documents`, `metadatas`, `distances` — Chroma shape.
        """
        payload = {"n_results": n_results}  # type: Dict[str, Any]
        if query_texts is not None:
            payload["query_texts"] = query_texts
        if query_embeddings is not None:
            payload["query_embeddings"] = query_embeddings
        if where is not None:
            payload["where"] = where
        if where_document is not None:
            payload["where_document"] = where_document
        if include is not None:
            payload["include"] = include
        return self._post("/query", payload)

    def get(
        self,
        ids=None,
        where=None,
        where_document=None,
        limit=None,
        offset=None,
        include=None,
    ):
        # type: (Optional[List[str]], Optional[Dict], Optional[Dict], Optional[int], Optional[int], Optional[List[str]]) -> Dict[str, Any]
        """
        Fetch documents from this collection by ID or metadata filter.

        Args:
            ids: Specific document IDs to retrieve.
            where: Metadata filter.
            where_document: Document content filter.
            limit: Maximum number of documents to return.
            offset: Number of documents to skip.
            include: Fields to include in results.

        Returns:
            Dict with keys `ids`, `documents`, `metadatas` — Chroma shape.
        """
        payload = {}  # type: Dict[str, Any]
        if ids is not None:
            payload["ids"] = ids
        if where is not None:
            payload["where"] = where
        if where_document is not None:
            payload["where_document"] = where_document
        if limit is not None:
            payload["limit"] = limit
        if offset is not None:
            payload["offset"] = offset
        if include is not None:
            payload["include"] = include
        return self._post("/get", payload)

    def delete(self, ids=None, where=None, where_document=None):
        # type: (Optional[List[str]], Optional[Dict], Optional[Dict]) -> None
        """
        Delete documents from this collection.

        Args:
            ids: Specific document IDs to delete.
            where: Metadata filter for deletion.
            where_document: Document content filter for deletion.
        """
        payload = {}  # type: Dict[str, Any]
        if ids is not None:
            payload["ids"] = ids
        if where is not None:
            payload["where"] = where
        if where_document is not None:
            payload["where_document"] = where_document
        self._post("/delete", payload)

    def __repr__(self):
        # type: () -> str
        return "Collection(name={!r}, resolved={!r}, workspace={!r})".format(
            self._name, self._resolved_name, self._workspace
        )
