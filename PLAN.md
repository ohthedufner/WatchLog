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
## Artist Linking
Table ARTIST_LINK
  ID (int, increment)
  ARTIST_1_ID
  ARTIST_2_ID
  RELATIONSHIP (text field)

This could get messy since their is no dominate artist to place in ARTIST_1_ID. They carry equal weight
Duplicates must not be allowed
The method of displaying these is not fully worked out

Here are samples:

Artist Page: Ren
- See also:
  - Trick the Fox
  - Ren and Sam Thompkins
  - The Big Push

Artist Page: The Big Push
- See also:
  - Ren
  - Romain....
  - Goran.....

## Channel Linking
We can't expect every Artist to have a channel so:
- Channels are on the channel  page
- Channels will always have a channel_creator as mentioned earlier
- Some artists wil undoubtably have a page without having their own channel. This edge case must be addresses 

# Channel overrides
 - The easiest case is if an artist has only one channel of their own
 - There are two cases I have identified where an artist has multiple channels
   - They have done this for better organition of their content
     - Tn this case, each can move to the artist page and used to group videos under their artist page. The separtate channels no longer need to be treated as separate artists.  THE CHANNELS WILL STILL BE LISTED SEPARATELY ON THE CHANNEL PAGE
     - Example: RenMakesStuff, RenMakesMusic
    -The artist seems to have created a second channel for no apparent reason. The channel however does exist. In YouTube Takeout. The CHANNEL WILL REMAIN SEPARATE ON THE CHANNEL PAGE. On the artist page, there will be no grouping based on channel.
      - Example: Adian347, ADIAN347


1. **Rules template format** — INI-style, YAML, or custom DSL? See 2.3. Curator-friendliness is priority.
  ** Explain in more detail. I have worked with INI files and YAML but small example of each will be helpful do decide
1. **Theme naming** — Suggestions: `Neon` (current), `Midnight`, `Daylight`?
   ** Themes> Current im neon. Adopt Midnight and Daylight. Good choices

2. **Document management** — Which option (A/B/C) before content sections are built? See 5.7.
3. A or C. Explain these options further

4. **Notes field** — `notes` column referenced in design but not in pipeline or DB. Where/how does the curator add notes? Admin page? Direct edit in `wl.db`?
  ** Notes for artist, song and channel for now.

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

## CLARiFICATION ON ARTISTS, TITLES CHANNELS

# General
A more clear deniniton of music / Other needs to be made.
There are two sides to theis system Music and Other
videos and channels not marked at music must be accessible to catch edge cases that need to move to music section
Focus will be on music related content until further notice
The section for non-music (other) channels and videos will now only be visible and available in the adimin section

# *Artist, Video creator and channel
Until now, the artist and video creator are now two fields, They will be maintained by the human currator.
video creator (the norm_name) will ve associated with the channel as the channel will be considered their creation
Artist will be changed on a per-video basis by the curator to specify the artist that is the subject of the video.

