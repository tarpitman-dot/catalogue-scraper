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

def _patch_streamlit_progress(monkeypatch):
    import app
    monkeypatch.setattr(app.st, "progress", lambda x: type("P", (), {"progress": lambda self, y: None})())
    monkeypatch.setattr(app.st, "empty", lambda: type("E", (), {"write": lambda self, x: None, "empty": lambda self: None})())


def test_bulk_found_rows_fallback_source_for_missing_none_empty_and_whitespace(monkeypatch):
    import pandas as pd, app
    _patch_streamlit_progress(monkeypatch)
    records = [{"Title": "missing"}, {"Source": None, "Title": "none"}, {"Source": "", "Title": "empty"}, {"Source": "   ", "Title": "space"}]
    monkeypatch.setattr(app, "lookup_barcode", lambda source_key, barcode, settings: records)
    monkeypatch.setitem(app.SOURCE_REGISTRY, "fake", type("D", (), {"display_name": "Fallback Source"})())

    df = run_bulk_lookup(["fake"], pd.DataFrame([{"UPC": "123"}]), "UPC", {})

    assert list(df["Source"]) == ["Fallback Source"] * 4
    app.validate_found_row_sources(df)


def test_bulk_found_rows_preserve_valid_source_specific_value(monkeypatch):
    import pandas as pd, app
    _patch_streamlit_progress(monkeypatch)
    monkeypatch.setattr(app, "lookup_barcode", lambda source_key, barcode, settings: [{"Source": "Specific Source", "Title": "ok"}])
    monkeypatch.setitem(app.SOURCE_REGISTRY, "fake", type("D", (), {"display_name": "Fallback Source"})())

    df = run_bulk_lookup(["fake"], pd.DataFrame([{"UPC": "123"}]), "UPC", {})

    assert df.iloc[0]["Source"] == "Specific Source"


def test_single_lookup_row_builder_fallback_and_validation():
    from app import found_result_row, validate_found_row_sources
    import pandas as pd

    rows = [
        found_result_row({"Lookup Status": "Found"}, {"Title": "missing"}, "Discogs"),
        found_result_row({"Lookup Status": "Found"}, {"Source": None}, "Discogs"),
        found_result_row({"Lookup Status": "Found"}, {"Source": ""}, "Discogs"),
        found_result_row({"Lookup Status": "Found"}, {"Source": "Spotify"}, "Discogs"),
    ]

    assert [row["Source"] for row in rows] == ["Discogs", "Discogs", "Discogs", "Spotify"]
    validate_found_row_sources(pd.DataFrame(rows))


def test_export_validation_rejects_blank_found_source():
    import pandas as pd
    from app import validate_found_row_sources

    for source in [None, "", "   "]:
        try:
            validate_found_row_sources(pd.DataFrame([{"Lookup Status": "Found", "Source": source}]))
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected blank source {source!r} to fail validation")


def test_with_base_protects_source_and_common_record_fields_from_metadata_overwrite():
    from sources.schema import with_base

    row = with_base(
        {"Source": "", "Source Record ID": "", "Source Record URL": "", "Title": "Album"},
        Source="Discogs",
        **{"Source Record ID": "123", "Source Record URL": "https://example.test/release/123"},
    )

    assert row["Source"] == "Discogs"
    assert row["Source Record ID"] == "123"
    assert row["Source Record URL"] == "https://example.test/release/123"


def test_musicbrainz_source_with_and_without_artwork():
    art = {"images": [{"image": "full1", "front": True, "types": ["Front"], "thumbnails": {}}]}
    no_art_error = SourceError("Cover Art Archive request failed (404): missing")
    mb_data = {"releases": [{"id": "with-art", "title": "A", "barcode": "123"}, {"id": "without-art", "title": "B", "barcode": "123"}]}
    rows = MusicBrainzConnector(client=QueueClient([mb_data]), cover_art=CoverArtArchiveClient("ua", QueueClient([art, no_art_error]))).lookup("123")

    assert rows[0]["Source"] == "MusicBrainz + Cover Art Archive"
    assert rows[0]["Main Image URL"] == "full1"
    assert rows[1]["Source"] == "MusicBrainz"
    assert rows[1]["Main Image URL"] == ""


def test_discogs_connector_explicit_source_and_common_fields():
    from sources.discogs import DiscogsConfig, DiscogsConnector

    discogs = DiscogsConnector.__new__(DiscogsConnector)
    discogs.config = DiscogsConfig("token")
    discogs.include_tracklist = discogs.include_notes = discogs.include_companies = discogs.include_videos = False
    discogs.include_identifiers = True
    row = discogs._release_to_row({"id": 7, "uri": "https://discogs.test/release/7", "title": "D"}, "123")

    assert row["Source"] == "Discogs"
    assert row["Source Record ID"] == 7
    assert row["Source Record URL"] == "https://discogs.test/release/7"


