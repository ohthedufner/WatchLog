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

## Database Field Naming Convention

**Every field name begins with a two-letter prefix that identifies its source database.**

| Prefix | Source |
|--------|--------|
| `wh_`  | Google Takeout `watch-history.json` |
| `dj_`  | Aggregated display data (`data.json`) |
| `ad_`  | Admin data (`admin_data.json`) |
| `mb_`  | MusicBrainz external API |
| `wl_`  | WatchLog system — derived or user-editable fields |

**User editing rule:** A user never edits source data directly. When a field from an outside source needs to be editable, a `wl_` field is created in our system, pre-populated with a copy of the original. The original appears read-only adjacent to the editable field for reference.

---

## Current Status (as of 2026-04-07)

### What exists and works

- `index.html` — Full working SPA: home, artists, songs, channels, search, artist/song/channel/song-detail pages. Player mode toggle. See Also section on artist detail. ~1,100 lines (all CSS + JS inline).
- `player.html` — YouTube IFrame player with queue and autoplay.
- `admin.html` — MusicBrainz channel selector: filterable/sortable table of 2,007 music channels, time estimator, command generator.
- `preprocess.py` — Processes Google Takeout (JSON or HTML format) → pipe-delimited flat files. Auto-detects format by extension.
- `build_watchlog_db.py` — Builds `watchlog.db` from preprocess output. Title cleaning, MB artist + recording enrichment, songs table. All results cached.
- `build_wl_db.py` — Builds `wl.db` (presentation database) from JSON sources + `watchlog.db`. Pipeline tables are dropped and recreated; user tables (`wl_artist_links`, future curator tables) are preserved with `CREATE TABLE IF NOT EXISTS`.
- `build_data_json.py` — Reads **only from `wl.db`** and writes `data.json` + `admin_data.json`. No pipe files or watchlog.db dependency.
- `server.py` — Flask server for editing sessions. Serves static files + REST API for writing to `wl.db`. Run this instead of a static server when editing data.

### Current data volumes

| | |
|---|---|
| Watch events (`wh_events`) | 7,300 |
| Music channels (`ad_channels`) | 2,007 |
| Music videos (`wl_videos`) | 5,540 |
| Songs (`wl_songs`) | 4,989 |
| MB matched channels | 2 (Gorillaz, accepted=100) |
| MB matched songs | 0 — recording enrichment not yet run |

---

## Environment

- **Dev OS**: Windows 11
- **Python**: 3.14 — stdlib + `flask` (installed). No `requests` or `musicbrainzngs`.
- **Serving (editing)**: `python server.py` — Flask on port 8000
- **Serving (view-only)**: `python -m http.server 8000` — static files only
- **Docker migration**: Planned. All code is Docker-compatible. `server.py` will be the Docker entry point.
- **No JS frameworks** — pure HTML/CSS/JS, static files only
- **Claude Code** for all development

### External CDN Dependencies (require internet)
- `fonts.googleapis.com` — Orbitron, Space Mono, DM Sans
- `www.youtube.com/iframe_api` — player.html
- `img.youtube.com/vi/{id}/mqdefault.jpg` — thumbnails (fetched dynamically)
- `musicbrainz.org/ws/2` — MusicBrainz API (Python scripts only, cached after first fetch)

---

## File Structure (as of 2026-04-07)

```
WatchLog/
├── index.html                  ← Main SPA viewer (CSS + JS inline)
├── player.html                 ← YouTube IFrame player with queue
├── admin.html                  ← MusicBrainz channel selector admin tool
│
├── preprocess.py               ← Takeout → flat pipe-delimited files
├── build_watchlog_db.py        ← Flat files + MB lookup → watchlog.db
├── build_wl_db.py              ← JSON sources + watchlog.db → wl.db
├── build_data_json.py          ← wl.db → data.json + admin_data.json
├── server.py                   ← Flask: static files + editing REST API
│
├── watchlog.db                 ← Pipeline/enrichment database (MB data, songs)
├── wl.db                       ← Presentation/application database (source of truth)
├── data.json                   ← Site data payload (~1,723 KB)
├── admin_data.json             ← Admin page data (~377 KB)
│
├── Google_Takeout/
│   ├── watch-history.json      ← Raw takeout data
│   └── watch-history.html      ← Older takeout (HTML format)
│
├── name_file.txt               ← Preprocess output: channel index
├── name_title_file.txt         ← Preprocess output: video catalog
├── dataset_info.txt            ← Preprocess run manifest
├── category_review.txt         ← Channels needing manual category review
│
├── manual_editing/
│   ├── to_categorize.csv
│   ├── apply_rules.py
│   └── category_rules.txt
│
├── CLAUDE.md                   ← This file
├── PLAN.md                     ← Prioritized development plan
└── table_structure.txt         ← wl.db table reference
```

