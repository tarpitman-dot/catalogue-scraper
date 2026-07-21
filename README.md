# Catalogue Scraper v2

Standalone Streamlit catalogue research and bulk enrichment app.

## Modes

### Single Lookup

Paste one UPC/EAN and view all returned releases as image-and-metadata cards.

### Bulk Lookup

Upload Excel or CSV and export one row per returned release.

## Current source

- Discogs

## Planned sources

- Amazon
- MusicBrainz
- Spotify
- Apple Music
- AudioSalad

## Secrets

```toml
DISCOGS_TOKEN = "your-token"
```

## Deploy

Replace the existing project files, preserve `.git/` and your local `.streamlit/secrets.toml`, test locally, then commit and push.
