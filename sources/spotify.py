from __future__ import annotations
import os, time
from dataclasses import dataclass, field
from typing import Any
from sources.base import CatalogueSource, SourceError
from sources.http import HttpClient
from sources.schema import with_base

@dataclass
class SpotifyConfig:
    client_id: str = ""; client_secret: str = ""; market: str = "GB"
    @classmethod
    def from_settings(cls, s: dict[str, Any]) -> "SpotifyConfig":
        return cls(str(s.get("client_id") or os.getenv("SPOTIFY_CLIENT_ID") or ""), str(s.get("client_secret") or os.getenv("SPOTIFY_CLIENT_SECRET") or ""), str(s.get("market") or os.getenv("SPOTIFY_MARKET") or "GB"))

class SpotifyConnector(CatalogueSource):
    source_name = "Spotify"
    def __init__(self, config: SpotifyConfig | None = None, client: HttpClient | None = None):
        self.config = config or SpotifyConfig.from_settings({}); self.client = client or HttpClient("Spotify", "CatalogueScraper/2.0")
        self._token = ""; self._token_expiry = 0.0
    @property
    def configured(self) -> bool: return bool(self.config.client_id and self.config.client_secret)
    def _ensure_token(self) -> str:
        if not self.configured: raise SourceError("Spotify client credentials are not configured.")
        if self._token and time.time() < self._token_expiry - 60: return self._token
        data = self.client.post_json("https://accounts.spotify.com/api/token", data={"grant_type":"client_credentials"}, auth=(self.config.client_id, self.config.client_secret))
        self._token = data.get("access_token", ""); self._token_expiry = time.time() + int(data.get("expires_in") or 3600)
        return self._token
    def _search_params(self, barcode: str) -> dict[str, str]: return {"q": f"upc:{barcode}", "type": "album", "market": self.config.market, "limit": "50"}
    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        token = self._ensure_token(); data = self.client.get_json("https://api.spotify.com/v1/search", params=self._search_params(barcode), headers={"Authorization": f"Bearer {token}"})
        return [self._album_to_row(a, barcode) for a in ((data.get("albums") or {}).get("items") or [])]
    def search(self, text: str) -> list[dict[str, Any]]: return []
    def get_release(self, release_id: str | int) -> dict[str, Any]:
        return self.client.get_json(f"https://api.spotify.com/v1/albums/{release_id}", headers={"Authorization": f"Bearer {self._ensure_token()}"})
    def _album_to_row(self, a: dict[str, Any], barcode: str) -> dict[str, Any]:
        imgs=a.get("images") or []; ext=a.get("external_ids") or {}; url=(a.get("external_urls") or {}).get("spotify", "")
        return with_base({"Spotify Album ID": a.get("id",""), "Spotify URI": a.get("uri",""), "Spotify URL": url, "UPC": ext.get("upc", barcode), "Album type": a.get("album_type",""), "Release date precision": a.get("release_date_precision",""), "Total tracks": a.get("total_tracks",""), "Copyrights": "; ".join(c.get("text","") for c in a.get("copyrights") or []), "Genres where available": "; ".join(a.get("genres") or []), "Available markets where available": "; ".join(a.get("available_markets") or []), "Popularity where available": a.get("popularity", ""), "Image dimensions": "; ".join(f"{i.get('width')}x{i.get('height')}" for i in imgs), "Track listing": " | ".join(t.get("name","") for t in ((a.get("tracks") or {}).get("items") or [])), "External identifiers": str(ext)}, Source="Spotify", **{"Lookup UPC/EAN": barcode, "Source Record ID": a.get("id",""), "Source Record URL": url, "Artist": "; ".join(x.get("name","") for x in a.get("artists") or []), "Title": a.get("name",""), "Label": a.get("label",""), "Release Date": a.get("release_date",""), "Barcode": ext.get("upc", barcode), "Main Image URL": imgs[0].get("url","") if imgs else "", "Additional Image URLs": "; ".join(i.get("url","") for i in imgs[1:])})