---

## Data Pipeline

```
Google Takeout ZIP
    ↓
preprocess.py               → name_file.txt, name_title_file.txt, category_review.txt
    ↓
[curator reviews category_review.txt]
    ↓
build_watchlog_db.py        → watchlog.db  (MB enrichment, title cleaning, songs)
    ↓
build_wl_db.py              → wl.db        (presentation DB, wl_songs/videos/links)
    ↓
build_data_json.py          → data.json + admin_data.json
    ↓
python server.py            (editing) or python -m http.server (view-only)
```

**Key rule:** `build_wl_db.py` drops and recreates all pipeline tables on every run. User-edited tables (`wl_artist_links` and future curator tables) use `CREATE TABLE IF NOT EXISTS` and are **never dropped** — their data survives rebuilds.

---

## Database Architecture

### Two-database design

| Database | Role |
|---|---|
| `watchlog.db` | Pipeline and enrichment. Raw takeout fields, MB data, title cleaning. Rebuilt when new takeout data arrives or MB enrichment runs. |
| `wl.db` | Presentation and application. What the site and API read. Contains user-editable curator tables. Source of truth for `data.json`. |

### wl.db table groups

| Group | Tables | Source | Survives rebuild? |
|---|---|---|---|
| `wh_` | `wh_events` | `watch-history.json` | No — pipeline |
| `dj_` | `dj_artists`, `dj_artist_videos`, `dj_other_channels`, `dj_other_videos`, `dj_recent`, `dj_cat_counts`, `dj_meta` | `data.json` | No — pipeline |
| `ad_` | `ad_channels`, `ad_stats` | `admin_data.json` | No — pipeline |
| `wl_` pipeline | `wl_songs`, `wl_videos`, `wl_song_video` | `watchlog.db` | No — pipeline |
| `wl_` user | `wl_artist_links` (+ future) | User editing | **Yes — preserved** |

### wl_songs / wl_videos / wl_song_video

Music videos from `watchlog.db` are imported into `wl.db` with proper song deduplication:
- One `wl_songs` row per unique (normalized title, normalized artist)
- All videos linked to their song via `wl_song_video` junction (no UNIQUE constraint — allows future MB duplicate candidates)
- `wl_match_type`: `'exact'` or `'normalized'` (case difference)
- `wl_match_basis`: `'title+artist'` or `'title_only'`

### wl_artist_links (user-editable)

Artist "See Also" relationships. Uses `dj_slug` as the stable key (survives rebuilds; stable because it is computed deterministically from the artist name). Relationships are directional. The UI provides a "Mutual" option that adds both directions in one operation.

```sql
CREATE TABLE IF NOT EXISTS wl_artist_links (
    wl_al_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    wl_from_slug  TEXT NOT NULL,
    wl_to_slug    TEXT NOT NULL,
    wl_label      TEXT NOT NULL DEFAULT 'See also',
    UNIQUE(wl_from_slug, wl_to_slug)
);
```

---

## Backend / Editing Architecture

The site is not static. Data will be editable. Architecture:

**Current (interim):** `server.py` (Flask) serves static files + REST API for `wl_artist_links`. The JS detects the server via `GET /api/health` and enables edit controls automatically.

**Target (post-Docker):** FastAPI or Flask backend serves API endpoints (`/api/artists`, `/api/songs`, etc.). HTML pages `fetch('/api/...')` instead of `fetch('data.json')`. Enables server-side filtering, pagination, and full write-back.

**WAL mode:** Must be enabled on `wl.db` before any concurrent use (pipeline running while user edits):
```python
con.execute("PRAGMA journal_mode=WAL")
```
Already applied in `server.py`. Must be applied to any future backend entry point.

### Current API endpoints (server.py)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Server detection |
| GET | `/api/artists?q=` | Artist search for link targets |
| GET | `/api/artist-links/<slug>` | Get see-also links for an artist |
| POST | `/api/artist-links` | Add link (`from_slug`, `to_slug`, `label?`, `mutual?`) |
| DELETE | `/api/artist-links/<id>` | Remove one link |

---

## Site Pages (index.html)

**Nav:** `Home | Artists | Songs | Channels | Search` + player mode toggle

