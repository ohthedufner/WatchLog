"""
build_watchlog_db.py
====================
Reads preprocess.py output files and builds watchlog.db (SQLite).

Steps:
  1. Import channels from name_file.txt
  2. Import videos from name_title_file.txt (all fields verbatim)
  3. Apply title cleaning rules — stores cleaned_title, feat_artist,
     stripped_text (JSON array of every piece removed, with type label)
  4. Match music channels to MusicBrainz artists
  5. Match music videos to MusicBrainz recordings
  6. Build songs table (deduplicated canonical songs)

Usage:
  python build_watchlog_db.py --channels name_file.txt --videos name_title_file.txt
  python build_watchlog_db.py --channels name_file.txt --videos name_title_file.txt --skip-mb
  python build_watchlog_db.py --channels name_file.txt --videos name_title_file.txt --mb-limit 100

Rate limiting: MusicBrainz requires ≤1 req/sec.
  All results are cached in the DB — re-runs skip already-fetched records.
  Use --skip-mb to build the DB without any network calls.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone


# ===========================================================================
# CLEANING RULES LOADER
# ===========================================================================

_RULES_FILE = os.path.join(os.path.dirname(__file__), "cleaning_rules.yaml")


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
        return s[1:-1]
    return s


def _load_cleaning_rules(path):
    """
    Minimal YAML loader for cleaning_rules.yaml.
    Handles top-level string-list sections and one string-mapping section.
    Comments and blank lines are ignored. All regex patterns compiled IGNORECASE.
    Returns dict with keys: feat_patterns, noise_suffix_literals,
    noise_regex_patterns, media_type_map.
    """
    result = {}
    current_key = None
    is_mapping = False

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip()
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#"):
                continue

            if not line[0].isspace():
                # Top-level key
                current_key = line.rstrip(": \t")
                is_mapping = False
                result[current_key] = None
            elif stripped.startswith("- "):
                # List item
                value = _unquote(stripped[2:])
                if result[current_key] is None:
                    result[current_key] = []
                result[current_key].append(value)
            elif ":" in stripped:
                # Mapping entry  key: value
                idx = stripped.index(":")
                k = _unquote(stripped[:idx])
                v = _unquote(stripped[idx + 1:])
                if result[current_key] is None:
                    result[current_key] = []
                    is_mapping = True
                result[current_key].append((k, v))

    # Compile regex lists
    rules = {}
    rules["feat_patterns"] = [
        re.compile(p, re.IGNORECASE) for p in (result.get("feat_patterns") or [])
    ]
    rules["noise_suffix_literals"] = result.get("noise_suffix_literals") or []
    rules["noise_regex_patterns"] = [
        re.compile(p, re.IGNORECASE) for p in (result.get("noise_regex_patterns") or [])
    ]
    rules["media_type_map"] = result.get("media_type_map") or []
    return rules


_RULES = _load_cleaning_rules(_RULES_FILE)


# ===========================================================================
# CONSTANTS
# ===========================================================================

DELIMITER = "|"
DB_FILE = "watchlog.db"

MB_BASE = "https://musicbrainz.org/ws/2"
MB_USER_AGENT = "WatchLog/1.0 (dufner6161@gmail.com)"
MB_RATE_LIMIT_SEC = 1.1   # slightly over 1s to be safe
MB_ACCEPT_SCORE = 85       # min score to auto-accept MB match
MB_REVIEW_SCORE = 60       # min score to flag for manual review (below = no match stored)


# ===========================================================================
# SCHEMA
# ===========================================================================

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS channels (
    -- Takeout fields (verbatim from name_file.txt)
    channel_url     TEXT PRIMARY KEY,
    raw_name        TEXT,
    norm_name       TEXT,
    category        TEXT,
    title_count     INTEGER,
    total_plays     INTEGER,
    date_first      TEXT,
    date_last       TEXT,
    -- MusicBrainz artist fields
    mb_artist_id    TEXT,
    mb_artist_name  TEXT,
    mb_sort_name    TEXT,
    mb_country      TEXT,
    mb_type         TEXT,
    mb_begin_date   TEXT,
    mb_end_date     TEXT,
    mb_disambiguation TEXT,
    mb_tags         TEXT,   -- JSON array of top MB tags/genres
    mb_confidence   INTEGER,
    mb_status       TEXT,   -- accepted | review | no_match | pending | skipped
    mb_cached_at    TEXT,
    e_tag           TEXT    -- 1-char curator tag, definition TBD
);

CREATE TABLE IF NOT EXISTS videos (
    -- Surrogate key (video_id can be blank for deleted/unavailable entries)
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Takeout fields (verbatim from name_title_file.txt)
    video_id        TEXT,
    norm_name       TEXT,
    raw_name        TEXT,
    channel_url     TEXT REFERENCES channels(channel_url),
    category        TEXT,
    title           TEXT,   -- raw title, never modified
    title_url       TEXT,
    date_first      TEXT,
    date_last       TEXT,
    play_count      INTEGER,
    -- Derived cleaning fields
    cleaned_title   TEXT,   -- title after all noise removal
    feat_artist     TEXT,   -- comma-separated featured artists extracted from title
    stripped_text   TEXT,   -- JSON array: [{type, text}, ...] of everything removed
    media_type      TEXT,   -- canonical content type: Official Music Video | Official Audio | Official Video | Official Lyric Video | Live | Acoustic | Visualizer | Music Video
    -- MusicBrainz recording fields
    mb_recording_id TEXT,
    mb_song_name    TEXT,   -- canonical title from MB
    mb_artist_id    TEXT,
    mb_artist_credit TEXT,  -- full artist credit string from MB
    mb_release_id   TEXT,
    mb_release_title TEXT,
    mb_release_date TEXT,
    mb_release_type TEXT,   -- Album, Single, EP, etc.
    mb_isrc         TEXT,   -- comma-separated if multiple
    mb_duration_ms  INTEGER,
    mb_confidence   INTEGER,
    mb_status       TEXT,   -- accepted | review | no_match | pending | skipped
    mb_cached_at    TEXT,
    e_tag           TEXT    -- 1-char curator tag, definition TBD
);

CREATE INDEX IF NOT EXISTS idx_videos_video_id     ON videos(video_id);
CREATE INDEX IF NOT EXISTS idx_videos_channel_url  ON videos(channel_url);
CREATE INDEX IF NOT EXISTS idx_videos_category     ON videos(category);
CREATE INDEX IF NOT EXISTS idx_videos_mb_status    ON videos(mb_status);

CREATE TABLE IF NOT EXISTS songs (
    -- One row per unique canonical song
    song_id         TEXT PRIMARY KEY,   -- system UUID (hex timestamp + counter)
    -- Best available title
    mb_recording_id TEXT,               -- from MB (null = unmatched)
    mb_song_name    TEXT,               -- canonical title from MB
    cleaned_title   TEXT,               -- our cleaned title (always present)
    -- Artist
    channel_url     TEXT,               -- primary artist channel_url
    artist_name     TEXT,               -- norm_name
    mb_artist_id    TEXT,
    feat_artist     TEXT,               -- extracted featured artists
    -- Release info
    mb_release_date TEXT,
    isrc            TEXT,
    mb_confidence   INTEGER,
    -- Curation
    notes           TEXT,
    video_count     INTEGER DEFAULT 0,  -- how many video rows map here
    e_tag           TEXT                -- 1-char curator tag, definition TBD
);

CREATE INDEX IF NOT EXISTS idx_songs_mb_recording_id ON songs(mb_recording_id);
CREATE INDEX IF NOT EXISTS idx_songs_artist_name      ON songs(artist_name);

CREATE TABLE IF NOT EXISTS run_log (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at          TEXT,
    channels_file   TEXT,
    videos_file     TEXT,
    channels_loaded INTEGER,
    videos_loaded   INTEGER,
    mb_artists_matched INTEGER,
    mb_recordings_matched INTEGER,
    songs_built     INTEGER,
    notes           TEXT
);
"""


