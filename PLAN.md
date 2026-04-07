# PLAN.md — WatchLog Development Plan
*Created: 2026-03-19 | Last updated: 2026-04-07*

## Priority Legend
- ✅ Done
- 🔴 Blocking — nothing downstream works without this
- 🟡 High — needed soon, unblocks other work
- 🟢 Normal — important but not blocking
- ⚪ Future — design awareness only
- ⚠️ Needs review — completed but requires verification or has known gaps

---

## Phase 1 — Foundation

### 1.1 ✅ Data Pipeline: `build_wl_db.py`
**Status:** Complete. Builds `wl.db` from Google Takeout JSON + `watchlog.db`.
**What was built:**
- `wh_events` — raw watch events from Takeout (with YouTube TV events excluded)
- `dj_*` tables — artist/channel/video/recent derived views
- `ad_*` tables — admin stats and channel list with MB enrichment status
- `wl_songs` / `wl_videos` / `wl_song_video` — deduplicated song model loaded from `watchlog.db`
- `wl_artist_links` — curator-managed "See Also" links (user table, never dropped on rebuild)
- Pipeline tables dropped and recreated each run; user tables use `CREATE TABLE IF NOT EXISTS`

---

### 1.2 ✅ Bridge Script: `build_data_json.py`
**Status:** Complete. Rewrote 2026-04-07 to source entirely from `wl.db`.
**What was built:**
- Reads only `wl.db` — no pipe files, no `watchlog.db`
- Generates `data.json` (artists, songs, other_channels, recent, cat_counts)
- Generates `admin_data.json` (stats, channels list)
- Songs section aggregated from `wl_songs + wl_videos + wl_song_video` via SQL
- Admin stats computed from live row counts (no circular `ad_stats` dependency)
- See Also links embedded in artist objects from `wl_artist_links`

> ⚠️ Only 891/5,540 music videos have `wl_date_last` — "Recently Watched" sort on songs is sparse. Upstream data quality issue in `watchlog.db`.

---

### 1.3 🟡 Docker Setup
**Status:** Not started.
**What:** Replace TinyWebServer with a portable dev environment.
**Deliverables:**
- `Dockerfile` — Python 3, installs Flask, runs `server.py`
- `docker-compose.yml` — mounts project folder as volume (live edits)
- `README-docker.md` — one-page quick start
**Dependencies:** None — can be done in parallel with any other task.

---

### 1.4 🟢 Code Split: Extract CSS and JS from `index.html`
**Status:** Not started. `index.html` is now ~1,100+ lines.
**What:** Break the monolith into maintainable pieces.
**Deliverables:**
- `watchlog.css` — all styles
- `watchlog.js` — all JavaScript
- `index.html` — links only, much shorter
**Why needed:** Theme switching requires CSS variables in a standalone file. Debugging JS is increasingly difficult inline. Required before Settings page (3.6).

---

## Phase 2 — MusicBrainz & Enrichment Pipeline

### 2.1 ✅ MusicBrainz Evaluation
**Status:** Complete (2026-03-19).
**Findings:**
- Artist-level matching: high confidence (~80-90% for artists with >10 plays)
- Recording-level: medium (~50-65%) due to YouTube title noise
- `channel_url` is the disambiguation key
- Best match order: YouTube Music header / Topic channels / VEVO / general music

---

### 2.2 ✅ MusicBrainz Integration: `build_watchlog_db.py`
**Status:** Complete (2026-03-19). Builds `watchlog.db` with MB enrichment.
**What was built:**
- Title cleaning pipeline: `cleaned_title`, `feat_artist`, `stripped_text`, `media_type`
- MB artist enrichment: country, type, begin/end dates, genre tags, disambiguation, confidence
- MB recording enrichment: canonical song name, ISRC, release title/date/type, duration
- Results cached — re-runs skip already-matched records
- Rate-limited to 1 req/sec, stdlib only

> ⚠️ MB enrichment run via `admin.html` per channel. Run on more channels as time allows.

