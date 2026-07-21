from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sources.discogs import DiscogsConnector


@dataclass(frozen=True)
class SourceDefinition:
    key: str
    display_name: str
    description: str
    enabled: bool
    connector_factory: Callable[[dict[str, Any]], Any]


SOURCE_REGISTRY = {
    "discogs": SourceDefinition(
        key="discogs",
        display_name="Discogs",
        description="Music release metadata, labels, formats, track listings and image URLs.",
        enabled=True,
        connector_factory=lambda settings: DiscogsConnector(**settings),
    ),
    "amazon": SourceDefinition(
        key="amazon",
        display_name="Amazon",
        description="ASIN, retail metadata, package dimensions, weights and images.",
        enabled=False,
        connector_factory=lambda settings: None,
    ),
    "musicbrainz": SourceDefinition(
        key="musicbrainz",
        display_name="MusicBrainz",
        description="Release metadata and Cover Art Archive fallback images.",
        enabled=False,
        connector_factory=lambda settings: None,
    ),
    "spotify": SourceDefinition(
        key="spotify",
        display_name="Spotify",
        description="Digital release and track metadata.",
        enabled=False,
        connector_factory=lambda settings: None,
    ),
    "apple_music": SourceDefinition(
        key="apple_music",
        display_name="Apple Music",
        description="Digital release metadata and artwork.",
        enabled=False,
        connector_factory=lambda settings: None,
    ),
    "audiosalad": SourceDefinition(
        key="audiosalad",
        display_name="AudioSalad",
        description="Internal catalogue metadata and digital identifiers.",
        enabled=False,
        connector_factory=lambda settings: None,
    ),
}
