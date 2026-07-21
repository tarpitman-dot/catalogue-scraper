# Catalogue Scraper

Catalogue Scraper is a Streamlit multi-source catalogue research platform for single UPC/EAN lookups and bulk metadata enrichment. It keeps source results separate: there is no automatic matching, merging, confidence scoring, or deduplication.

## Supported sources

- **Discogs**: connected when `DISCOGS_TOKEN` is configured.
- **MusicBrainz**: available without private credentials. Uses exact barcode searches against the official JSON web service.
- **Cover Art Archive**: available without private credentials as MusicBrainz artwork enrichment. Missing artwork is normal and does not fail the release result.
- **Spotify**: optional; connected when `SPOTIFY_CLIENT_ID` and `SPOTIFY_CLIENT_SECRET` are configured. Uses client-credentials auth and UPC album search.
- **Apple Music**: optional; connected when `APPLE_MUSIC_DEVELOPER_TOKEN` is configured.
- **iTunes Lookup**: public fallback when no Apple Music developer token is configured.
- **Amazon**: retained in the registry as planned / awaiting credentials and intentionally disabled.

## Output model

All connectors share a small base schema for exports:

`Source`, `Lookup UPC/EAN`, `Source Record ID`, `Source Record URL`, `Artist`, `Title`, `Label`, `Catalogue Number`, `Format`, `Country`, `Release Date`, `Barcode`, `Main Image URL`, `Additional Image URLs`, `Result Number`, `Results For Barcode`, `Lookup Status`, and `Error`.

Source-specific metadata is added in extra columns. Original uploaded columns are preserved in bulk exports. Image fields are direct URLs only; images are not downloaded or stored.

## Credentials and configuration

Catalogue Scraper reads Streamlit Secrets first, then environment variables.

```toml
DISCOGS_TOKEN = "your-discogs-token"

MUSICBRAINZ_APP_NAME = "CatalogueScraper"
MUSICBRAINZ_APP_VERSION = "2.0"
MUSICBRAINZ_CONTACT = "you@example.com"

SPOTIFY_CLIENT_ID = "your-spotify-client-id"
SPOTIFY_CLIENT_SECRET = "your-spotify-client-secret"
SPOTIFY_MARKET = "GB"

APPLE_MUSIC_DEVELOPER_TOKEN = "your-apple-music-developer-token"
APPLE_MUSIC_STOREFRONT = "gb"
```

MusicBrainz requires a meaningful User-Agent. App name and version have safe defaults; set `MUSICBRAINZ_CONTACT` for best compliance.

## Search modes

- **Single Lookup**: select one or more configured sources, enter a UPC/EAN, view source-labelled cards, and export all returned rows to Excel.
- **Bulk Lookup**: upload Excel or CSV, choose the barcode column, select one or more sources, and export one row per source result while preserving all original input columns.

## Development

```bash
python -m pytest -q
streamlit run app.py --server.headless true
```
