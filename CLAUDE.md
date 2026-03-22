# CLAUDE.md — WatchLog / Dufner Personal Site

---

## Owner
**Eric Johnson** aka Duf / Dufner
- Email: dufner6161@gmail.com
- GitHub: github.com/ohthedufner
- License: MIT open source (intended)
- Data note: This software operates on data files supplied by the user. That data belongs to its respective owners.

WatchLog is a personal music and video history viewer built from Google Takeout exports.
It will be distributed as a standalone tool for others to use with their own data.

---

## Core Design Philosophy

1. **Open source, open formats, no lock-in.**
   All data must live in formats that can be migrated without loss. Pipe-delimited text, JSON, Markdown, and SQLite are acceptable. A hosted SaaS database is not.

2. **Data portability is sacred.**
   If a tool becomes unavailable tomorrow, nothing is lost. Every piece of data and metadata must be exportable and re-importable.

3. **Modular and separable.**
   WatchLog can run standalone OR as part of the larger personal site. Shared navigation and theme are layered on top — not baked in.

4. **Content-first, tools-second.**
   Evaluate existing open source tools before building custom ones.

5. **Storage and API use must be practical.**
   External data (MusicBrainz, etc.) must be cached locally on first fetch. Guardrails on storage size and re-fetch frequency must be built in from the start.

---

## Current Status (as of 2026-03-19)

**What exists and works:**
- `index.html` — Full working SPA: home, artists, songs, channels, search, artist/song/channel detail pages. Player mode toggle (Embed vs YouTube). MusicBrainz data displayed throughout. ~950 lines (all CSS + JS inline).
- `player.html` — YouTube IFrame player with queue and autoplay.
- `preprocess.py` — Processes Google Takeout JSON → 4 pipe-delimited output files. Includes append/merge and overlap detection.
- `build_watchlog_db.py` — Builds `watchlog.db` (SQLite) from preprocess.py output. Runs title cleaning, MusicBrainz artist + recording enrichment, builds songs table. All results cached in DB.
- `build_data_json.py` — Converts preprocess.py output (+ optional watchlog.db) → `data.json` for the site. Includes songs array and MusicBrainz fields.
- `data.json` — Pre-built data payload (old schema, ~465K tokens). **Needs to be regenerated** after running the pipeline on current data.
- `Gopogle_Takeout/data_structure.txt` — Well-documented analysis of the full takeout schema.
- One new takeout zip is present and ready to process: `takeout-20260316T021540Z-3-001.zip`

**Remaining critical gaps:**
- `preprocess.py` has not been run on the new takeout zip — `name_file.txt`, `name_title_file.txt` do not yet exist
- Without those files, `build_watchlog_db.py` and `build_data_json.py` cannot run
- `data.json` is still the old hand-built version with old schema (no songs, no MB fields)
- No `validate_input_files.py`
- No commit/rollback workflow or run log for `data.json`
- No rules template file — title cleaning rules are still hardcoded in `build_watchlog_db.py`
- No admin or settings pages
- No Docker setup
- All CSS and JS are still inline in `index.html` (not yet split to separate files)

---

## Environment

- **Dev OS**: Windows 11 (with WSL installed)
- **Python**: 3.14.3 — only stdlib available (`sqlite3`, `urllib`, `json`, `re`). No `requests` or `musicbrainzngs`.
- **Serving (current)**: RebexTinyWebServer (Windows-only — not Docker-compatible)
- **Serving (Docker target)**: Python `http.server` or similar lightweight static server
- **Runtime dependencies**: Python 3 (scripts), internet access (Google Fonts CDN, YouTube IFrame API, YouTube thumbnails)
- **No JS frameworks** — pure HTML/CSS/JS, static files only
- **Docker migration**: Planned. All code is Docker-compatible except TinyWebServer.
- **Claude Code** for all development

### External CDN Dependencies (require internet in Docker container)
- `fonts.googleapis.com` — Orbitron, Space Mono, DM Sans
- `www.youtube.com/iframe_api` — player.html
- `img.youtube.com/vi/{id}/mqdefault.jpg` — thumbnails (fetched dynamically)
- `musicbrainz.org/ws/2` — MusicBrainz API (Python scripts only, cached after first fetch)

---

## Actual File Structure (as of 2026-03-19)