| Page | Status | Notes |
|---|---|---|
| Home | Working | 5 stat cards, recent + top artists + top songs |
| Artists | Working | Filterable/sortable grid, featured Ren + Gorillaz cards |
| Artist Detail | Working | Hero, MB chips, bio/arcs (featured), See Also section, paginated video list |
| Songs | Working | Filter by title + artist, sort by plays/A–Z/recent/year, 4,989 songs |
| Song Detail | Working | MB data, source videos |
| Channels | Working | Category tabs, filter, paginated grid |
| Channel Detail | Working | Hero, video list |
| Search | Working | Searches artists, songs, channels, recent videos |

**Player modes:** Embed (player.html via IFrame API) or YouTube (direct tab). Toggle in nav.

---

## MusicBrainz Integration

- Artist-level matching: ~80–90% confidence for artists with >10 plays
- Recording-level: ~50–65% due to YouTube title noise
- `channel_url` is the disambiguation key
- Rate-limited to 1 req/sec; results cached in `watchlog.db`
- Status values: `accepted` (≥85), `review` (60–84), `no_match` (<60), `pending`
- Re-runs skip already-cached records
- No MB enrichment run yet on songs — `mb_recording_id` is NULL for all `wl_songs`
- Run MB enrichment via `admin.html` channel selector → generates CLI command

---

## Content Scope

WatchLog has two sides: **Music** and **Other**.

- All active development and UI focus is on the **Music** side.
- Non-music channels and videos are accessible only through the **admin section** — they are not shown in the main viewer.
- This ensures edge cases (miscategorized content) can still be found and moved to music if needed.

---

## Artist, Video Creator, and Channel

Three distinct concepts — all curator-maintained:

| Concept | Field | Scope | Definition |
|---|---|---|---|
| **Video creator** | `norm_name` | Per channel | The person or entity that owns the channel. Every video on that channel shares the same creator. |
| **Artist** | `wl_artist` | Per video | The musical artist that is the *subject* of the video. Set by the curator. May differ from the creator. |
| **Channel** | `channel_url` | Per channel | The stable key for the channel. Creator is its associated person/entity. |

**Examples:**

| Channel | Video creator | Artist on video |
|---|---|---|
| Hexkind | Hexkind | Ren *(Hexkind covers multiple artists)* |
| RenMakesMusic | Ren | Ren |
| Trick the Fox | Trick the Fox | Trick the Fox |

**Channel grouping — two cases for multi-channel artists:**

1. **Intentional organization** (e.g. `RenMakesMusic`, `RenMakesStuff`) — channels are grouped under the artist page. Videos from each channel appear together on the artist page. Channels still listed separately on the Channels page.
2. **Accidental duplicate** (e.g. `Adian347`, `ADIAN347`) — no grouping on the artist page. Both channels remain fully separate on the Channels page.

**Artists without their own channel:** Valid case. An artist page can exist even if no channel maps to them directly (e.g. an artist whose content appears only on fan/cover channels).

---

## Content Types (`wl_content_type`)

All music-side videos have a `wl_content_type` field. Values are restricted to this list:

| Value | Description |
|---|---|
| `AUDIO_ONLY` | Audio with no video component |
| `MUSIC_VIDEO` | Official or fan music video |
| `LYRIC_VIDEO` | Lyrics displayed on screen |
| `VISUALIZER` | Abstract/animated visuals, not a narrative video |
| `MEDLEY` | One video containing all or parts of multiple songs |
| `MUSIC_SET` | Concert or multi-song performance in one video |
| `BTS` | Behind the scenes, associated with one video |
| `SPOKEN` | Primarily spoken (poem, monologue); may have some music |
| `REACTION` | Creator reacting to a song or video |
| `BIO` | Biographical, background, or history content |
| `CLIPS` | Fan compilations or clip collections |
| `OTHER_XXXXXXXX` | Freeform tag (8 alphanumeric chars, e.g. `OTHER_ACOUSTIC`) |

**Default assignment rules (applied at import, curator can override):**

| Condition | Default `wl_content_type` |
|---|---|
| Imported from YouTube Music Takeout | `AUDIO_ONLY` |
| Title contains "BTS" | `BTS` |
| Title contains "Visualizer" | `VISUALIZER` |
| Title contains "Lyric" | `LYRIC_VIDEO` |
| Title contains "Poem" | `SPOKEN` |
| Title contains "Reaction" | `REACTION` |
| Title contains "Fan Compilation" | `CLIPS` |
| All other music videos | `MUSIC_VIDEO` |

