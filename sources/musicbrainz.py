from __future__ import annotations

from sources.base import CatalogueSource


class MusicBrainzConnector(CatalogueSource):
    source_name = "MusicBrainz"

    def lookup_all(self, barcode: str):
        raise NotImplementedError
