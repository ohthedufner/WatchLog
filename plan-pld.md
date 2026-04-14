# PLAN.md — WatchLog Development Plan
*Created: 2026-03-19 | Last updated: 2026-04-06

## Priority Legend
- ✅ Done
- 🔴 Blocking — nothing downstream works without this
- 🟡 High — needed soon, unblocks other work
- 🟢 Normal — important but not blocking
- ⚪ Future — design awareness only
- ⚠️ Needs review — completed but requires verification or has known gaps

---

## Phase 1 — Foundation

### 1.1 ✅ Bridge Script: `build_data_json.py`
**Status:** Complete.
**What was built:** Reads `name_file.txt` + `name_title_file.txt`, optionally joins MB enrichment from `watchlog.db`, and writes `data.json`. Schema expanded from original spec to include:
- `songs` array (deduplicated music recordings with MB data)
- MB fields on artists: `mb_id`, `mb_country`, `mb_type`, `mb_begin`, `mb_tags`, `mb_conf`
- MB fields on channels: same subset
- MB fields on videos within artists: `mt` (media type), `ms` (MB song name), `isrc`, `rd` (release date), `rt` (release type)

**Usage:**
```bash
python build_data_json.py --channels name_file.txt --videos name_title_file.txt
python build_data_json.py --channels name_file.txt --videos name_title_file.txt --db watchlog.db
```

> ⚠️ `channel_count` is set to `1` for all artists. Original data had `4` for Ren (multiple channels merged). Multi-channel grouping not yet implemented — this is a known gap.

---

### 1.2 🔴 Run the New Takeout Data End-to-End
**Status:** Blocked — `preprocess.py` not yet run on new zip.
**What's needed:**
1. Unzip `Gopogle_Takeout/takeout-20260316T021540Z-3-001.zip` to a working folder
2. Run `preprocess.py` with `--append` if prior flat files exist; fresh run otherwise
3. Review `category_review.txt`
4. Run `build_watchlog_db.py` (with `--mb-limit` for first test pass)
5. Run `build_data_json.py --db watchlog.db`
6. Verify site loads and songs/MB data is populated

**Note:** `data.json` is currently the old hand-built file. The site will not show songs or MB data until this step is complete.

---

### 1.3 🟡 Docker Setup
**Status:** Not started.
**What:** Replace TinyWebServer with a portable dev environment.
**Deliverables:**
- `Dockerfile` — Python 3 base image, copies project files, runs `python -m http.server 8080`
- `docker-compose.yml` — mounts project folder as volume so edits are live
- `README-docker.md` — one-page quick start
**Dependencies:** None (can be done in parallel with any other task)

---

### 1.4 🟡 Code Split: Extract CSS and JS from `index.html`
**Status:** Not started. `index.html` has grown from 730 to ~950 lines.
**What:** Break the monolith into maintainable pieces.
**Deliverables:**
- `watchlog.css` — all styles
- `watchlog.js` — all JavaScript
- `index.html` — links only, much shorter
**Why needed:** Theme switching requires CSS variables in a standalone file. Debugging JS is increasingly difficult inline.

---

## Phase 2 — MusicBrainz & Enrichment Pipeline

### 2.1 ✅ MusicBrainz Evaluation
**Status:** Complete (2026-03-19).
**Findings:**
- Artist-level matching: high confidence (~80–90% for artists with >10 plays)
- Recording-level: medium (~50–65%) due to YouTube title noise
- `channel_url` is the disambiguation key (e.g., two artists named "Ren")
- Best match order: YouTube Music header → Topic channels → VEVO → general music category

---

### 2.2 ✅ MusicBrainz Integration: `build_watchlog_db.py`
**Status:** Complete (2026-03-19).
**What was built:**
- SQLite database (`watchlog.db`) with tables: `channels`, `videos`, `songs`, `run_log`
- Title cleaning pipeline: `cleaned_title`, `feat_artist`, `stripped_text` (JSON array, preserves all removed text with type labels), `media_type`
- MB artist enrichment: country, type, begin/end dates, genre tags, disambiguation, confidence score
- MB recording enrichment: canonical song name, ISRC, release title/date/type, duration, confidence
- Results cached in DB — re-runs skip already-matched records
- Rate-limited to 1 req/sec, stdlib only (no external packages)
- Flags: `--skip-mb`, `--mb-artists-only`, `--mb-limit N`

