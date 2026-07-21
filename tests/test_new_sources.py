from __future__ import annotations

from app import run_bulk_lookup
from sources.apple import AppleConfig, AppleConnector
from sources.base import SourceError
from sources.musicbrainz import CoverArtArchiveClient, MusicBrainzConnector
from sources.registry import SOURCE_REGISTRY
from sources.spotify import SpotifyConfig, SpotifyConnector

class FakeClient:
    def __init__(self, responses): self.responses=list(responses); self.calls=[]
    def get_json(self, url, **kwargs): self.calls.append(("GET", url, kwargs)); r=self.responses.pop(0); 
    def post_json(self, url, **kwargs): self.calls.append(("POST", url, kwargs)); return self.responses.pop(0)

class QueueClient:
    def __init__(self, responses): self.responses=list(responses); self.calls=[]
    def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs)); r=self.responses.pop(0)
        if isinstance(r, Exception): raise r
        return r
    def post_json(self, url, **kwargs): self.calls.append((url, kwargs)); return self.responses.pop(0)

def test_musicbrainz_exact_barcode_query_and_multiple_results():
    cover = CoverArtArchiveClient("ua", QueueClient([SourceError("Cover Art Archive request failed (404): nope"), SourceError("Cover Art Archive request failed (404): nope")]))
    client = QueueClient([{"releases":[{"id":"r1","title":"A","barcode":"123"},{"id":"r2","title":"B","barcode":"123"}]}])
    rows = MusicBrainzConnector(client=client, cover_art=cover).lookup("123")
    assert client.calls[0][1]["params"]["query"] == 'barcode:"123"'
    assert [r["MusicBrainz Release ID"] for r in rows] == ["r1", "r2"]

def test_cover_art_archive_extraction_and_missing_response():
    data={"images":[{"image":"full1","front":True,"types":["Front"],"thumbnails":{"250":"t250","500":"t500","1200":"t1200"}},{"image":"full2","back":True,"types":["Back"],"thumbnails":{}}]}
    row=CoverArtArchiveClient("ua", QueueClient([data])).lookup("rel")
    assert row["Main Image URL"] == "full1" and row["Thumbnail URL 500"] == "t500" and row["Back Image URL"] == "full2"
    missing=CoverArtArchiveClient("ua", QueueClient([SourceError("Cover Art Archive request failed (404): missing")])).lookup("rel")
    assert missing["Image count"] == 0

def test_spotify_query_token_and_expiry():
    client=QueueClient([{"access_token":"tok","expires_in":3600},{"albums":{"items":[{"id":"a","name":"Album","external_urls":{"spotify":"url"},"external_ids":{"upc":"123"}}]}}])
    sp=SpotifyConnector(SpotifyConfig("id","secret","GB"), client)
    rows=sp.lookup("123")
    assert client.calls[0][0] == "https://accounts.spotify.com/api/token"
    assert client.calls[1][1]["params"]["q"] == "upc:123"
    assert rows[0]["Source"] == "Spotify"

def test_apple_request_and_itunes_fallback():
    apple_client=QueueClient([{"data":[{"id":"1","attributes":{"name":"A","artistName":"B","url":"u","artwork":{"url":"http://x/{w}x{h}.jpg"}}}]}])
    apple=AppleConnector(AppleConfig("dev","gb"), apple_client)
    assert apple.lookup("123")[0]["Source"] == "Apple Music"
    assert apple_client.calls[0][1]["params"]["filter[upc]"] == "123"
    it_client=QueueClient([{"results":[{"wrapperType":"collection","collectionId":2,"collectionName":"I","artistName":"B"}]}])
    assert AppleConnector(AppleConfig("","gb"), it_client).lookup("123")[0]["Source"] == "iTunes Lookup"
    assert it_client.calls[0][1]["params"]["upc"] == "123"

def test_registry_constructor_compatibility_and_missing_credentials_state():
    for key in ["discogs","musicbrainz","spotify","apple"]:
        settings={"token":"x"} if key=="discogs" else {}
        assert SOURCE_REGISTRY[key].create_connector(settings)
    assert not SpotifyConnector(SpotifyConfig()).configured

def test_failing_source_does_not_prevent_another(monkeypatch):
    import pandas as pd, app
    monkeypatch.setattr(app.st, "progress", lambda x: type("P",(),{"progress":lambda self,y:None})())
    monkeypatch.setattr(app.st, "empty", lambda: type("E",(),{"write":lambda self,x:None,"empty":lambda self:None})())
    def fake_lookup(source_key, barcode, settings):
        if source_key == "bad": raise SourceError("boom")
        return [{"Source":"Good","Title":"ok"}]
    monkeypatch.setattr(app, "lookup_barcode", fake_lookup)
    monkeypatch.setitem(app.SOURCE_REGISTRY, "bad", type("D",(),{"display_name":"Bad"})())
    monkeypatch.setitem(app.SOURCE_REGISTRY, "good", type("D",(),{"display_name":"Good"})())
    df=run_bulk_lookup(["bad","good"], pd.DataFrame([{"UPC":"123","Input":"keep"}]), "UPC", {})
    assert set(df["Source"]) == {"Bad", "Good"}
    assert "Input" in df.columns