# ===========================================================================
# DATABASE HELPERS
# ===========================================================================

def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # Migration: add columns that may not exist in older DBs
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection):
    """Add any new columns to existing tables without destroying data."""
    video_cols   = {row[1] for row in conn.execute("PRAGMA table_info(videos)")}
    channel_cols = {row[1] for row in conn.execute("PRAGMA table_info(channels)")}
    song_cols    = {row[1] for row in conn.execute("PRAGMA table_info(songs)")}

    if "media_type" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN media_type TEXT")
        print("  [migrate] Added media_type column to videos table.")
    if "e_tag" not in video_cols:
        conn.execute("ALTER TABLE videos ADD COLUMN e_tag TEXT")
        print("  [migrate] Added e_tag column to videos table.")
    if "e_tag" not in channel_cols:
        conn.execute("ALTER TABLE channels ADD COLUMN e_tag TEXT")
        print("  [migrate] Added e_tag column to channels table.")
    if "e_tag" not in song_cols:
        conn.execute("ALTER TABLE songs ADD COLUMN e_tag TEXT")
        print("  [migrate] Added e_tag column to songs table.")


# ===========================================================================
# FILE READERS
# ===========================================================================

def read_pipe_file(path: str) -> list[dict]:
    """Read a pipe-delimited file with header row. Returns list of dicts."""
    rows = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return rows
    headers = [h.strip() for h in lines[0].split(DELIMITER)]
    for line in lines[1:]:
        line = line.rstrip("\n")
        if not line:
            continue
        parts = line.split(DELIMITER)
        # Pad if short, truncate if long (last field may contain pipe chars — unlikely)
        while len(parts) < len(headers):
            parts.append("")
        row = {headers[i]: parts[i] for i in range(len(headers))}
        rows.append(row)
    return rows