def test_multi_source_bulk_export_contains_correct_sources(monkeypatch):
    import pandas as pd, app
    _patch_streamlit_progress(monkeypatch)

    def fake_lookup(source_key, barcode, settings):
        return {
            "discogs": [{"Source": "", "Title": "D"}],
            "musicbrainz": [{"Source": "MusicBrainz", "Title": "M"}],
            "spotify": [{"Source": None, "Title": "S"}],
        }[source_key]

    monkeypatch.setattr(app, "lookup_barcode", fake_lookup)
    monkeypatch.setitem(app.SOURCE_REGISTRY, "discogs", type("D", (), {"display_name": "Discogs"})())
    monkeypatch.setitem(app.SOURCE_REGISTRY, "musicbrainz", type("D", (), {"display_name": "MusicBrainz + Cover Art Archive"})())
    monkeypatch.setitem(app.SOURCE_REGISTRY, "spotify", type("D", (), {"display_name": "Spotify"})())

    df = run_bulk_lookup(["discogs", "musicbrainz", "spotify"], pd.DataFrame([{"UPC": "123"}]), "UPC", {})

    assert list(df["Source"]) == ["Discogs", "MusicBrainz", "Spotify"]
    app.validate_found_row_sources(df)


def test_found_result_row_protects_lookup_metadata_from_blank_connector_fields():
    from app import found_result_row

    row = found_result_row(
        {"Lookup UPC/EAN": "123", "Lookup Status": "Found", "Result Number": 2, "Results For Barcode": 4, "Input": "keep"},
        {"Source": "", "Lookup UPC/EAN": "", "Lookup Status": "", "Result Number": "", "Results For Barcode": "", "Title": "Album"},
        "Discogs",
    )

    assert row["Source"] == "Discogs"
    assert row["Lookup UPC/EAN"] == "123"
    assert row["Lookup Status"] == "Found"
    assert row["Result Number"] == 2
    assert row["Results For Barcode"] == 4
    assert row["Input"] == "keep"


def test_found_result_row_preserves_valid_connector_source_values():
    from app import found_result_row

    assert found_result_row({"Lookup Status": "Found"}, {"Source": "MusicBrainz + Cover Art Archive"}, "MusicBrainz")["Source"] == "MusicBrainz + Cover Art Archive"
    assert found_result_row({"Lookup Status": "Found"}, {"Source": "iTunes Lookup"}, "Apple Music / iTunes")["Source"] == "iTunes Lookup"


def test_with_base_does_not_add_blank_orchestration_fields_without_values():
    from sources.schema import with_base

    row = with_base({"Title": "Album"})

    assert "Source" not in row
    assert "Lookup UPC/EAN" not in row
    assert "Lookup Status" not in row
    assert "Result Number" not in row
    assert "Results For Barcode" not in row


def test_discogs_found_row_keeps_found_status_and_is_counted_and_validated(monkeypatch):
    import pandas as pd, app
    from sources.discogs import DiscogsConfig, DiscogsConnector

    _patch_streamlit_progress(monkeypatch)
    discogs = DiscogsConnector.__new__(DiscogsConnector)
    discogs.config = DiscogsConfig("token")
    discogs.include_tracklist = discogs.include_notes = discogs.include_companies = discogs.include_videos = False
    discogs.include_identifiers = True
    record = discogs._release_to_row({"id": 7, "uri": "https://discogs.test/release/7", "title": "D"}, "123")
    record.update({"Lookup Status": "", "Result Number": "", "Results For Barcode": ""})

    monkeypatch.setattr(app, "lookup_barcode", lambda source_key, barcode, settings: [record])
    monkeypatch.setitem(app.SOURCE_REGISTRY, "discogs", type("D", (), {"display_name": "Discogs"})())

    df = run_bulk_lookup(["discogs"], pd.DataFrame([{"UPC": "123"}]), "UPC", {})

    assert df.iloc[0]["Source"] == "Discogs"
    assert df.iloc[0]["Lookup Status"] == "Found"
    assert int((df["Lookup Status"] == "Found").sum()) == 1
    app.validate_found_row_sources(df)