---

### 2.3 🟢 Rules Template File
**Status:** Not started.
**What:** Move hardcoded title/name cleaning rules in `build_watchlog_db.py` to a curator-editable text file.
**Why needed:** `NOISE_SUFFIX_LITERALS`, `NOISE_REGEX_PATTERNS`, `FEAT_PATTERNS`, `MEDIA_TYPE_MAP` are Python lists — not editable without touching code.

---

## Phase 3 — Core Site Features

### 3.1 ✅ Songs Page
**Status:** Complete. Now populated with 4,989 real songs from `wl_songs`.
- Filter by title and artist
- Sort: most played, A-Z, recently watched
- Song cards: title, artist, feat., plays, latest
- Song detail: source videos lookup by video ID in artists[]

---

### 3.2 ✅ Song Detail Page
**Status:** Complete. Shows MB data when available; source video panel with thumbnails.

---

### 3.3 ✅ Channels Page
**Status:** Complete (2026-03-19). Renamed from "Videos". Shows MB country/type chips.

---

### 3.4 ✅ Player Mode Toggle
**Status:** Complete (2026-03-19). Embed / YouTube direct toggle in nav.

---

### 3.5 ✅ Admin Page (`admin.html`)
**Status:** Complete. Shows dataset stats, channel list with MB enrichment status and confidence, per-channel MB run controls.

---

### 3.6 ✅ Artist "See Also" Editing Interface
**Status:** Complete (2026-04-07).
**What was built:**
- `wl_artist_links` table in `wl.db` (user table — survives rebuilds)
- `server.py` — Flask local server with static file serving + REST API
- API: `GET /api/health`, `GET /api/artists?q=`, `GET /api/artist-links/<slug>`, `POST /api/artist-links`, `DELETE /api/artist-links/<id>`
- Artist detail page: See Also chips with remove button (server mode only)
- Search dropdown: type-to-search artists by name, mutual link checkbox
- `serverMode` flag: detected at boot via `GET /api/health` with 600ms timeout

> ⚠️ WAL mode enabled per-connection in `server.py` via PRAGMA. Sufficient for single local user. Full WAL on DB open not yet set at DB creation time in `build_wl_db.py`.

---

### 3.7 🟡 `validate_input_files.py`
**Status:** Not started.
**What:** Pre-flight check before running `preprocess.py`.
**Checks:**
- Valid JSON in expected Takeout format
- `header` field values are expected (`YouTube`, `YouTube Music`, `YouTube TV`)
- Date ranges / overlap detection against existing data
- Enumerate invalid/missing records with reasons

---

### 3.8 🟡 Settings Page + Theme Switcher
**Status:** Not started. Requires 1.4 (code split) first.
**What:** New page within SPA with theme selection.
**Themes:**
- `theme-neon` — current dark neon (legacy)
- `theme-dark` — new readable dark theme (default)
- `theme-light` — new light theme
**Requirements:**
- All theme values via CSS variables
- Theme persisted in localStorage

---

### 3.9 🟢 Multi-Channel Artist Grouping
**Status:** Not started. Known gap.
**What:** Artists like Ren have multiple channels (`Ren`, `Ren - Topic`, `RenMakesStuff`) that should merge into one entry with accurate `channel_count`.
**Approach options:**
- A) Use `mb_artist_id` as grouping key (requires MB match)
- B) User-defined merge rules file (`channel_merges.txt`)
- C) Normalize `norm_name` after Topic/VEVO stripping (approximate, fast)

---

### 3.10 🟢 Commit Step + Run Log
**Status:** Not started.
**What:** Formalize the step that moves rebuilt data into live `data.json`.
**Requirements:**
- Timestamp marker on every build
- Log: date, source file, record counts, MB match rates
- Rollback: keep N previous `data.json` versions with timestamps

---

## Phase 4 — Backend API (Post-Docker)

