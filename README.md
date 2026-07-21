# Catalogue Scraper

Catalogue Scraper is a Streamlit multi-source catalogue research platform for single barcode lookups and bulk metadata enrichment.

## Application sections

### Search

- **Single Lookup**: enter one UPC/EAN and view every returned release as cards with artwork, key metadata, source links, and direct image links.
- **Bulk Lookup**: upload Excel or CSV, select the barcode column, preserve the original columns, output one row per returned source release, and export Excel.

### Sources

The source registry is the central place for source metadata, status, credentials, and connector factories. Adding a production source should only require implementing a connector that follows the shared interface and registering it.

Current source status:

- Discogs: available
- Amazon: planned placeholder
- MusicBrainz: planned placeholder
- Spotify: planned placeholder
- Apple Music: planned placeholder
- AudioSalad: planned placeholder

### Settings

Catalogue Scraper reads credentials from Streamlit Secrets first, then environment variables. If a configured Discogs token is present, users do not need to paste a token into the UI.

```toml
DISCOGS_TOKEN = "your-token"

AMAZON_CLIENT_ID = "future-value"
AMAZON_CLIENT_SECRET = "future-value"
AMAZON_REFRESH_TOKEN = "future-value"
AMAZON_SELLER_ID = "future-value"
```

## Connector interface

Every connector implements `CatalogueSource`:

- `lookup(barcode)` returns every release/product matching a UPC/EAN.
- `search(text)` returns source results matching text.
- `get_release(id)` returns a fully hydrated source record.

The Streamlit UI uses this interface and does not call source-specific APIs directly.

## Discogs behavior

Discogs lookup searches by UPC/EAN and returns one row per Discogs release returned by the API. It does not perform confidence scoring, matching, image downloads, or result filtering. Optional output fields include track listing, release notes, companies, identifiers, and video URLs. Image fields contain the main image URL and additional image URLs.

## Develop and test

```bash
python -m pytest -q
streamlit run app.py
```
