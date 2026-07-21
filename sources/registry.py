from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable
from sources.base import CatalogueSource
from sources.discogs import DiscogsConfig, DiscogsConnector
from sources.placeholders import PlaceholderConnector
from sources.musicbrainz import MusicBrainzConfig, MusicBrainzConnector
from sources.spotify import SpotifyConfig, SpotifyConnector
from sources.apple import AppleConfig, AppleConnector

ConnectorFactory = Callable[[dict[str, Any]], CatalogueSource]

@dataclass(frozen=True)
class SourceDefinition:
    key: str; display_name: str; description: str; enabled: bool; required_secret_names: tuple[str, ...]; connector_factory: ConnectorFactory; no_credentials: bool=False; planned: bool=False
    @property
    def status(self) -> str:
        if self.planned: return "Planned"
        return "Available without credentials" if self.no_credentials else "Connected"
    def create_connector(self, settings: dict[str, Any]) -> CatalogueSource: return self.connector_factory(settings)

def create_discogs_connector(settings: dict[str, Any]) -> DiscogsConnector: return DiscogsConnector(DiscogsConfig.from_settings(settings))
def create_mb_connector(settings: dict[str, Any]) -> MusicBrainzConnector: return MusicBrainzConnector(MusicBrainzConfig.from_settings(settings))
def create_spotify_connector(settings: dict[str, Any]) -> SpotifyConnector: return SpotifyConnector(SpotifyConfig.from_settings(settings))
def create_apple_connector(settings: dict[str, Any]) -> AppleConnector: return AppleConnector(AppleConfig.from_settings(settings))
def placeholder_factory(source_name: str) -> ConnectorFactory: return lambda settings: PlaceholderConnector(source_name)

SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "discogs": SourceDefinition("discogs", "Discogs", "Music release metadata, labels, formats, track listings and image URLs.", True, ("DISCOGS_TOKEN",), create_discogs_connector),
    "musicbrainz": SourceDefinition("musicbrainz", "MusicBrainz", "Official MusicBrainz release metadata enriched with Cover Art Archive image URLs.", True, ("MUSICBRAINZ_CONTACT",), create_mb_connector, no_credentials=True),
    "spotify": SourceDefinition("spotify", "Spotify", "Spotify Web API album metadata by UPC.", True, ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"), create_spotify_connector),
    "apple": SourceDefinition("apple", "Apple Music / iTunes", "Apple Music catalogue UPC lookup, falling back to public iTunes Lookup.", True, ("APPLE_MUSIC_DEVELOPER_TOKEN",), create_apple_connector, no_credentials=True),
    "amazon": SourceDefinition("amazon", "Amazon", "ASIN, retail metadata, package dimensions, weights and images; awaiting access.", False, ("AMAZON_CLIENT_ID", "AMAZON_CLIENT_SECRET", "AMAZON_REFRESH_TOKEN", "AMAZON_SELLER_ID"), placeholder_factory("Amazon"), planned=True),
}
