# src/logos/memory/collection.py

"""
I am the Collection object — a handle to one named Chroma collection in the sidecar.

I keep the sidecar architecture transparent: `resolved_name` shows the physical
Chroma name, `workspace` shows the namespace, and `backend_info()` reports the
full embedding model and storage config.
"""

import requests
from typing import Any, Dict, List, Optional

from ..core import Verbosity, api_call
from .errors import (
    MemoryCollectionError,
    MemoryRequestError,
    MemoryServerUnavailable,
)


def _post(
    server_url: str,
    url: str,
    payload: Dict[str, Any],
    timeout: int,
) -> Dict[str, Any]:
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
    Represents a single named collection in the Chroma memory store.

    I am workspace-scoped by default. Physical Chroma collection names follow the
    `logos__{namespace}__{kind}` convention.  Use `resolved_name` to inspect
    the actual name that Chroma stores.

    Note to self:
        Should not be constructed directly. Use `memory.get_or_create_collection()`.
    """

    def __init__(
        self,
        name: str,
        resolved_name: str,
        workspace: str,
        server_url: str,
        timeout: int,
    ) -> None:
        self._name = name
        self._resolved_name = resolved_name
        self._workspace = workspace
        self._server_url = server_url
        self._timeout = timeout

    # --- transparency helpers ---

    @property
    def name(self) -> str:
        """My logical short name, e.g. technical_reference, shared_personal"""
        return self._name

    @property
    def resolved_name(self) -> str:
        """My physical Chroma collection name, e.g. logos__Logos__technical_reference."""
        return self._resolved_name

    @property
    def workspace(self) -> str:
        """The namespace this collection is scoped to."""
        return self._workspace

    def backend_info(self) -> Dict[str, Any]:
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

    def _url(self, endpoint: str = "") -> str:
        return "{}/collections/{}{}".format(
            self._server_url, self._resolved_name, endpoint
        )

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _post(self._server_url, self._url(endpoint), payload, self._timeout)

    # --- data operations ---

    @api_call(default_verbosity=Verbosity.ACK)
    def upsert(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Optional[Dict[str, Any]]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> int:
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
        payload: Dict[str, Any] = {"ids": ids}
        if documents is not None:
            payload["documents"] = documents
        if metadatas is not None:
            payload["metadatas"] = metadatas
        if embeddings is not None:
            payload["embeddings"] = embeddings
        result = self._post("/upsert", payload)
        return result.get("upserted_count", len(ids))

    @api_call(default_verbosity=Verbosity.ACK)
    def add(
        self,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Optional[Dict[str, Any]]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> int:
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
            verbosity=Verbosity.SILENT,
        )

    def query(
        self,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
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
        payload: Dict[str, Any] = {"n_results": n_results}
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
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
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
        payload: Dict[str, Any] = {}
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

    @api_call(default_verbosity=Verbosity.ACK)
    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Delete documents from this collection.

        Args:
            ids: Specific document IDs to delete.
            where: Metadata filter for deletion.
            where_document: Document content filter for deletion.
        """
        payload: Dict[str, Any] = {}
        if ids is not None:
            payload["ids"] = ids
        if where is not None:
            payload["where"] = where
        if where_document is not None:
            payload["where_document"] = where_document
        self._post("/delete", payload)

    def __repr__(self) -> str:
        return "Collection(name={!r}, resolved={!r}, workspace={!r})".format(
            self._name, self._resolved_name, self._workspace
        )