**Usage:**
```bash
python build_watchlog_db.py --channels name_file.txt --videos name_title_file.txt
python build_watchlog_db.py --db watchlog.db --stats
python build_watchlog_db.py --channels name_file.txt --videos name_title_file.txt --skip-mb
```

> ⚠️ Has not been run on real data yet (blocked on 1.2). Tested with small fixture files only.

---

### 2.3 🟢 Rules Template File
**Status:** Not started.
**What:** Move hardcoded title/name cleaning rules out of `build_watchlog_db.py` into a curator-editable text file.

> ⚠️ **[SPECIAL ATTENTION]** Currently, the noise suffix lists (`NOISE_SUFFIX_LITERALS`, `NOISE_REGEX_PATTERNS`, `FEAT_PATTERNS`, `MEDIA_TYPE_MAP`) are Python lists in `build_watchlog_db.py`. This violates the intent of keeping rules curator-editable. This is the highest-friction gap in the cleaning pipeline for a non-developer user.

**Proposed format:**
```
# Prefix removal
strip_artist_prefix           # "ArtistName - " at start

# Featured artist extraction
extract_feat  \(feat\. ([^)]+)\)
extract_feat  \(ft\. ([^)]+)\)

# Noise suffixes (literal)
strip_suffix  (Official Music Video)
strip_suffix  (Official Audio)
...

# Media type classification
media_type Official Music Video = official music video
media_type Official Audio       = official audio
```

---

## Phase 3 — Core Site Features

### 3.1 ✅ Songs Page
**Status:** Complete (2026-03-19).
**What was built:** New `#songs` page in `index.html`:
- Filter by title, separate filter by artist
- Sort: most played, A–Z, recently watched, release year
- Song cards: title, artist, feat., plays, year, release type, media type badge, ISRC

---

### 3.2 ✅ Song Detail Page
**Status:** Complete (2026-03-19).
**What was built:** New `#song/artist-slug/title-slug` page:
- Full MB data display: recording ID, ISRC, release title/date/type, duration, confidence
- Original raw YouTube title shown if different from cleaned title
- Source videos panel with thumbnails and play buttons

---

### 3.3 ✅ Channels Page
**Status:** Complete (2026-03-19). Previously called "Videos" page in nav.
**What changed:**
- Renamed from "Videos" to "Channels" in nav (`#channels`)
- Channel cards now show MB country/type if matched
- Channel detail now shows MB chips
- Channel detail video list is now paginated (was flat)
- Backward compat: `#videos` hash still works (redirects to `#channels`)

---

### 3.4 ✅ Player Mode Toggle
**Status:** Complete (2026-03-19). Not in original plan — added in response to YouTube IFrame restrictions.
**What was built:** Two-button toggle in top-right nav:
- **Embed** (default): opens `player.html` with YouTube IFrame API
- **YouTube**: opens `youtube.com/watch?v=...` directly in a new tab
- All video links and "Play Page" queue button respect the selected mode

---

### 3.5 🟡 `validate_input_files.py`
**Status:** Not started.
**What:** Pre-flight check before running `preprocess.py`.
**Checks:**
- File is valid JSON in expected format
- `header` field values are expected (`YouTube`, `YouTube Music`, `YouTube TV`)
- Date ranges relative to existing data (overlap detection)
- Data format unchanged by Google (structural validation)
- Enumerate invalid/missing records with reasons

---

### 3.6 🟡 Settings Page + Theme Switcher
**Status:** Not started.
**What:** New page within SPA with theme selection.
**Themes:**
- `theme-neon` — current dark neon (legacy, kept for nostalgia)
- `theme-dark` — new readable dark theme (default)
- `theme-light` — new light theme
**Requirements:**
- All theme values via CSS variables (requires 1.4 code split first)
- Theme choice persisted in localStorage
- Fonts slightly larger than current
- Text/background contrast must be readable
- Home page display options (placeholders only initially)

---

### 3.7 🟢 Admin Page (skeleton)
**Status:** Not started.
**What:** `admin.html` — links to tools, no functionality yet.
**Sections:**
- Import (link to pipeline tools)
- Dataset stats (read from `dataset_info.txt`)
- Category management (placeholder)
- Artist management (placeholder)
- Song list management (link to songs page for now)
- Featured Artists management (placeholder)

---

