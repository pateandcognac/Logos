# src/logos/memory/errors.py

"""
Exception hierarchy for my Chroma-backed vector memory subsystem.

I raise these instead of returning empty results so infrastructure failures
are never silently swallowed.
"""


class MemoryError(RuntimeError):
    """Base class for all memory subsystem errors."""
    pass


class MemoryServerUnavailable(MemoryError):
    """Raised when the Logos Chroma sidecar cannot be reached over HTTP."""
    pass


class MemoryRequestError(MemoryError):
    """Raised when the sidecar returns an error response (4xx / 5xx)."""
    pass


class MemoryEmbeddingError(MemoryError):
    """Raised when the embedding model is unavailable or the embed call fails."""
    pass


class MemoryCollectionError(MemoryError):
    """Raised for collection-level errors such as a missing collection."""
    pass


class MemoryConfigurationError(MemoryError):
    """Raised when memory.configure() has not been called or is incomplete."""
    pass