# ===========================================================================
# TITLE CLEANING
# ===========================================================================

# Cleaning rules loaded from cleaning_rules.yaml
FEAT_PATTERNS         = _RULES["feat_patterns"]
NOISE_SUFFIX_LITERALS = _RULES["noise_suffix_literals"]
NOISE_REGEX_PATTERNS  = _RULES["noise_regex_patterns"]
MEDIA_TYPE_MAP        = _RULES["media_type_map"]


def derive_media_type(stripped: list[dict]) -> str | None:
    """
    Inspect the stripped items produced by clean_title and return a canonical
    media_type string, or None if none of the stripped text signals a type.
    """
    combined = " ".join(item["text"].lower() for item in stripped)
    for fragment, label in MEDIA_TYPE_MAP:
        if fragment in combined:
            return label
    return None



def clean_title(raw_title: str, artist_name: str) -> dict:
    """
    Clean a video title and return a dict with:
      cleaned_title  : final cleaned song name
      feat_artist    : comma-separated featured artists (may be empty)
      stripped_text  : JSON string — list of {type, text} for everything removed
      media_type     : canonical content type derived from stripped text, or None

    Nothing in raw_title is discarded — it all appears in stripped_text or is kept.
    """
    working = raw_title
    stripped = []   # list of {type, text} dicts

    # --- 1. Strip leading artist prefix: "ArtistName - " ---
    if artist_name:
        prefix_pat = re.compile(
            r'^' + re.escape(artist_name) + r'\s*[-–]\s*',
            re.IGNORECASE
        )
        m = prefix_pat.match(working)
        if m:
            stripped.append({"type": "artist_prefix", "text": m.group(0)})
            working = working[m.end():]

    # --- 2. Extract featured artists ---
    feat_parts = []
    for pat in FEAT_PATTERNS:
        m = pat.search(working)
        if m:
            feat_parts.append(m.group(1).strip())
            stripped.append({"type": "feat_artist", "text": m.group(0)})
            working = working[:m.start()] + working[m.end():]
            working = working.strip()
            break   # one feat extraction per title (avoid double-match)

    # --- 3 & 4. Strip noise: loop until nothing more is removed ---
    # Runs literal suffix strip + regex patterns repeatedly until stable,
    # so stacked suffixes like "(Official Video) (Remastered 2012)" all get removed.
    overall_changed = True
    while overall_changed:
        overall_changed = False

        # Literal suffixes (from end)
        changed = True
        while changed:
            changed = False
            for suffix in NOISE_SUFFIX_LITERALS:
                if working.lower().endswith(suffix.lower()):
                    removed = working[-len(suffix):]
                    stripped.append({"type": "noise_suffix", "text": removed})
                    working = working[:-len(suffix)].strip()
                    changed = True
                    overall_changed = True
                    break

        # Regex patterns (anywhere in string)
        for pat in NOISE_REGEX_PATTERNS:
            m = pat.search(working)
            if m:
                stripped.append({"type": "noise_suffix_re", "text": m.group(0)})
                working = (working[:m.start()] + working[m.end():]).strip()
                overall_changed = True

    cleaned = working.strip(" -–|")

    return {
        "cleaned_title": cleaned,
        "feat_artist":   ", ".join(feat_parts),
        "stripped_text": json.dumps(stripped, ensure_ascii=False),
        "media_type":    derive_media_type(stripped),
    }