```
WatchLog/
├── index.html                  ← Main SPA viewer (all CSS + JS inline, ~950 lines)
├── player.html                 ← YouTube IFrame player with queue
├── preprocess.py               ← Takeout JSON → flat text files
├── build_watchlog_db.py        ← Flat text + MB lookup → watchlog.db (SQLite)
├── build_data_json.py          ← Flat text + watchlog.db → data.json (bridge script)
├── data.json                   ← Runtime data payload — OLD SCHEMA, needs regeneration
├── WatchLog.bat                ← Launches TinyWebServer
├── CLAUDE.md                   ← This file
├── PLAN.md                     ← Prioritized development plan
├── Gopogle_Takeout/
│   ├── takeout-20260316T021540Z-3-001.zip   ← New data, ready to process
│   └── data_structure.txt      ← Takeout schema reference
├── TinyWebServer/              ← Windows-only static file server (to be replaced)
└── memory/                     ← Claude session memory files
```

**Output files produced by preprocess.py (not yet present — pipeline not yet run):**
- `name_file.txt` — channel/artist index (pipe-delimited)
- `name_title_file.txt` — video catalog (pipe-delimited)
- `dataset_info.txt` — run manifest / statistics
- `category_review.txt` — unsure channels for manual review

**Output files produced by build_watchlog_db.py:**
- `watchlog.db` — SQLite database (not yet present — pipeline not yet run)

---

## Data Pipeline (current state — all scripts built, not yet run on new data)

```
Google Takeout ZIP
    ↓
[unzip to working folder]
    ↓
validate_input_files.py     ← NOT YET BUILT — verify format, date ranges, user identity
    ↓
preprocess.py               ← parse + clean + categorize → flat text files
    ↓ (produces name_file.txt, name_title_file.txt, category_review.txt, dataset_info.txt)
[curator reviews category_review.txt, edits if needed]
    ↓
build_watchlog_db.py        ← BUILT — flat files + MusicBrainz → watchlog.db
    ↓ (title cleaning, MB artist + recording enrichment, songs table — all cached in DB)
build_data_json.py          ← BUILT — watchlog.db + flat files → data.json
    ↓
commit step                 ← NOT YET BUILT — timestamp-stamped, logged, rollback-safe
    ↓
data.json                   ← served by static site
```

---

## Data Structure Rules

### Raw Data is Sacred
The takeout files are backup archives — never modified. All processing produces new files in parallel.

### All Removed Text Must Be Preserved
Title cleaning in `build_watchlog_db.py` stores every piece of text removed from a video title in a `stripped_text` JSON array column. Each entry has a `type` label (`artist_prefix`, `feat_artist`, `noise_suffix`, `noise_suffix_re`). Nothing is discarded.

### Channel Normalization
- `channel_url` is the **stable key** — channel names can change, URLs do not
- `" - Topic"` and `"VEVO"` suffixes stripped for display (kept in raw_name)
- Ren's channels kept separate: `Ren`, `Ren - Topic`, `RenMakesStuff` (different content)

> ⚠️ **[SPECIAL ATTENTION]** `build_data_json.py` currently sets `channel_count: 1` for all artists. The original `data.json` had `channel_count: 4` for Ren (multiple channels aggregated under one artist). Multi-channel artist grouping logic is not yet implemented in the new pipeline.

### Title Cleaning (implemented in build_watchlog_db.py)
- `"Watched "`, `"Watched this "` prefixes stripped by `preprocess.py` (Google-added prefix)
- In `build_watchlog_db.py`, further cleaning produces:
  - `cleaned_title` — canonical song name (artist prefix, feat., noise suffixes removed)
  - `feat_artist` — extracted featured artists
  - `stripped_text` — JSON array of everything removed with type labels
  - `media_type` — canonical content format (Official Music Video, Official Audio, Official Lyric Video, Live, Acoustic, Visualizer, Music Video)
- Rules are **still hardcoded** in `build_watchlog_db.py` — rules template file not yet built

> ⚠️ **[SPECIAL ATTENTION]** Title cleaning rules should be moved to an external template file (see PLAN.md 2.2). Currently they are in Python source, making them non-curator-editable.

### Data Handling for Edge Cases
When anomalies are found in real data:
1. Separate problem data from clean data
2. Document: what was found, nature of problem, possible fixes
3. Do NOT act on fixes — present for analysis only
4. Continue processing clean portion

### Sandboxing Rule
Preprocessing and comparison to raw data all takes place in sandboxed files.
Committing to the live `data.json` is a separate, explicit step with a timestamp marker.

---

