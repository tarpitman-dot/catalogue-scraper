from __future__ import annotations

from sources.placeholders import PlaceholderConnector


class MusicBrainzConnector(PlaceholderConnector):
    def __init__(self) -> None:
        super().__init__("MusicBrainz")
