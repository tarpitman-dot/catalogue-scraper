from __future__ import annotations
import os
from dataclasses import dataclass
import re
from typing import Any
from sources.base import CatalogueSource, SourceCapabilities
from sources.http import HttpClient
from sources.schema import with_base

@dataclass(frozen=True)
class AppleConfig:
    developer_token: str = ""; storefront: str = "gb"
    @classmethod
    def from_settings(cls, s: dict[str, Any]) -> "AppleConfig":
        return cls(str(s.get("developer_token") or os.getenv("APPLE_MUSIC_DEVELOPER_TOKEN") or ""), str(s.get("storefront") or os.getenv("APPLE_MUSIC_STOREFRONT") or "gb"))

class AppleConnector(CatalogueSource):
    source_name = "Apple Music / iTunes"
    supported_lookup_types = {"barcode", "isrc", "artist", "title"}
    APPLE_MUSIC_CATALOG_SEARCH_LIMIT = 25
    ITUNES_SEARCH_LIMIT = 200
    capabilities = SourceCapabilities(frozenset(supported_lookup_types), max_page_size=25, supports_pagination=True, credentials_required=False, rate_limit="Apple Music Catalog Search limit capped at 25; iTunes uses an independent limit.")
    def __init__(self, config: AppleConfig | None = None, client: HttpClient | None = None):
        self.config=config or AppleConfig.from_settings({}); self.client=client or HttpClient("Apple", "CatalogueScraper/2.0")
    @property
    def configured(self)->bool: return bool(self.config.developer_token)
    def _apple_url(self, barcode:str)->str: return f"https://api.music.apple.com/v1/catalog/{self.config.storefront}/albums"
    def _apple_params(self, barcode:str)->dict[str,str]: return {"filter[upc]": barcode, "include": "tracks"}
    def _itunes_params(self, barcode:str)->dict[str,str]: return {"upc": barcode, "entity": "album"}
    def lookup(self, barcode: str) -> list[dict[str, Any]]:
        if self.configured:
            data=self.client.get_json(self._apple_url(barcode), params=self._apple_params(barcode), headers={"Authorization": f"Bearer {self.config.developer_token}"})
            return [self._apple_row(x, barcode) for x in data.get("data") or []]
        data=self.client.get_json("https://itunes.apple.com/lookup", params=self._itunes_params(barcode))
        return [self._itunes_row(x, barcode) for x in data.get("results") or [] if x.get("wrapperType") in ("collection", None)]
    @staticmethod
    def _normalise_artist(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

    @classmethod
    def _artist_matches(cls, searched_artist: str, returned_artist: str) -> bool:
        needle = cls._normalise_artist(searched_artist)
        haystack = cls._normalise_artist(returned_artist)
        if not needle or not haystack:
            return False
        if needle == haystack:
            return True
        parts = [part.strip() for part in re.split(r"\s*(?:&|,|/|\+|;|\band\b|\bfeat\.?\b|\bfeaturing\b|\bwith\b)\s*", haystack, flags=re.IGNORECASE) if part.strip()]
        return needle in parts

    def _apple_search_url(self) -> str:
        return f"https://api.music.apple.com/v1/catalog/{self.config.storefront}/search"

    def _apple_search_params(self, lookup_type: str, value: str, *, offset: int = 0, limit: int | None = None) -> dict[str, str]:
        page_limit = min(limit or self.APPLE_MUSIC_CATALOG_SEARCH_LIMIT, self.APPLE_MUSIC_CATALOG_SEARCH_LIMIT)
        if lookup_type in {"artist", "title"}:
            params = {"term": value.strip(), "types": "albums", "limit": str(page_limit)}
            if offset:
                params["offset"] = str(offset)
            return params
        return {}

    def _itunes_search_params(self, lookup_type: str, value: str) -> dict[str, str]:
        if lookup_type == "artist":
            return {"term": value.strip(), "attribute": "artistTerm", "entity": "album", "limit": str(self.ITUNES_SEARCH_LIMIT)}
        if lookup_type == "isrc":
            return {"term": value.strip(), "entity": "song", "limit": str(self.ITUNES_SEARCH_LIMIT)}
        return {"term": value.strip(), "entity": "album", "limit": str(self.ITUNES_SEARCH_LIMIT)}

    def _apple_search_pages(self, lookup_type: str, value: str, requested_limit: int = 200) -> list[dict[str, Any]]:
        albums: list[dict[str, Any]] = []
        offset = 0
        while len(albums) < requested_limit:
            params = self._apple_search_params(lookup_type, value, offset=offset, limit=requested_limit - len(albums))
            data = self.client.get_json(self._apple_search_url(), params=params, headers={"Authorization": f"Bearer {self.config.developer_token}"})
            album_block = ((data.get("results") or {}).get("albums") or {})
            page = album_block.get("data") or []
            albums.extend(page)
            if not page or not album_block.get("next") or len(page) < self.APPLE_MUSIC_CATALOG_SEARCH_LIMIT:
                break
            offset += len(page)
        return albums[:requested_limit]

    def search_by_type(self, lookup_type: str, value: str) -> list[dict[str,Any]]:
        if self.configured and lookup_type in {"artist", "title"}:
            rows = [self._apple_row(x, value) for x in self._apple_search_pages(lookup_type, value)]
        else:
            params = self._itunes_search_params(lookup_type, value)
            data=self.client.get_json("https://itunes.apple.com/search", params=params)
            rows = [self._itunes_row(x, value) for x in data.get("results") or []]
        if lookup_type == "artist":
            return [row for row in rows if self._artist_matches(value, row.get("Artist", ""))]
        return rows
    def search(self,text:str)->list[dict[str,Any]]: return []
    def get_release(self, release_id: str|int)->dict[str,Any]: return {}
    def _art(self, artwork:dict[str,Any])->tuple[str,str]:
        tmpl=artwork.get("url",""); return tmpl, tmpl.replace("{w}","3000").replace("{h}","3000")
    def _apple_row(self,a:dict[str,Any],barcode:str)->dict[str,Any]:
        at=a.get("attributes") or {}; tmpl,large=self._art(at.get("artwork") or {}); url=at.get("url","")
        return with_base({"Apple Music Album ID": a.get("id",""), "Apple Music URL": url, "UPC": at.get("upc", barcode), "Record label": at.get("recordLabel", ""), "Genre names": "; ".join(at.get("genreNames") or []), "Copyright": at.get("copyright", ""), "Editorial notes where available": str(at.get("editorialNotes") or ""), "Track count": at.get("trackCount", ""), "Content rating": at.get("contentRating", ""), "Compilation status": at.get("isCompilation", ""), "Single status": at.get("isSingle", ""), "Artwork URL template": tmpl, "Resolved high-resolution artwork URL": large}, Source="Apple Music", **{"Lookup UPC/EAN":barcode,"Source Record ID":a.get("id",""),"Source Record URL":url,"Artist":at.get("artistName",""),"Title":at.get("name",""),"Label":at.get("recordLabel",""),"Release Date":at.get("releaseDate",""),"Barcode":at.get("upc",barcode),"Main Image URL":large, "Result Entity Type": "Release"})
    def _itunes_row(self,a:dict[str,Any],barcode:str)->dict[str,Any]:
        return with_base({"iTunes Collection ID": a.get("collectionId",""), "iTunes Lookup URL": a.get("collectionViewUrl", ""), "UPC": barcode, "Genre names": a.get("primaryGenreName", ""), "Track count": a.get("trackCount", ""), "Copyright": a.get("copyright", ""), "Artwork URL template": a.get("artworkUrl100", ""), "Resolved high-resolution artwork URL": str(a.get("artworkUrl100","")).replace("100x100bb", "1200x1200bb")}, Source="iTunes Lookup", **{"Lookup UPC/EAN":barcode,"Source Record ID":a.get("collectionId",""),"Source Record URL":a.get("collectionViewUrl",""),"Artist":a.get("artistName",""),"Title":a.get("collectionName",""),"Label":a.get("collectionCensoredName",""),"Release Date":a.get("releaseDate",""),"Barcode":barcode,"Main Image URL":str(a.get("artworkUrl100","")).replace("100x100bb", "1200x1200bb"), "Result Entity Type": "Release"})
