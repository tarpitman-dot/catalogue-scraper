from __future__ import annotations

import pandas as pd

from app import result_sources_with_rows, safe_source_filename, source_specific_results
from sources.lookup import normalise_lookup_value


def test_source_specific_export_contains_only_that_source_and_all_combined_rows() -> None:
    df = pd.DataFrame([
        {"Input Col": "a", "Source": "Discogs", "Title": "A"},
        {"Input Col": "b", "Source": "MusicBrainz + Cover Art Archive", "Title": "B"},
        {"Input Col": "c", "Source": "Spotify", "Title": "C"},
    ])

    assert len(df) == 3
    assert result_sources_with_rows(df) == ["Discogs", "MusicBrainz + Cover Art Archive", "Spotify"]
    mb = source_specific_results(df, "MusicBrainz + Cover Art Archive")
    assert mb["Source"].unique().tolist() == ["MusicBrainz + Cover Art Archive"]
    assert mb["Input Col"].tolist() == ["b"]


def test_buttons_hidden_for_sources_with_no_rows() -> None:
    df = pd.DataFrame([{"Source": "Discogs"}])
    assert result_sources_with_rows(df) == ["Discogs"]
    assert source_specific_results(df, "Spotify").empty


def test_safe_predictable_source_filenames() -> None:
    assert safe_source_filename("Discogs") == "discogs"
    assert safe_source_filename("MusicBrainz + Cover Art Archive") == "musicbrainz_cover_art_archive"
    assert safe_source_filename("Apple Music / iTunes") == "apple_music_itunes"
    assert safe_source_filename("iTunes Lookup") == "itunes_lookup"


def test_lookup_normalisation_preserves_expected_values() -> None:
    assert normalise_lookup_value("barcode", " 00-123 456 ")[0] == "00123456"
    assert normalise_lookup_value("catalogue_number", "  ABC-001/7 ")[0] == "ABC-001/7"
    assert normalise_lookup_value("isrc", "us-abc 12-34567")[0] == "USABC1234567"