# ===========================================================================
# MUSICBRAINZ CLIENT
# ===========================================================================

_last_mb_call: float = 0.0


def _mb_get(endpoint: str, params: dict) -> dict | None:
    """
    Make a rate-limited GET request to MusicBrainz WS2.
    Returns parsed JSON dict or None on error.
    """
    global _last_mb_call
    elapsed = time.monotonic() - _last_mb_call
    if elapsed < MB_RATE_LIMIT_SEC:
        time.sleep(MB_RATE_LIMIT_SEC - elapsed)

    params["fmt"] = "json"
    url = f"{MB_BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": MB_USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _last_mb_call = time.monotonic()
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _last_mb_call = time.monotonic()
        print(f"    [MB] Request failed: {e}")
        return None


def mb_search_artist(name: str) -> dict | None:
    """
    Search MB for an artist by name.
    Returns the top result dict (with added 'score' key) or None.
    """
    data = _mb_get("artist", {"query": f'artist:"{name}"', "limit": 5})
    if not data or not data.get("artists"):
        return None
    top = data["artists"][0]
    top["score"] = int(top.get("score", 0))
    return top


def mb_search_recording(title: str, artist: str, artist_id: str | None = None) -> dict | None:
    """
    Search MB for a recording by cleaned title + artist.
    Uses arid:{artist_id} when available (precise); falls back to fuzzy artist name.
    Returns the top result dict or None.
    """
    if artist_id:
        query = f'recording:"{title}" AND arid:{artist_id}'
    else:
        query = f'recording:"{title}" AND artist:"{artist}"'
    data = _mb_get("recording", {"query": query, "limit": 5})
    if not data or not data.get("recordings"):
        return None
    top = data["recordings"][0]
    top["score"] = int(top.get("score", 0))
    return top


# ===========================================================================
# IMPORT — CHANNELS
# ===========================================================================