def test_apple_artist_search_uses_artist_term_and_rejects_title_only_match():
    client = QueueClient([{"results": [{"collectionId": 1, "collectionName": "Burial", "artistName": "Unrelated"}]}])

    rows = AppleConnector(AppleConfig("", "gb"), client).search_by_type("artist", "Burial")

    assert rows == []
    assert client.calls[0][1]["params"]["attribute"] == "artistTerm"
    assert client.calls[0][1]["params"]["entity"] == "album"


def test_apple_artist_search_keeps_exact_case_insensitive_and_collaboration_matches():
    client = QueueClient([{"results": [
        {"collectionId": 1, "collectionName": "A", "artistName": "Burial"},
        {"collectionId": 2, "collectionName": "B", "artistName": " burial "},
        {"collectionId": 3, "collectionName": "C", "artistName": "Four Tet & Burial"},
        {"collectionId": 4, "collectionName": "Burial", "artistName": "Different Artist"},
    ]}])

    rows = AppleConnector(AppleConfig("", "gb"), client).search_by_type("artist", " Burial ")

    assert [row["Artist"] for row in rows] == ["Burial", " burial ", "Four Tet & Burial"]


def test_apple_music_artist_search_filters_album_results_by_artist_credit():
    client = QueueClient([{"results": {"albums": {"data": [
        {"id": "1", "attributes": {"name": "Burial", "artistName": "Other", "artwork": {}}},
        {"id": "2", "attributes": {"name": "A", "artistName": "Burial & Four Tet", "artwork": {}}},
    ]}}}])

    rows = AppleConnector(AppleConfig("dev", "gb"), client).search_by_type("artist", "burial")

    assert [row["Source Record ID"] for row in rows] == ["2"]
    assert client.calls[0][0] == "https://api.music.apple.com/v1/catalog/gb/search"
    assert client.calls[0][1]["params"]["types"] == "albums"


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _discogs_for_test(responses):
    from sources.discogs import DiscogsConfig, DiscogsConnector
    discogs = DiscogsConnector(DiscogsConfig("token", max_retries=2, min_retry_delay=0, max_retry_delay=0))
    discogs.session = FakeSession(responses)
    return discogs


def test_discogs_first_429_retries_and_succeeds(monkeypatch):
    import sources.discogs as discogs_module
    monkeypatch.setattr(discogs_module.time, "sleep", lambda delay: None)
    discogs = _discogs_for_test([
        FakeResponse(429, headers={"Retry-After": "0"}),
        FakeResponse(200, {"ok": True}),
    ])

    assert discogs._get("/database/search") == {"ok": True}
    assert len(discogs.session.calls) == 2


def test_discogs_repeated_429_exhausts_retries(monkeypatch):
    import sources.discogs as discogs_module
    monkeypatch.setattr(discogs_module.time, "sleep", lambda delay: None)
    discogs = _discogs_for_test([FakeResponse(429), FakeResponse(429), FakeResponse(429)])

    try:
        discogs._get("/database/search")
    except SourceError as exc:
        assert "after retries" in str(exc)
    else:
        raise AssertionError("Expected Discogs 429 retries to exhaust")
    assert len(discogs.session.calls) == 3


def test_discogs_duplicate_release_ids_are_fetched_once():
    discogs = _discogs_for_test([
        FakeResponse(200, {"results": [{"id": 7}, {"id": 7}], "pagination": {"pages": 1}}),
        FakeResponse(200, {"id": 7, "title": "D"}),
    ])

    rows = discogs.lookup("123")

    assert len(rows) == 1
    assert [call[0] for call in discogs.session.calls].count("https://api.discogs.com/releases/7") == 1


def test_discogs_cached_release_results_are_reused():
    discogs = _discogs_for_test([FakeResponse(200, {"id": 7, "title": "D"})])

    assert discogs.get_release(7)["id"] == 7
    assert discogs.get_release("7")["id"] == 7
    assert len(discogs.session.calls) == 1


def test_bulk_successful_non_discogs_sources_still_return_when_discogs_fails(monkeypatch):
    import pandas as pd, app
    _patch_streamlit_progress(monkeypatch)
    def fake_lookup(source_key, barcode, settings):
        if source_key == "discogs":
            raise SourceError("Discogs rate limit reached after retries; please try again later.")
        return [{"Source": "Spotify", "Title": "ok"}]
    monkeypatch.setattr(app, "lookup_barcode", fake_lookup)
    monkeypatch.setitem(app.SOURCE_REGISTRY, "discogs", type("D", (), {"display_name": "Discogs"})())
    monkeypatch.setitem(app.SOURCE_REGISTRY, "spotify", type("D", (), {"display_name": "Spotify"})())

    df = run_bulk_lookup(["discogs", "spotify"], pd.DataFrame([{"UPC": "123"}]), "UPC", {})

    assert list(df["Source"]) == ["Discogs", "Spotify"]
    assert list(df["Lookup Status"]) == ["Source error", "Found"]