---

## Notes Fields

Three curator-editable notes fields exist — one per entity type:

| Table | Field | Purpose |
|---|---|---|
| `wl_artists` (future) | `wl_notes` | Freeform curator notes on an artist |
| `wl_songs` | `wl_notes` | Freeform curator notes on a song |
| `wl_videos` | `wl_notes` | Freeform curator notes on a video |

Notes are plain text. No markup required. Edited in-page when `server.py` is running.

---

## Title Cleaning Rules File

Hardcoded rules in `build_watchlog_db.py` (`NOISE_SUFFIX_LITERALS`, `NOISE_REGEX_PATTERNS`, `FEAT_PATTERNS`, `MEDIA_TYPE_MAP`) will be moved to a curator-editable **YAML file** (e.g. `cleaning_rules.yaml`).

- YAML format chosen for readability and native list/map support
- A minimal stdlib YAML parser will be written — no `PyYAML` dependency
- The Python scripts will load this file at runtime

**Example structure:**
```yaml
noise_suffix_literals:
  - Official Video
  - Official Audio
  - HD

feat_patterns:
  - "ft."
  - "feat."

media_type_map:
  "Official Music Video": music_video
  "Lyric Video": lyric_video
  "Live": live
```

---

## Content / Document Management

Artist bios, narrative arcs, and other long-form content are stored as **Git + Markdown files** (Option C).

- Each artist has one `.md` file with YAML frontmatter for structured fields (slug, tags, channels) and free prose in the body
- Files live in a `content/artists/` directory (and `content/songs/`, `content/channels/` as needed)
- Renders natively on GitHub; editable in any text editor
- A small stdlib parser extracts frontmatter at build time

**Example:**
```
content/
  artists/
    ren-gill.md
    gorillaz.md
  songs/
  channels/
```

```markdown
---
slug: ren-gill
channels: [ren, ren-topic, renmakesstuff]
tags: [rap, folk, spoken-word]
---

Ren Gill is a Wales-born artist based in Brighton...
```

---

## Themes

Three named themes (CSS variables, stored in `localStorage`):

| Name | Description |
|---|---|
| `Neon` | Current dark neon style (legacy default) |
| `Midnight` | New readable dark theme (future default) |
| `Daylight` | New light theme |

Theme switching requires extracting CSS to `watchlog.css` first (PLAN.md 1.4).

---

## Data Structure Rules

### Raw Data is Sacred
Takeout files are never modified. All processing writes new files in parallel.

### All Removed Text Must Be Preserved
Title cleaning in `build_watchlog_db.py` stores every piece of text removed from a video title in `stripped_text` (JSON array). Each entry has a `type` label (`artist_prefix`, `feat_artist`, `noise_suffix`, etc.). Nothing is discarded.

### Channel Normalization
- `channel_url` is the **stable key** — channel names change, URLs do not
- `" - Topic"` and `"VEVO"` suffixes stripped for display (kept in `raw_name`)

### Title Cleaning Fields (in watchlog.db.videos)
| Field | Purpose |
|---|---|
| `cleaned_title` | Canonical song name (artist prefix, feat., noise removed) |
| `feat_artist` | Extracted featured artists |
| `stripped_text` | JSON array of everything removed with type labels |
| `media_type` | Official Music Video, Official Audio, Lyric Video, Live, Acoustic, etc. |

### Sandboxing Rule
Pipeline output is validated before committing to live `data.json`. The commit step is explicit and logged.

---

## Featured Artists

Ren Gill and Gorillaz are hardcoded featured artists in `index.html` (biography, narrative arcs in `ARTIST_META` JS object). A third featured artist requires moving these to external files first.

**Rule: Claude must NEVER invent biographical details.** Use only what is documented here or in profile files. Mark gaps as `[TO BE WRITTEN]`.

### Ren Gill
- Full name: Ren Gill. Wales-born, based in Brighton.
- Channels: `Ren`, `Ren - Topic`, `RenMakesStuff`
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
- Related channels: `Gorillaz`, `Gorillaz - Topic`, `GZ 23`

---

## Workflow Notes

- Owner thinks in normalized tables naturally (FoxPro/ColdFusion background).
- Notes may be rough — make reasonable interpretations and confirm.
- Other active projects: LED matrix, ESP32, Home Assistant nav, smart switch, kinetic art.

---

*Last updated: 2026-04-13 (evening) CDT*