## Database Strategy

**Current:** Two-layer storage:
1. Flat pipe-delimited text (`name_file.txt`, `name_title_file.txt`) — primary pipeline output, human-readable, portable
2. SQLite (`watchlog.db`) — enrichment layer with MusicBrainz data and derived fields. Not required to run the site; used to enrich `data.json`.

**watchlog.db tables:**
| Table | Purpose |
|---|---|
| `channels` | One row per channel. All takeout fields + MB artist fields. |
| `videos` | One row per unique video. All takeout fields + cleaning fields (cleaned_title, feat_artist, stripped_text, media_type) + MB recording fields (mb_song_name, mb_isrc, mb_release_date, mb_release_type, mb_duration_ms, etc.). |
| `songs` | Deduplicated canonical songs. Keyed by mb_recording_id if matched, else by artist+cleaned_title. |
| `run_log` | Audit trail of pipeline runs. |

**MusicBrainz caching:** All MB results stored in `watchlog.db` with `mb_cached_at` timestamp and `mb_status` (`accepted` / `review` / `no_match` / `pending`). Re-runs skip already-cached records.

**Upgrade path:** Remaining tables (playlists, user notes, admin overrides) go in SQLite when needed.

---

## Song Table (built in watchlog.db — basic version)

The `songs` table in `watchlog.db` and the `songs` array in `data.json` now exist.

| Field | Source | Notes |
|---|---|---|
| `song_id` | System-generated | hex timestamp + counter |
| `mb_recording_id` | MusicBrainz | null if unmatched |
| `mb_song_name` | MusicBrainz | canonical title |
| `cleaned_title` | Derived | always present; pre-MB best-effort |
| `channel_url` | Takeout | primary artist channel |
| `artist_name` | Takeout | norm_name |
| `mb_artist_id` | MusicBrainz | from channel enrichment |
| `feat_artist` | Derived | extracted from title |
| `mb_release_date` | MusicBrainz | |
| `isrc` | MusicBrainz | comma-separated if multiple |
| `mb_confidence` | MusicBrainz | 0–100 score |
| `notes` | Manual | freeform, curator-added |
| `video_count` | Aggregated | source video count |

> ⚠️ **[SPECIAL ATTENTION]** The songs table is built from `watchlog.db` output. It has not yet been populated with real data (pipeline not yet run). The planned `notes` field from CLAUDE.md's original song table design is present as a column but no mechanism exists yet to populate it from the curator review flow.

---

## MusicBrainz Integration (built — not yet run on real data)

**Evaluation summary (2026-03-19):**
- Artist-level matching: high confidence (~80–90% for artists with >10 plays)
- Recording-level matching: medium confidence (~50–65%) due to title noise in YouTube titles
- Best match candidates: `YouTube Music` header rows first, then `" - Topic"` channels, then `VEVO`
- The `channel_url` field is the tiebreaker for artist disambiguation (e.g., multiple artists named "Ren")

**Implementation:** `build_watchlog_db.py`
- Uses `urllib` only (no external packages required)
- Rate-limited to 1 req/sec via `time.sleep()`
- User-Agent: `WatchLog/1.0 (dufner6161@gmail.com)` (required by MB policy)
- Accept threshold: score ≥ 85 → `accepted`; score 60–84 → `review`; below → `no_match`
- Flags: `--skip-mb` (offline), `--mb-artists-only`, `--mb-limit N` (for testing)

---

## Pages — Current Layout (index.html as of 2026-03-19)

**Nav:** `Home | Artists | Songs | Channels | Search` + player mode toggle (top right)

### Home Page
- 5 stat cards: Total Watches, Music Plays, Artists, Songs, Other (all clickable nav)
- Two columns: Recently Watched (left) | Top Artists + Top Songs stacked (right)

### Artists Page (`#artists`)
- Featured artist cards (Ren, Gorillaz) hardcoded at top
- Filterable/sortable artist grid (48/page): plays, A–Z, recently watched
- Artist cards show MB country + type if matched
- *Planned: A–Z sidebar filter, larger search*

### Artist Detail Page (`#artist/slug`)
- Hero: initials avatar, play count, last watched, video count
- MB chips row: country, type, active years, top 5 genre tags, confidence score
- Featured artists: biography (from ARTIST_META in JS), narrative arcs, affiliate chips
- Paginated video list with "Play Page" queue button
- Media type badge on each video