### 4.1 🟡 Full Backend API: FastAPI or Flask
**Status:** `server.py` is the working prototype (artist links only). Full backend not yet built.
**What:** Replace all `fetch('data.json')` calls in JS with API endpoints.
**Endpoints needed (minimum):**
- `GET /api/artists` — paginated, with search
- `GET /api/artist/<slug>` — full artist detail
- `GET /api/songs` — paginated, with search
- `GET /api/recent`
- `GET /api/channels`
- Existing artist-links endpoints (already in server.py)
**Dependencies:** Docker (1.3) — backend should run in container.

---

### 4.2 🟡 WAL Mode at DB Creation
**Status:** Currently set via PRAGMA per-connection in `server.py`. Should be set at creation time in `build_wl_db.py`.
**What:** Add `PRAGMA journal_mode=WAL` to `build_wl_db.py` before any writes, so all connections inherit WAL automatically.

---

## Phase 5 — Future (Design Awareness Only)

### 5.1 ⚪ Featured Artist Pages
Full per-artist profiles: bio, affiliations, arcs, timeline.
Ren and Gorillaz are priority candidates. "See Also" links (3.6) are the first step toward this.
Prerequisite: Admin page complete, document management decision, move `ARTIST_META` out of index.html JS.

### 5.2 ⚪ wl_songs Editing
Curator-editable fields on song records: correct title, correct artist, manual MB ID override.
Will follow the same pattern as artist links: backend API + in-page editing UI.
Prerequisite: Full backend API (4.1).

### 5.3 ⚪ MusicBrainz Recording Matching
`wl_songs` has 0 MB matches currently — `mb_recording_id` all NULL.
Will require running MB recording lookup on `wl_songs` (similar to channel enrichment).

### 5.4 ⚪ Deep Search
Search across all metadata: notes, display text, tags, affiliations.
Prerequisite: Song table populated with MB data, notes field in pipeline.

### 5.5 ⚪ Playlist Builder
UI for building and saving playlists.
Prerequisite: Deep search, usage patterns from existing playlists.

### 5.6 ⚪ MusicBrainz Refresh / Re-enrichment
TTL-based re-fetch. `mb_cached_at` stored but no TTL logic enforced.
Suggested: 90 days for artists, 30 days for recordings.

### 5.7 ⚪ Document Management System
Decision needed before building any content sections:
- A) Folders + manifest JSON
- B) Obsidian/Joplin
- C) Git + Markdown

---

## Open Questions / Decisions Needed

1. **Multi-channel artist grouping** — How to merge Ren's channels? MB ID, rules file, or normalized name? See 3.9. Required before `channel_count` is accurate.

2. **Rules template format** — INI-style, YAML, or custom DSL? See 2.3. Curator-friendliness is priority.

3. **Theme naming** — Suggestions: `Neon` (current), `Midnight`, `Daylight`?

4. **Document management** — Which option (A/B/C) before content sections are built? See 5.7.

5. **Notes field** — `notes` column referenced in design but not in pipeline or DB. Where/how does the curator add notes? Admin page? Direct edit in `wl.db`?

---

## Items Flagged for Special Attention

| Item | Issue |
|------|-------|
| `channel_count` in artists | Always 1; multi-channel grouping not implemented (3.9) |
| Title cleaning rules | Hardcoded Python lists in `build_watchlog_db.py` — not curator-editable (2.3) |
| `wl_date_last` coverage | Only 891/5,540 music videos have a date — "recently watched" sort is unreliable |
| `wl_songs` MB matches | 0 recordings matched to MB — MB recording pipeline not yet run |
| `ARTIST_META` in `index.html` | Ren + Gorillaz bios hardcoded in JS — third featured artist requires externalizing first |
| WAL mode | Set per-connection via PRAGMA in `server.py`; not set at DB creation in `build_wl_db.py` (4.2) |
| `notes` field | In design; not in pipeline, DB, or site yet |

---

*See CLAUDE.md for architecture decisions, field naming convention, table groups, and design philosophy.*