def import_channels(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """
    Insert/replace channels. Returns count inserted.
    Preserves mb_* fields if the channel already exists and has a cached match.
    """
    cur = conn.cursor()
    inserted = 0
    for r in rows:
        url = r.get("channel_url", "").strip()
        if not url:
            url = f"__name__{r.get('raw_name', '')}"

        # Check if already in DB with MB data
        existing = cur.execute(
            "SELECT mb_cached_at FROM channels WHERE channel_url=?", (url,)
        ).fetchone()

        if existing and existing["mb_cached_at"]:
            # Already has MB data — update takeout fields only, preserve MB
            cur.execute("""
                UPDATE channels SET
                    raw_name=?, norm_name=?, category=?,
                    title_count=?, total_plays=?,
                    date_first=?, date_last=?
                WHERE channel_url=?
            """, (
                r.get("raw_name", ""),
                r.get("norm_name", ""),
                r.get("category", ""),
                int(r.get("title_count", 0) or 0),
                int(r.get("total_plays", 0) or 0),
                r.get("date_first", ""),
                r.get("date_last", ""),
                url,
            ))
        else:
            cur.execute("""
                INSERT OR REPLACE INTO channels
                    (channel_url, raw_name, norm_name, category,
                     title_count, total_plays, date_first, date_last,
                     mb_status)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                url,
                r.get("raw_name", ""),
                r.get("norm_name", ""),
                r.get("category", ""),
                int(r.get("title_count", 0) or 0),
                int(r.get("total_plays", 0) or 0),
                r.get("date_first", ""),
                r.get("date_last", ""),
                "pending",
            ))
            inserted += 1

    conn.commit()
    return inserted


# ===========================================================================
# IMPORT — VIDEOS
# ===========================================================================

def import_videos(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """
    Insert videos, apply title cleaning immediately.
    Skips rows that are already in the DB (matched by video_id + channel_url).
    Returns count inserted.
    """
    cur = conn.cursor()
    inserted = 0

    for r in rows:
        vid = r.get("video_id", "").strip()
        curl = r.get("channel_url", "").strip()
        norm = r.get("norm_name", "")
        title = r.get("title", "")

        # Deduplication check
        if vid:
            exists = cur.execute(
                "SELECT id FROM videos WHERE video_id=? AND channel_url=?",
                (vid, curl)
            ).fetchone()
            if exists:
                continue

        # Apply title cleaning
        cleaned = clean_title(title, norm)

        cur.execute("""
            INSERT INTO videos
                (video_id, norm_name, raw_name, channel_url, category,
                 title, title_url, date_first, date_last, play_count,
                 cleaned_title, feat_artist, stripped_text, media_type,
                 mb_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            vid or None,
            norm,
            r.get("raw_name", ""),
            curl or None,
            r.get("category", ""),
            title,
            r.get("title_url", ""),
            r.get("date_first", ""),
            r.get("date_last", ""),
            int(r.get("play_count", 0) or 0),
            cleaned["cleaned_title"],
            cleaned["feat_artist"],
            cleaned["stripped_text"],
            cleaned["media_type"],
            "pending",
        ))
        inserted += 1

    conn.commit()
    return inserted


# ===========================================================================
# MUSICBRAINZ ENRICHMENT — ARTISTS
# ===========================================================================

def enrich_artists(conn: sqlite3.Connection, limit: int | None = None,
                   channel_urls: list | None = None) -> int:
    """
    Match pending music channels to MusicBrainz artists.
    Returns count matched (accepted + review).
    If channel_urls is provided, only those channels are processed.
    """
    cur = conn.cursor()
    where = "WHERE category='music' AND (mb_status='pending' OR mb_status IS NULL)"
    params = []
    if channel_urls:
        placeholders = ','.join('?' * len(channel_urls))
        where += f" AND channel_url IN ({placeholders})"
        params.extend(channel_urls)
    query = f"""
        SELECT channel_url, norm_name, raw_name
        FROM channels
        {where}
        ORDER BY total_plays DESC
    """
    if limit:
        query += f" LIMIT {limit}"
    pending = cur.execute(query, params).fetchall()

    if not pending:
        print("  No pending music channels to match.")
        return 0

    print(f"  Matching {len(pending)} music channel(s) to MusicBrainz artists...")
    matched = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in pending:
        url = row["channel_url"]
        name = row["norm_name"] or row["raw_name"]
        print(f"    > {name}...", end=" ", flush=True)

        result = mb_search_artist(name)

        if result is None:
            cur.execute(
                "UPDATE channels SET mb_status=?, mb_cached_at=? WHERE channel_url=?",
                ("no_match", now, url)
            )
            print("no match")
            continue

        score = result.get("score", 0)
        tags = [t["name"] for t in result.get("tags", [])[:10]]

        if score >= MB_ACCEPT_SCORE:
            status = "accepted"
        elif score >= MB_REVIEW_SCORE:
            status = "review"
        else:
            status = "no_match"

        if status in ("accepted", "review"):
            cur.execute("""
                UPDATE channels SET
                    mb_artist_id=?, mb_artist_name=?, mb_sort_name=?,
                    mb_country=?, mb_type=?,
                    mb_begin_date=?, mb_end_date=?,
                    mb_disambiguation=?, mb_tags=?,
                    mb_confidence=?, mb_status=?, mb_cached_at=?
                WHERE channel_url=?
            """, (
                result.get("id"),
                result.get("name"),
                result.get("sort-name"),
                result.get("country"),
                result.get("type"),
                (result.get("life-span") or {}).get("begin"),
                (result.get("life-span") or {}).get("end"),
                result.get("disambiguation"),
                json.dumps(tags),
                score,
                status,
                now,
                url,
            ))
            print(f"{status} (score={score}): {result.get('name')}")
            matched += 1
        else:
            cur.execute(
                "UPDATE channels SET mb_status=?, mb_confidence=?, mb_cached_at=? WHERE channel_url=?",
                ("no_match", score, now, url)
            )
            print(f"no_match (score={score})")

    conn.commit()
    return matched


# ===========================================================================
# MUSICBRAINZ ENRICHMENT — RECORDINGS
# ===========================================================================

def enrich_recordings(conn: sqlite3.Connection, limit: int | None = None,
                      channel_urls: list | None = None,
                      accepted_only: bool = False) -> int:
    """
    Match pending music videos to MusicBrainz recordings.
    Uses arid:{mb_artist_id} when the channel has a MB match; falls back to norm_name.
    accepted_only=True restricts to channels with mb_status='accepted'.
    Returns count matched.
    """
    cur = conn.cursor()
    where = """WHERE v.category='music'
          AND v.cleaned_title IS NOT NULL
          AND v.cleaned_title != ''
          AND (v.mb_status='pending' OR v.mb_status IS NULL)"""
    params = []
    if accepted_only:
        where += " AND c.mb_status = 'accepted'"
    if channel_urls:
        placeholders = ','.join('?' * len(channel_urls))
        where += f" AND v.channel_url IN ({placeholders})"
        params.extend(channel_urls)
    query = f"""
        SELECT v.id, v.cleaned_title, v.norm_name, v.raw_name,
               c.mb_artist_id
        FROM videos v
        LEFT JOIN channels c ON v.channel_url = c.channel_url
        {where}
        ORDER BY v.play_count DESC
    """
    if limit:
        query += f" LIMIT {limit}"
    pending = cur.execute(query, params).fetchall()

    if not pending:
        print("  No pending music videos to match.")
        return 0

    print(f"  Matching {len(pending)} music video(s) to MusicBrainz recordings...")
    matched = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in pending:
        vid_row_id = row["id"]
        title = row["cleaned_title"]
        artist = row["norm_name"] or row["raw_name"]
        print(f"    > {artist} - {title[:50]}...", end=" ", flush=True)

        result = mb_search_recording(title, artist, artist_id=row["mb_artist_id"])

        if result is None:
            cur.execute(
                "UPDATE videos SET mb_status=?, mb_cached_at=? WHERE id=?",
                ("no_match", now, vid_row_id)
            )
            print("no match")
            continue

        score = result.get("score", 0)

        if score >= MB_ACCEPT_SCORE:
            status = "accepted"
        elif score >= MB_REVIEW_SCORE:
            status = "review"
        else:
            status = "no_match"

        if status in ("accepted", "review"):
            # Extract artist credit
            artist_credits = result.get("artist-credit", [])
            artist_credit_str = " ".join(
                ac.get("name") or ac.get("artist", {}).get("name", "")
                for ac in artist_credits
                if isinstance(ac, dict)
            )
            first_artist_id = None
            if artist_credits and isinstance(artist_credits[0], dict):
                first_artist_id = artist_credits[0].get("artist", {}).get("id")

            # Extract release info (first release)
            releases = result.get("releases", [])
            rel_id = rel_title = rel_date = rel_type = None
            if releases:
                rel = releases[0]
                rel_id    = rel.get("id")
                rel_title = rel.get("title")
                rel_date  = rel.get("date")
                rel_type  = (rel.get("release-group") or {}).get("primary-type")

            # Extract ISRCs
            isrcs = result.get("isrcs", [])
            isrc_str = ", ".join(isrcs) if isrcs else None

            cur.execute("""
                UPDATE videos SET
                    mb_recording_id=?, mb_song_name=?,
                    mb_artist_id=?, mb_artist_credit=?,
                    mb_release_id=?, mb_release_title=?,
                    mb_release_date=?, mb_release_type=?,
                    mb_isrc=?, mb_duration_ms=?,
                    mb_confidence=?, mb_status=?, mb_cached_at=?
                WHERE id=?
            """, (
                result.get("id"),
                result.get("title"),
                first_artist_id,
                artist_credit_str,
                rel_id, rel_title, rel_date, rel_type,
                isrc_str,
                result.get("length"),
                score,
                status,
                now,
                vid_row_id,
            ))
            print(f"{status} (score={score}): {result.get('title')}")
            matched += 1
        else:
            cur.execute(
                "UPDATE videos SET mb_status=?, mb_confidence=?, mb_cached_at=? WHERE id=?",
                ("no_match", score, now, vid_row_id)
            )
            print(f"no_match (score={score})")

    conn.commit()
    return matched


# ===========================================================================
# BUILD SONG TABLE
# ===========================================================================

def build_songs(conn: sqlite3.Connection) -> int:
    """
    Populate the songs table from matched videos.
    One row per unique (mb_recording_id OR cleaned_title+channel_url).
    Returns count of song rows created/updated.
    """
    cur = conn.cursor()
    cur.execute("DELETE FROM songs")   # rebuild from scratch

    rows = cur.execute("""
        SELECT
            v.mb_recording_id,
            v.mb_song_name,
            v.cleaned_title,
            v.channel_url,
            v.norm_name,
            v.mb_artist_id,
            v.feat_artist,
            v.mb_release_date,
            v.mb_isrc,
            v.mb_confidence,
            COUNT(*) AS video_count
        FROM videos v
        WHERE v.category='music'
        GROUP BY
            COALESCE(v.mb_recording_id, '__' || v.channel_url || '__' || v.cleaned_title)
        ORDER BY video_count DESC
    """).fetchall()

    inserted = 0
    counter = 0
    now_hex = format(int(time.time()), "x")

    for r in rows:
        song_id = f"{now_hex}_{counter:05d}"
        counter += 1
        cur.execute("""
            INSERT INTO songs
                (song_id, mb_recording_id, mb_song_name, cleaned_title,
                 channel_url, artist_name, mb_artist_id, feat_artist,
                 mb_release_date, isrc, mb_confidence, video_count)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            song_id,
            r["mb_recording_id"],
            r["mb_song_name"],
            r["cleaned_title"],
            r["channel_url"],
            r["norm_name"],
            r["mb_artist_id"],
            r["feat_artist"],
            r["mb_release_date"],
            r["mb_isrc"],
            r["mb_confidence"],
            r["video_count"],
        ))
        inserted += 1

    conn.commit()
    return inserted


# ===========================================================================
# STATS REPORT
# ===========================================================================

def print_stats(conn: sqlite3.Connection):
    cur = conn.cursor()

    ch = cur.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    ch_music = cur.execute("SELECT COUNT(*) FROM channels WHERE category='music'").fetchone()[0]
    ch_mb = cur.execute("SELECT COUNT(*) FROM channels WHERE mb_status='accepted'").fetchone()[0]
    ch_review = cur.execute("SELECT COUNT(*) FROM channels WHERE mb_status='review'").fetchone()[0]

    v = cur.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    v_music = cur.execute("SELECT COUNT(*) FROM videos WHERE category='music'").fetchone()[0]
    v_mb = cur.execute("SELECT COUNT(*) FROM videos WHERE mb_status='accepted'").fetchone()[0]
    v_review = cur.execute("SELECT COUNT(*) FROM videos WHERE mb_status='review'").fetchone()[0]
    v_pending = cur.execute("SELECT COUNT(*) FROM videos WHERE mb_status='pending'").fetchone()[0]

    songs = cur.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    songs_mb = cur.execute("SELECT COUNT(*) FROM songs WHERE mb_recording_id IS NOT NULL").fetchone()[0]

    cats = cur.execute("""
        SELECT category, COUNT(*) c FROM videos GROUP BY category ORDER BY c DESC
    """).fetchall()

    sep = "-" * 43
    print(f"\n{sep}")
    print("  WatchLog DB Stats")
    print(sep)
    print(f"  Channels : {ch:>6}  ({ch_music} music)")
    print(f"    MB matched : {ch_mb} accepted, {ch_review} review")
    print(f"  Videos   : {v:>6}  ({v_music} music)")
    print(f"    MB matched : {v_mb} accepted, {v_review} review")
    print(f"    Pending MB : {v_pending}")
    print(f"  Songs    : {songs:>6}  ({songs_mb} with MB ID)")
    print(sep)
    print("  Category breakdown:")
    for cat in cats:
        print(f"    {cat[0]:<14} {cat[1]:>6}")
    print(sep)


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(
        description="Build watchlog.db from preprocess.py output files"
    )
    parser.add_argument(
        "--channels", metavar="NAME_FILE",
        help="Path to name_file.txt (channel index)"
    )
    parser.add_argument(
        "--videos", metavar="VIDEO_FILE",
        help="Path to name_title_file.txt (video catalog)"
    )
    parser.add_argument(
        "--db", default=DB_FILE,
        help=f"Output database path (default: {DB_FILE})"
    )
    parser.add_argument(
        "--skip-mb", action="store_true",
        help="Skip all MusicBrainz lookups (build DB only)"
    )
    parser.add_argument(
        "--mb-artists-only", action="store_true",
        help="Run only artist-level MB matching (skip recording lookup)"
    )
    parser.add_argument(
        "--mb-limit", type=int, metavar="N",
        help="Limit MB lookups to N records (for testing)"
    )
    parser.add_argument(
        "--mb-channel", metavar="URL", nargs="+",
        help="Restrict MB enrichment to these channel URL(s) only"
    )
    parser.add_argument(
        "--mb-accepted-only", action="store_true",
        help="Restrict recording enrichment to channels with mb_status=accepted"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Print DB stats and exit (no import/matching)"
    )
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  WatchLog DB Builder")
    print(f"  DB:  {args.db}")
    print(f"{'='*60}\n")

    conn = open_db(args.db)

    if args.stats:
        print_stats(conn)
        return

    run_ts = datetime.now(timezone.utc).isoformat()
    ch_loaded = v_loaded = mb_artists = mb_recordings = songs_built = 0

    # --- Import channels ---
    if args.channels:
        if not os.path.exists(args.channels):
            print(f"ERROR: channels file not found: {args.channels}")
            sys.exit(1)
        print(f"Loading channels from {args.channels}...")
        ch_rows = read_pipe_file(args.channels)
        ch_loaded = import_channels(conn, ch_rows)
        print(f"  {ch_loaded} channel rows imported ({len(ch_rows)} total in file).")

    # --- Import videos ---
    if args.videos:
        if not os.path.exists(args.videos):
            print(f"ERROR: videos file not found: {args.videos}")
            sys.exit(1)
        print(f"Loading videos from {args.videos}...")
        v_rows = read_pipe_file(args.videos)
        v_loaded = import_videos(conn, v_rows)
        print(f"  {v_loaded} video rows imported ({len(v_rows)} total in file).")

    # --- MusicBrainz enrichment ---
    if not args.skip_mb:
        if args.mb_channel:
            print(f"\nMusicBrainz enrichment restricted to {len(args.mb_channel)} channel(s).")
        print("\nMusicBrainz artist enrichment...")
        mb_artists = enrich_artists(conn, limit=args.mb_limit, channel_urls=args.mb_channel)
        print(f"  {mb_artists} artist(s) matched to MusicBrainz.")

        if not args.mb_artists_only:
            print("\nMusicBrainz recording enrichment...")
            mb_recordings = enrich_recordings(conn, limit=args.mb_limit, channel_urls=args.mb_channel, accepted_only=args.mb_accepted_only)
            print(f"  {mb_recordings} recording(s) matched to MusicBrainz.")
    else:
        print("Skipping MusicBrainz lookups (--skip-mb).")

    # --- Build song table ---
    print("\nBuilding song table...")
    songs_built = build_songs(conn)
    print(f"  {songs_built} unique song(s) in songs table.")

    # --- Log run ---
    conn.execute("""
        INSERT INTO run_log
            (run_at, channels_file, videos_file,
             channels_loaded, videos_loaded,
             mb_artists_matched, mb_recordings_matched, songs_built)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        run_ts,
        args.channels or "",
        args.videos or "",
        ch_loaded, v_loaded,
        mb_artists, mb_recordings, songs_built,
    ))
    conn.commit()

    print()
    print_stats(conn)
    print(f"\nDatabase written to: {args.db}\n")


if __name__ == "__main__":
    main()
