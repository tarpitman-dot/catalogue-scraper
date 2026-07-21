from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sources.lookup import LookupStatus


@dataclass(frozen=True)
class SourceCapabilities:
    supported_lookup_types: frozenset[str]
    max_page_size: int | None = None
    supports_pagination: bool = False
    credentials_required: bool = False
    rate_limit: str = ""


class SourceError(RuntimeError):
    """Raised when a catalogue source cannot complete a request."""


class CatalogueSource(ABC):
    """Common interface implemented by every catalogue source.

    Connectors keep all source-specific API details out of the Streamlit UI. New
    sources should implement these three methods and return dictionaries whose
    keys are safe to display in result tables and exports.
    """

    source_name: str
    supported_lookup_types: set[str] = {"barcode"}
    capabilities: SourceCapabilities | None = None

    def supports_lookup_type(self, lookup_type: str) -> bool:
        return lookup_type in self.supported_lookup_types

    def lookup_by_type(self, lookup_type: str, value: str) -> list[dict[str, Any]]:
        if not self.supports_lookup_type(lookup_type):
            return []
        if lookup_type == "barcode":
            return self.lookup(value)
        return self.search_by_type(lookup_type, value)

    def search_by_type(self, lookup_type: str, value: str) -> list[dict[str, Any]]:
        raise SourceError(f"{self.source_name} does not support {lookup_type} lookup.")

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