Examples:
  Video_creator: Hexkind (this is the norm_name for the channel and every video in on this channel)
  Artist: Ren (Hexkind creates videos associated with multiple artists. Many of them are Ren.

  Video_creator: Ren (channel : RenMakesMusic
  Artist : Ren

  Video_creator: Trick the Fox (name assocciated with the channel)
  Artist: Trick the Fpx (Artist of the video)

# Videos, songs and other types of music content
This pertains the the music side of Watchlog only.
*NOT ALL VIDEOS IN THE MUSIC SECTION OF WATCHLOG ARE ACTUALLY VIDEOS
The CONTENT_TYPE  will be filled with defaul values as shown below after the iist of types below
Often these will have to be tagged by the curator of the dataase

# CONTENT_TYPE will be restricted to the short list below.
To handle edge cases that irriate the curator, there will an option "Other - "
  Upon selection of "Other - " a field must be activated to add an 8 character alphanumeric tag.
  This will be saved and displayed as " 

# CONTENT_TYPE options available
  AUDIO ONLY 
  MUSIC VIDEO
  LYRIC VIDEO
  VISUALIZER
  MEDLEY (considered one song but uses all or parts of other songS)
  MUSIC SET (a concert or multiple songs contained in one video)
  BTS - Behind the sceens (this is associdated with one video)
  SPOKEN - Primarily spoken like a poem. May have some music as well
  REACTION - Creators of reaction videos to songs
  BIO - Biographic, background or history
  CLIPS - usually craeations compilied on other fan sites
  OTHER - 
  
# Default CONTENT_TYPE
AUDIO ONLY - default for content impported from YouTube Music takeout files
MUSIC VIDEO will be the default for others uness these key works are found in the YouTube Title
- BTS
- Visualizer
- Poem ( content_type: SPOKEN)
- Reaction
- Lyric
- Fan Compilationm
  
* suggestings for other default filers here will be helpful





---

## Bugs & Fixes
*Logged: 2026-04-14 — from full Playwright browser test of http://localhost:8000*

---

### BUG-01 🔴 Home — "Music Plays" stat card always shows 0
**What failed:** The "Music Plays" stat card on the home page displays `0` regardless of actual play counts (Ren alone has 1,549).
**Why it failed:** `watchlog.js:217` reads `cc.music` (lowercase). `data.json` stores the key as `'Music'` (capital M). JavaScript object key lookup is case-sensitive — `cc.music` is always `undefined`, which falls back to `0`.
**Recommended fix:** In `watchlog.js`, change `cc.music||0` → `cc['Music']||0`. Or normalize keys to lowercase in `build_data_json.py` when writing `cat_counts`.

---

### BUG-02 🔴 Home — "Other" stat card always shows 0
**What failed:** The "Other" stat card displays `0`.
**Why it failed:** `watchlog.js:220` sums `cc.tv + cc.tech + cc.food + cc.comedy + cc.gaming` — six hardcoded lowercase keys. The actual `cat_counts` in `data.json` only ever has `{'Music': 3904}` — none of those keys exist.
**Recommended fix:** Replace the hardcoded sum with a dynamic sum of all non-Music keys: `Object.entries(cc).filter(([k])=>k!=='Music').reduce((s,[,v])=>s+v, 0)`.

---

### BUG-03 🔴 Channels page — completely empty ("No channels found")
**What failed:** The Channels page renders with no data. The category tab shows only "ALL" and the grid shows `No channels found`.
**Why it failed:** `watchlog.js:79` populates the channel list from `DB.other_channels`, which maps to `data.json`'s `other_channels` key. That key is populated by `build_data_json.py` from the `dj_other_channels` table — which contains *non-music* channels only. Per the current design, non-music channels are excluded from the main viewer. Since all 3,904 watch events are categorized as Music, `dj_other_channels` has 0 rows.
**Consequence:** The "Total Watches" stat card (which `onclick` routes to `#channels`) and the "All channels →" button on the home page both lead to an empty page.
**Recommended fix:** This is a design decision. Two options:
- A) Repurpose the Channels page to show music artist channels (derived from `dj_artists[].channels`). Requires restructuring how channels are surfaced in `data.json` and the JS.
- B) Remove the Channels nav link and stat card routing until channel data is available. Replace "All channels →" with "All artists →".
Option B is the faster fix. Option A aligns better with the intended feature.

---

### BUG-04 🟡 Song detail — raw YouTube ID displayed as video title
**What failed:** On the "What You Want" song detail page (`#song/ren/what-you-want`), one of the three source videos shows the raw YouTube ID `08m3rcDA4tw` as its title instead of a human-readable title.
**Why it failed:** This video has no title stored in `wl_videos` (the title field is NULL or empty — likely a deleted or unavailable video that was never resolved). The display code renders whatever is in the title field with no fallback.
**Recommended fix:** In `build_data_json.py` or the JS rendering code, fall back to `[Unavailable]` (or similar) when `wl_title` is NULL or is a raw YouTube ID (matches `^[A-Za-z0-9_-]{11}$`).

---

### BUG-05 🟡 Songs — "Stylo (Labrinth Remix" split incorrectly: closing paren in artist field
**What failed:** The song titled `Stylo (Labrinth Remix` appears with artist `Gorillaz ft. Tinie Tempah)`. The closing parenthesis ended up in the artist field instead of the title.
**Why it failed:** The title-cleaning regex in `build_watchlog_db.py` extracted the featured artist from inside a parenthetical but split incorrectly — the `)` boundary was consumed by the feat-artist extraction pattern, stripping it from the title without appending it back.
**Recommended fix:** Review `FEAT_PATTERNS` regex in `build_watchlog_db.py`. After extracting a feat artist from a parenthetical group, ensure the remainder of that group (including the closing `)` and any trailing text) is either retained in `cleaned_title` or discarded cleanly — not left as a dangling character on the artist string.

---

