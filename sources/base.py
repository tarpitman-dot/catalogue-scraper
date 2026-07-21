from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SourceError(RuntimeError):
    """Raised when a catalogue source cannot complete a request."""


class CatalogueSource(ABC):
    """Common interface implemented by every catalogue source.

    Connectors keep all source-specific API details out of the Streamlit UI. New
    sources should implement these three methods and return dictionaries whose
    keys are safe to display in result tables and exports.
    """

    source_name: str

    @abstractmethod
    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        """Return every release/product matching a UPC/EAN barcode."""
        raise NotImplementedError

    @abstractmethod
    def search(self, text: str) -> list[dict[str, Any]]:
        """Return source results matching free-text search criteria."""
        raise NotImplementedError

    @abstractmethod
    def get_release(self, release_id: str | int) -> dict[str, Any]:
        """Return one fully hydrated source release/product record by id."""
        raise NotImplementedError
