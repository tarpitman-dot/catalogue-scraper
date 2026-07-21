from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Any
from sources.base import CatalogueSource
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
    def search_by_type(self, lookup_type: str, value: str) -> list[dict[str,Any]]:
        term = value if lookup_type != "isrc" else value
        entity = "song" if lookup_type == "isrc" else "album"
        data=self.client.get_json("https://itunes.apple.com/search", params={"term": term, "entity": entity, "limit": "200"})
        return [self._itunes_row(x, value) for x in data.get("results") or []]
    def search(self,text:str)->list[dict[str,Any]]: return []
    def get_release(self, release_id: str|int)->dict[str,Any]: return {}
    def _art(self, artwork:dict[str,Any])->tuple[str,str]:
        tmpl=artwork.get("url",""); return tmpl, tmpl.replace("{w}","3000").replace("{h}","3000")
    def _apple_row(self,a:dict[str,Any],barcode:str)->dict[str,Any]:
        at=a.get("attributes") or {}; tmpl,large=self._art(at.get("artwork") or {}); url=at.get("url","")
        return with_base({"Apple Music Album ID": a.get("id",""), "Apple Music URL": url, "UPC": at.get("upc", barcode), "Record label": at.get("recordLabel", ""), "Genre names": "; ".join(at.get("genreNames") or []), "Copyright": at.get("copyright", ""), "Editorial notes where available": str(at.get("editorialNotes") or ""), "Track count": at.get("trackCount", ""), "Content rating": at.get("contentRating", ""), "Compilation status": at.get("isCompilation", ""), "Single status": at.get("isSingle", ""), "Artwork URL template": tmpl, "Resolved high-resolution artwork URL": large}, Source="Apple Music", **{"Lookup UPC/EAN":barcode,"Source Record ID":a.get("id",""),"Source Record URL":url,"Artist":at.get("artistName",""),"Title":at.get("name",""),"Label":at.get("recordLabel",""),"Release Date":at.get("releaseDate",""),"Barcode":at.get("upc",barcode),"Main Image URL":large, "Result Entity Type": "Release"})
    def _itunes_row(self,a:dict[str,Any],barcode:str)->dict[str,Any]:
        return with_base({"iTunes Collection ID": a.get("collectionId",""), "iTunes Lookup URL": a.get("collectionViewUrl", ""), "UPC": barcode, "Genre names": a.get("primaryGenreName", ""), "Track count": a.get("trackCount", ""), "Copyright": a.get("copyright", ""), "Artwork URL template": a.get("artworkUrl100", ""), "Resolved high-resolution artwork URL": str(a.get("artworkUrl100","")).replace("100x100bb", "1200x1200bb")}, Source="iTunes Lookup", **{"Lookup UPC/EAN":barcode,"Source Record ID":a.get("collectionId",""),"Source Record URL":a.get("collectionViewUrl",""),"Artist":a.get("artistName",""),"Title":a.get("collectionName",""),"Label":a.get("collectionCensoredName",""),"Release Date":a.get("releaseDate",""),"Barcode":barcode,"Main Image URL":str(a.get("artworkUrl100","")).replace("100x100bb", "1200x1200bb"), "Result Entity Type": "Release"})
