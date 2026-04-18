# WatchLog — Usage Guide

Day-to-day operation: serving the site, adding new watch history data, and running the pipeline.

For first-time setup, see [SETUP.md](SETUP.md). For editing your data in the browser, see [CURATING.md](CURATING.md).

---

## Serving the site

**View-only** — read-only browsing, no editing controls:

```bash
python -m http.server 8000
```

**With Curator mode** — activates the Viewer / Curator toggle in the nav, enables all in-page editing:

```bash
python server.py
```

Open `http://localhost:8000`. The site detects which server is running automatically.

---

## Adding new watch history

When you export a new Takeout file, re-run the pipeline from the beginning. The pipeline is designed to be re-run safely:

- Raw source data is never modified
- Pipeline tables are dropped and rebuilt each run
- Your curator edits (See Also links, content types, channel categories, notes) are stored in permanent tables that survive every rebuild

```bash
# Replace the file in Google_Takeout/ with your new export, then:
python preprocess.py
python build_watchlog_db.py   # skips already-cached MusicBrainz lookups
python build_wl_db.py
python build_data_json.py
```

After the run, open the site — your history is updated and your curator work is intact.

---

## Pipeline reference

| Script | Input | Output | Notes |
|---|---|---|---|
| `preprocess.py` | `Google_Takeout/watch-history.json` | Flat pipe-delimited files | Accepts JSON or HTML Takeout format |
| `build_watchlog_db.py` | Flat files | `watchlog.db` | Title cleaning, MusicBrainz enrichment; caches results |
| `build_wl_db.py` | `watchlog.db` + sources | `wl.db` | Presentation DB; user tables never dropped |
| `build_data_json.py` | `wl.db` | `data.json`, `admin_data.json` | Site data payload |

---

## MusicBrainz enrichment

MusicBrainz data enriches artist records (country, genre tags, type) and eventually song records (canonical title, release date, ISRC). Lookups are rate-limited to 1 request/second and cached in `watchlog.db` after the first fetch — re-runs are fast.

Channel enrichment is managed from the admin page (`admin.html`): select channels, review confidence scores, accept or reject matches.

> Re-running enrichment on already-accepted channels requires a manual flag. Accepted results are not overwritten automatically.

---

## Player modes

The nav bar includes a player mode toggle:

- **Embed** — plays videos in an IFrame player (`player.html`) with queue and autoplay
- **YouTube** — opens each video directly in a new YouTube tab

Your choice persists across sessions in `localStorage`.

---

## File structure reference

| File | Purpose |
|---|---|
| `index.html` | Single-page app |
| `watchlog.css` | All styles and theme definitions |
| `watchlog.js` | App logic |
| `player.html` | YouTube IFrame player with queue |
| `admin.html` | Admin tools: MusicBrainz enrichment, channel management |
| `preprocess.py` | Takeout → flat files |
| `build_watchlog_db.py` | Flat files + MusicBrainz → `watchlog.db` |
| `build_wl_db.py` | `watchlog.db` → `wl.db` |
| `build_data_json.py` | `wl.db` → `data.json` + `admin_data.json` |
| `server.py` | Flask server — static files + curator REST API |
| `watchlog.db` | Pipeline database (MusicBrainz cache, title cleaning) |
| `wl.db` | Presentation database — source of truth for the site |
