# WatchLog

A personal music and video history viewer built from Google Takeout exports.

Browse your YouTube watch history by artist, song, and channel. See play counts, recently watched, and curator-maintained "See Also" relationships and content type tags.

---

## What It Does

- Parses Google Takeout watch history (JSON or HTML format)
- Enriches data with [MusicBrainz](https://musicbrainz.org) artist and recording metadata
- Generates a local SQLite database (`wl.db`) as the source of truth
- Serves a single-page web app — no frameworks, no build step

**Pages:** Home · Artists · Songs · Channels · Search  
**Player modes:** Embedded YouTube IFrame or direct YouTube tab

---

## Quick Start

**Requirements:** Python 3.10+ with `flask` installed (`pip install flask`)

1. Export your YouTube history from [Google Takeout](https://takeout.google.com) — select only "YouTube and YouTube Music", history format JSON.

2. Place `watch-history.json` in `Google_Takeout/`.

3. Run the pipeline:
   ```bash
   python preprocess.py
   python build_watchlog_db.py
   python build_wl_db.py
   python build_data_json.py
   ```

4. Serve the site:
   ```bash
   # View-only (no editing):
   python -m http.server 8000

   # With editing support (curator features):
   python server.py
   ```

5. Open `http://localhost:8000` in your browser.

---

## Data Pipeline

```
Google Takeout export
    ↓  preprocess.py          parse raw JSON/HTML
    ↓  build_watchlog_db.py   clean titles, fetch MusicBrainz data
    ↓  build_wl_db.py         build presentation database (wl.db)
    ↓  build_data_json.py     export data.json + admin_data.json
    ↓  server.py / http.server
```

---

## Curator Features

Running `python server.py` instead of the plain HTTP server enables write-back features. All curator edits are stored in `wl.db` and survive pipeline rebuilds.

- **Artist See Also links** — on any artist page, search for related artists and add/remove "See Also" chips
- **Content type tagging** — on any artist or song page, assign a content type to each video (Music Video, Audio Only, Lyric Video, Visualizer, etc.) via a per-row dropdown. Auto-assigned on import; curator-correctable at any time.
- **Channel categorization** — via the admin panel, assign categories to uncategorized channels

### Content Types

| Value | Description |
|-------|-------------|
| `MUSIC_VIDEO` | Official or fan music video |
| `AUDIO_ONLY` | Audio with no video component |
| `LYRIC_VIDEO` | Lyrics displayed on screen |
| `VISUALIZER` | Abstract/animated visuals |
| `MEDLEY` | Multiple songs in one video |
| `MUSIC_SET` | Concert or multi-song performance |
| `BTS` | Behind the scenes |
| `SPOKEN` | Primarily spoken word |
| `REACTION` | Creator reacting to a song or video |
| `BIO` | Biographical or history content |
| `CLIPS` | Fan compilations or clip collections |
| `OTHER_XXXXXXXX` | Freeform tag (8 alphanumeric chars) |

---

## File Structure

| File | Purpose |
|------|---------|
| `index.html` | Single-page app (CSS + JS inline) |
| `player.html` | YouTube IFrame player with queue |
| `admin.html` | MusicBrainz channel enrichment tool |
| `preprocess.py` | Takeout → flat files |
| `build_watchlog_db.py` | Flat files + MB lookup → `watchlog.db` |
| `build_wl_db.py` | `watchlog.db` + sources → `wl.db` |
| `build_data_json.py` | `wl.db` → `data.json` + `admin_data.json` |
| `server.py` | Flask local server with editing REST API |

---

## License

MIT — see [LICENSE](LICENSE).  
Data files processed by this tool belong to their respective owners.