def test_bulk_lookup_preserves_earlier_successful_rows_after_later_discogs_failure(monkeypatch):
    import pandas as pd, app
    _patch_streamlit_progress(monkeypatch)
    def fake_lookup(source_key, barcode, settings):
        if barcode == "222":
            raise SourceError("Discogs rate limit reached after retries; please try again later.")
        return [{"Source": "Discogs", "Title": "first"}]
    monkeypatch.setattr(app, "lookup_barcode", fake_lookup)
    monkeypatch.setitem(app.SOURCE_REGISTRY, "discogs", type("D", (), {"display_name": "Discogs"})())

    df = run_bulk_lookup(["discogs"], pd.DataFrame([{"UPC": "111"}, {"UPC": "222"}]), "UPC", {})

    assert list(df["Lookup Status"]) == ["Found", "Source error"]
    assert df.iloc[0]["Title"] == "first"

def test_apple_music_catalog_search_limit_never_exceeds_25_for_artist_and_title():
    client = QueueClient([
        {"results": {"albums": {"data": []}}},
        {"results": {"albums": {"data": []}}},
    ])
    apple = AppleConnector(AppleConfig("dev", "gb"), client)

    apple.search_by_type("artist", "Burial")
    apple.search_by_type("title", "Untrue")

    limits = [int(call[1]["params"]["limit"]) for call in client.calls]
    assert limits == [25, 25]
    assert all(limit <= 25 for limit in limits)


def test_itunes_search_limit_stays_independent_at_200():
    client = QueueClient([{"results": []}])

    AppleConnector(AppleConfig("", "gb"), client).search_by_type("artist", "Burial")

    assert client.calls[0][1]["params"]["limit"] == "200"


def test_apple_music_search_paginates_without_exceeding_25():
    page = [{"id": str(i), "attributes": {"name": f"A{i}", "artistName": "Burial", "artwork": {}}} for i in range(25)]
    client = QueueClient([
        {"results": {"albums": {"data": page, "next": "/next"}}},
        {"results": {"albums": {"data": [{"id": "26", "attributes": {"name": "A26", "artistName": "Burial", "artwork": {}}}]}}},
    ])

    rows = AppleConnector(AppleConfig("dev", "gb"), client).search_by_type("artist", "Burial")

    assert len(rows) == 26
    assert [int(call[1]["params"]["limit"]) for call in client.calls] == [25, 25]
    assert client.calls[1][1]["params"]["offset"] == "25"


def test_discogs_broad_artist_search_uses_summary_rows_without_release_fetch():
    discogs = _discogs_for_test([
        FakeResponse(200, {"results": [{"id": 7, "title": "Burial - Untrue", "label": ["Hyperdub"], "catno": ["HDBCD002"], "format": ["CD"], "year": "2007", "cover_image": "img"}], "pagination": {"pages": 1}}),
    ])

    rows = discogs.search_by_type("artist", "Burial")

    assert len(rows) == 1
    assert rows[0]["Artist"] == "Burial"
    assert rows[0]["Title"] == "Untrue"
    assert len(discogs.session.calls) == 1


def test_discogs_detail_option_fetches_duplicate_release_once_for_broad_search():
    discogs = _discogs_for_test([
        FakeResponse(200, {"results": [{"id": 7}, {"id": 7}], "pagination": {"pages": 1}}),
        FakeResponse(200, {"id": 7, "title": "D"}),
    ])
    discogs.include_tracklist = True

    rows = discogs.search_by_type("artist", "Burial")

    assert len(rows) == 1
    assert [call[0] for call in discogs.session.calls].count("https://api.discogs.com/releases/7") == 1


def test_single_lookup_status_rows_are_not_rendered_as_result_cards(monkeypatch):
    import pandas as pd, app
    calls = {"subheader": [], "error": [], "info": []}
    monkeypatch.setattr(app.st, "subheader", lambda value: calls["subheader"].append(value))
    monkeypatch.setattr(app.st, "error", lambda value: calls["error"].append(value))
    monkeypatch.setattr(app.st, "info", lambda value: calls["info"].append(value))

    app.render_single_result_cards(pd.DataFrame([{"Source": "Discogs", "Lookup Status": "Source error", "Error": "Discogs rate limit reached."}]))

    assert calls["subheader"] == []
    assert calls["error"] == ["Discogs: Source error — Discogs rate limit reached."]