### 3.8 🟢 Commit Step + Run Log
**Status:** Not started.
**What:** Formalize the step that moves sandboxed data into live `data.json`.
**Requirements:**
- Timestamp marker on every commit
- Log file: date, source file, record count, categories, MB match rates
- Rollback capability (keep N previous `data.json` versions with timestamps)
**Note:** `run_log` table exists in `watchlog.db` but the data.json commit step is separate and not yet formalized.

---

### 3.9 🟢 Multi-Channel Artist Grouping
**Status:** Not started. Known gap from 1.1.
**What:** `build_data_json.py` currently treats each channel_url as a distinct artist. Ren has at least 3 channels (`Ren`, `Ren - Topic`, `RenMakesStuff`) that should appear merged under one artist entry with `channel_count: 3`.
**Approach options:**
- A) Use `mb_artist_id` as the grouping key (most accurate, requires MB match)
- B) User-defined merge rules file (`channel_merges.txt`)
- C) Normalize `norm_name` after Topic/VEVO stripping (approximate, fast)

 

---

## Phase 4 — Future (Design Awareness Only)

### 4.1 ⚪ Featured Artist Pages
Full implementation: `profile.md` + `arcs.json` + `affiliations.json` per artist.
Ren Gill and Gorillaz are the first two. Currently, bio and arcs are hardcoded in `index.html` JS (`ARTIST_META`). These must be moved to external files before adding a third featured artist.
Prerequisite: Admin page, document management decision.

### 4.2 ⚪ Deep Search
Search across all metadata: notes, display text, tags, affiliations.
Currently search only covers artist names, song titles, channel names, and recent video titles.
Prerequisite: Song table populated, notes field flowing through pipeline.

### 4.3 ⚪ Playlist Builder
UI for building and saving playlists.
Prerequisite: Deep search, usage patterns from plain-text playlists.

### 4.4 ⚪ Document Management System
Decision needed: Option A (folders + manifest), B (Obsidian/Joplin), or C (git + markdown).
Prerequisite: Determined before building any content sections.

### 4.5 ⚪ MusicBrainz Refresh / Re-enrichment
TTL-based re-fetch of MB data. Currently `mb_cached_at` is stored but no TTL logic is enforced.
After first full run, add: skip records cached within N days (suggested: 90 days for artists, 30 for recordings).

---

## Open Questions / Decisions Needed

1. **Multi-channel artist grouping** — How to merge channels like `Ren`, `Ren - Topic`, `RenMakesStuff` into one artist? See 3.9 above. Decision required before rebuild produces correct channel_count.

2. **Rules template file format** — What should the external cleaning rules format look like? See 2.3. Should it be a simple INI-style file, YAML, or a custom DSL? Curator-friendliness is the priority.

3. **Hyphen disambiguation in titles** — `"Artist - Title"` vs `"Artist - Featured Artist"`. Currently the artist prefix is stripped using `norm_name`. This works well for known artists but may strip incorrectly for titles that genuinely start with a hyphenated phrase. Auto-flag for review, or attempt to resolve programmatically first?

4. **Theme naming** — What to call the three themes? Suggestions: `Neon` (current), `Midnight`, `Daylight`?

5. **Document management** — Which option (A/B/C above) before content sections are built?

6. **Notes field pipeline** — The `notes` column is referenced in design but does not yet flow from any input file through to the DB or site. Where/how does the curator add notes? Admin page? Directly editing `name_file.txt`?


## 





---
## Items Flagged for Special Attention

These are completed items with known gaps, or design decisions that were deferred:

| Item | Issue |
|------|-------|
| `channel_count` in `build_data_json.py` | Always 1; multi-channel grouping not implemented |
| Title cleaning rules in `build_watchlog_db.py` | Hardcoded Python lists — should be external template file |
| `notes` field | Exists in design, not in pipeline or DB yet |
| `build_watchlog_db.py` on real data | Only tested with small fixtures; first real run may surface edge cases |
| Songs deduplication key | Falls back to `artist+cleaned_title` string when no MB match — susceptible to title variation across versions/remixes |
| `ARTIST_META` in `index.html` | Ren + Gorillaz bios hardcoded in JS. Third featured artist requires moving to external files first |
| `data.json` | Still the old hand-built file. Site shows no songs/MB data until pipeline runs |

---

*See CLAUDE.md for full context on design philosophy, data rules, and architecture decisions.*
# Updated 2026-04-96