### Songs Page (`#songs`)
- Filter by title + separate filter by artist name
- Sort: most played, A–Z, recently watched, release year
- Song cards: title, artist, feat., plays, year, release type, media type badge, ISRC

### Song Detail Page (`#song/artist-slug/title-slug`)
- Full MB data: recording ID, ISRC, release title/date/type, duration, confidence
- Original raw YouTube title shown if different from cleaned title
- Source videos panel with thumbnails

### Channels Page (`#channels`)
- Category tabs (TV, Tech, Food, Comedy, News, Gaming, Mystery/Unsure)
- Text filter, paginated channel grid
- Channel cards show MB country/type if matched

### Channel Detail Page (`#channel/slug`)
- Hero with MB chips if available
- Paginated video list

### Search (`#search`)
- Searches: artists, songs, channels, recent videos — shown in four labeled sections

### Player Mode Toggle
- **Embed mode** (default): opens `player.html` with YouTube IFrame API. YouTube may reject on some networks.
- **YouTube mode**: opens `youtube.com/watch?v=...` directly in a new browser tab.

---

## Pages — Still Planned (not yet built)

- **Settings page** — theme switcher, home page display options
- **Admin page** — import tool links, dataset stats, category management, featured artist management
- **About page** — dataset stats (currently on home page)

---

## Featured Artists — FUTURE (not on main site yet)

Featured artist pages combine:
1. Auto-pulled video history from the pipeline
2. Hand-authored narrative (biography, story, context)
3. Structured metadata (arcs, affiliations) in JSON files

**Rule: Claude must NEVER invent biographical details.** Use only what is documented here or in `profile.md` files. Mark gaps as `[TO BE WRITTEN]`.

Planned file structure:
```
featured_artists/
└── {slug}/
    ├── profile.md         ← Biography, hand-authored
    ├── arcs.json          ← Named song groupings / narrative arcs
    └── affiliations.json  ← Related artists (channel_url as key)
```

### Ren Gill
- Full name: Ren Gill. From Wales, based in Brighton.
- Channels: `Ren`, `Ren - Topic` (auto), `RenMakesStuff`
- Genre: Rap, folk, spoken word, theatrical.
- ~10 years undiagnosed Lyme Disease. Story of perseverance.
- Key work: *Hi Ren* — theatrical self-dialogue.
- Narrative arcs: Jenny Arc, Vincent's Tale, Seven-Part Series
- Circle: The Big Push, The Skinner Brothers, Sam Tompkins, PROF

### Gorillaz
- Created by Damon Albarn (Blur) + Jamie Hewlett
- Fictional band: 2-D, Murdoc Niccals, Noodle, Russel Hobbs
- 50+ collaborators. Ongoing fictional world/narrative.
- Notable eras: Plastic Beach (2010), Song Machine (2020+)
- Related channels: `Gorillaz`, `Gorillaz - Topic`, `GZ 23`, `whatsnextgorillaz`
- Blur connection: Damon Albarn frontman. `Blur - Topic` in the data.

---

## Notes Field

The `notes` column in `name_file.txt` contains free-text metadata added manually during category review. Unstructured. Preserved verbatim.

> ⚠️ **[SPECIAL ATTENTION]** The `notes` field is referenced in design but does not yet flow through the pipeline. `preprocess.py` does not output a notes column, and `build_watchlog_db.py` does not read one. This needs to be reconciled when the admin/curator workflow is built.

---

## Roadmap Summary

| Horizon | Focus |
|---|---|
| **NOW** | Run pipeline on new takeout data (blocked on preprocess.py run), Docker setup, code split (HTML→CSS+JS) |
| **NEAR** | validate_input_files.py, rules template file, settings/themes, admin page skeleton, commit/rollback step |
| **FUTURE** | Deep search, playlist builder, featured artist pages, multi-channel artist grouping |

See `PLAN.md` for detailed task breakdown.

---

## Workflow Notes

- Owner types fast, captures ideas quickly — notes may be rough. Make reasonable interpretations and confirm.
- FoxPro/ColdFusion database background — thinks in normalized tables naturally.
- Cordon Bleu + civil engineering + ESPHome/WLED/Home Assistant background.
- Interests: golden ratio, non-Western math, Alan Watts / philosophy.
- Playlists are future — hold off on UI. Interim plain-text format:
  ```
  # playlist_name: Late Night Chill
  # created: 2026-03-10
  video_id, artist, title
  ```

---

*Last updated: 2026-03-19*