### BUG-06 🟡 Songs — "Ren" appears as song title (from "Ren Ft. Kit - Slaughter House")
**What failed:** A song row titled `Ren` with artist `Ren ft. Kit - Slaughter House` appears in the Songs grid. The song title should be `Slaughter House` and the artist `Ren ft. Kit`.
**Why it failed:** The artist-prefix stripping in `build_watchlog_db.py` removed `Ren Ft. Kit - ` from the front of the title but then stored the remainder `Slaughter House` under the title field — however, what was left as the `cleaned_title` was only `Ren` (the prefix before `Ft.`), not the post-dash token.
**Recommended fix:** When stripping an `artist - song` prefix with a `Ft.` in the artist portion, the song title should be the text *after* the final ` - ` separator, not before it.

---

### BUG-07 🟡 Songs — "Ren & Sam Tompkins - Blind Eyed" not cleaned from title
**What failed:** A song titled `Ren & Sam Tompkins - Blind Eyed` appears with artist `Ren ft. Angry Car Park Attendant`. The artist prefix `Ren & Sam Tompkins` was not stripped from the title.
**Why it failed:** The artist-prefix stripping regex handles `Artist - Song` and `Artist ft. X - Song` patterns, but not `Artist & CoArtist - Song` — an ampersand-joined dual-artist prefix that doesn't contain `ft.`/`feat.`.
**Recommended fix:** Add an ampersand-joined dual-artist prefix pattern to `FEAT_PATTERNS` or the prefix-stripping step: detect `[Name] & [Name] - ` as a strippable prefix and extract both artists as the primary/feat artists.

---

### BUG-08 🟢 Songs — "Love Music, Pt. 4" and "Love Music, Part 4" appear as separate songs
**What failed:** Two distinct song rows exist: `Love Music, Pt. 4` and `Love Music, Part 4`, both by Ren. These are the same song.
**Why it failed:** The title normalization step does not treat `Pt.` and `Part` as equivalent strings during deduplication. The `wl_songs` deduplication key is `(normalized_title, normalized_artist)`, and these two forms produce different normalized strings.
**Recommended fix:** Add `Pt.` → `Part` (or vice versa) to the title normalization step before computing the deduplication key in `build_watchlog_db.py`.

---

### BUG-09 🟢 Songs — "Release Year" sort has no effect (same order as Most Played)
**What failed:** Selecting "Release Year" in the sort dropdown on the Songs page produces the same ordering as "Most Played".
**Why it failed:** This is a data gap, not a code bug. All `wl_songs` rows have NULL release year because MB recording enrichment has not been run (0 MB recording matches). When all sort keys are NULL/0, the sort falls back to insertion order, which happens to match play count order.
**Recommended fix:** No code fix needed — this resolves when MB recording enrichment runs (Phase 5.3). Optionally, display a subtle UI note on the sort dropdown when year data is sparse: e.g., `Release Year (limited data)`.

---

### BUG-10 🟢 Nav search bar — retains previous query across page navigations
**What failed:** After using an affiliate chip search (e.g., clicking "The Big Push" on Ren's page), the nav search bar displays `The Big Push` on all subsequent page visits, including the Home and Songs pages.
**Why it failed:** The `searchAffil()` function sets the nav search input value to trigger a search result, but never clears it afterward. The nav bar input value persists in the DOM.
**Recommended fix:** In `searchAffil()`, after navigating to `#search`, clear the input value (or reset it after a short delay): `document.getElementById('navSearch').value = ''`. Alternatively, clear the input when navigating away from `#search`.

---

### BUG-12 ⚪ Remove "X ago" timestamps from artist, song, and channel list rows
**What failed:** The artist list (and likely song/channel lists) display "last watched" relative timestamps like "3 months ago" or "2 days ago". This data is not meaningful or relevant to the viewer.
**Scope:** Remove `ago()` display from all three list pages (Artists, Songs, Channels). Do not change the underlying `latest` field or pipeline — the data can stay in `data.json`. Display change only.
**Dependency:** Hold until a batch of DB/display field decisions are ready to implement together. No urgency.

---

### BUG-11 ⚪ favicon.ico missing (404 on every page load)
**What failed:** Every page load logs `404 NOT FOUND` for `http://localhost:8000/favicon.ico`.
**Why it failed:** No `favicon.ico` file exists in the project root.
**Recommended fix:** Add a `favicon.ico` (or `<link rel="icon" href="...">` in `index.html` pointing to a PNG). Low priority.

---

*See CLAUDE.md for architecture decisions, field naming convention, table groups, and design philosophy.*
