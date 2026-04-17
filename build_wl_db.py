"""
build_wl_db.py — Extract JSON source files into wl.db (SQLite)

Table prefix convention (per field naming standard):
  wh_  watch-history.json   (Google Takeout raw events)
  dj_  data.json            (aggregated display data)
  ad_  admin_data.json      (admin/music-channel detail)
  wl_  watchlog.db / user-edited data (songs, videos, links, curator tables)

Rebuild strategy:
  Pipeline tables (wh_, dj_, ad_) are dropped and recreated on every run.
  wl_videos, wl_songs, wl_song_video are PERSISTENT — new records are upserted,
  existing records updated (pipeline fields only). Curator-owned fields
  (wl_artist_id) are never overwritten after first assignment.
  User-edited tables (wl_artists, wl_artist_links, wl_channel_cats) use
  CREATE TABLE IF NOT EXISTS and are NEVER dropped.
"""

import json
import sqlite3
import os
import re

DB_PATH         = os.path.join(os.path.dirname(__file__), "wl.db")
WH_PATH         = os.path.join(os.path.dirname(__file__), "Google_Takeout", "watch-history.json")
DJ_PATH         = os.path.join(os.path.dirname(__file__), "data.json")
AD_PATH         = os.path.join(os.path.dirname(__file__), "admin_data.json")
WATCHLOG_DB_PATH = os.path.join(os.path.dirname(__file__), "watchlog.db")


def _slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


def _content_type(video_id, title, media_type, yt_music_ids):
    """Auto-assign wl_content_type from available signals. Curator can override."""
    if video_id in yt_music_ids:
        return 'AUDIO_ONLY'
    if 'audio' in (media_type or '').lower():
        return 'AUDIO_ONLY'
    t = (title or '').lower()
    if 'visualizer' in t:
        return 'VISUALIZER'
    if 'lyric' in t:
        return 'LYRIC_VIDEO'
    if 'bts' in t:
        return 'BTS'
    if 'poem' in t:
        return 'SPOKEN'
    if 'reaction' in t:
        return 'REACTION'
    if 'fan compilation' in t:
        return 'CLIPS'
    return 'MUSIC_VIDEO'


# Pipeline tables dropped and recreated on every build.
# wl_songs / wl_videos / wl_song_video are NOT in this list — they are persistent.
_PIPELINE_TABLES = [
    "dj_artist_videos", "dj_artists",
    "dj_other_videos", "dj_other_channels",
    "dj_recent", "dj_cat_counts", "dj_meta",
    "ad_channels", "ad_stats",
    "wh_events",
]


def migrate_schema(con):
    """One-time migrations to evolve persistent table schemas without data loss."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(wl_videos)")}
    if cols and 'wl_artist_id' not in cols:
        for t in ('wl_song_video', 'wl_videos', 'wl_songs'):
            con.execute(f"DROP TABLE IF EXISTS [{t}]")
        con.commit()
        print("Schema migration: rebuilt wl_videos/wl_songs/wl_song_video with wl_artist_id.")
        cols = set()  # fresh table, recheck below

    if cols and 'wl_content_type' not in cols:
        con.execute("ALTER TABLE wl_videos ADD COLUMN wl_content_type TEXT")
        con.commit()
        print("Schema migration: added wl_content_type to wl_videos.")


def reset_pipeline_tables(con):
    """Drop all pipeline tables. Persistent wl_ tables and user-edited tables are untouched."""
    for t in _PIPELINE_TABLES:
        con.execute(f"DROP TABLE IF EXISTS [{t}]")
    con.commit()
    print("Pipeline tables cleared (wl_ data and user data preserved).")


def create_schema(con):
    con.executescript("""
    -- ----------------------------------------------------------------
    -- wh_ tables  (source: Google_Takeout/watch-history.json)
    -- ----------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS wh_events (
        wh_id               INTEGER PRIMARY KEY AUTOINCREMENT,
        wh_header           TEXT,
        wh_title            TEXT,
        wh_title_url        TEXT,
        wh_channel_name     TEXT,
        wh_channel_url      TEXT,
        wh_time             TEXT
    );

    -- ----------------------------------------------------------------
    -- dj_ tables  (source: data.json)
    -- ----------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS dj_meta (
        dj_generated        TEXT,
        dj_total            INTEGER
    );

    CREATE TABLE IF NOT EXISTS dj_cat_counts (
        dj_category         TEXT PRIMARY KEY,
        dj_count            INTEGER
    );

    CREATE TABLE IF NOT EXISTS dj_recent (
        dj_id               INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_title            TEXT,
        dj_video_id         TEXT,
        dj_channel          TEXT,
        dj_date             TEXT,
        dj_category         TEXT,
        dj_url              TEXT
    );

    CREATE TABLE IF NOT EXISTS dj_artists (
        dj_artist_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_name             TEXT,
        dj_slug             TEXT,
        dj_plays            INTEGER,
        dj_latest           TEXT,
        dj_channel_count    INTEGER
    );

    CREATE TABLE IF NOT EXISTS dj_artist_videos (
        dj_av_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_artist_id        INTEGER REFERENCES dj_artists(dj_artist_id),
        dj_title            TEXT,
        dj_video_id         TEXT,
        dj_date             TEXT
    );

    CREATE TABLE IF NOT EXISTS dj_other_channels (
        dj_oc_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_name             TEXT,
        dj_category         TEXT,
        dj_channel_url      TEXT,
        dj_slug             TEXT,
        dj_plays            INTEGER,
        dj_latest           TEXT
    );

    CREATE TABLE IF NOT EXISTS dj_other_videos (
        dj_ov_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        dj_oc_id            INTEGER REFERENCES dj_other_channels(dj_oc_id),
        dj_title            TEXT,
        dj_video_id         TEXT,
        dj_date             TEXT,
        dj_category         TEXT
    );

    -- ----------------------------------------------------------------
    -- ad_ tables  (source: admin_data.json)
    -- ----------------------------------------------------------------
    CREATE TABLE IF NOT EXISTS ad_stats (
        ad_total_channels       INTEGER,
        ad_music_channels       INTEGER,
        ad_total_videos         INTEGER,
        ad_music_videos         INTEGER,
        ad_total_songs          INTEGER,
        ad_mb_matched_channels  INTEGER,
        ad_mb_matched_videos    INTEGER
    );

    CREATE TABLE IF NOT EXISTS ad_channels (
        ad_ch_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ad_url              TEXT UNIQUE,
        ad_name             TEXT,
        ad_plays            INTEGER,
        ad_mb_status        TEXT,
        ad_mb_name          TEXT,
        ad_mb_confidence    INTEGER,
        ad_music_videos     INTEGER,
        ad_pending_videos   INTEGER
    );

    -- ----------------------------------------------------------------
    -- wl_ user-edited tables  (NEVER dropped — survive all rebuilds)
    -- ----------------------------------------------------------------

    -- One row per artist. Default populated from norm_name on first import.
    -- MB enrichment fields filled by build_watchlog_db.py --mb-artists.
    -- wl_artist_id is the stable FK used by wl_videos and wl_songs.
    CREATE TABLE IF NOT EXISTS wl_artists (
        wl_artist_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_name         TEXT NOT NULL,
        wl_slug         TEXT UNIQUE,
        wl_sort_name    TEXT,
        mb_artist_id    TEXT,
        mb_country      TEXT,
        mb_type         TEXT,
        mb_begin_date   TEXT,
        mb_end_date     TEXT,
        mb_tags         TEXT,
        mb_confidence   INTEGER,
        mb_status       TEXT DEFAULT 'pending',
        mb_cached_at    TEXT,
        wl_notes        TEXT
    );

    -- Artist "See also" relationships.
    CREATE TABLE IF NOT EXISTS wl_artist_links (
        wl_al_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_from_slug    TEXT NOT NULL,
        wl_to_slug      TEXT NOT NULL,
        wl_label        TEXT NOT NULL DEFAULT 'See also',
        UNIQUE(wl_from_slug, wl_to_slug)
    );

    -- Curator-assigned channel categories.
    CREATE TABLE IF NOT EXISTS wl_channel_cats (
        wl_cc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_channel_url  TEXT NOT NULL UNIQUE,
        wl_category     TEXT NOT NULL
    );

    -- ----------------------------------------------------------------
    -- wl_ persistent tables  (not dropped — upserted on each rebuild)
    -- wl_artist_id is curator-owned: set on first import, never overwritten.
    -- ----------------------------------------------------------------

    -- One row per music video. Stable key: wl_video_id (YouTube ID).
    CREATE TABLE IF NOT EXISTS wl_videos (
        wl_vid_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_video_id         TEXT UNIQUE,        -- YouTube video ID
        wl_cleaned_title    TEXT,
        wl_title            TEXT,
        wl_channel_url      TEXT,
        wl_artist_name      TEXT,               -- norm_name from watchlog.db (display)
        wl_feat_artist      TEXT,
        wl_play_count       INTEGER,
        wl_date_first       TEXT,
        wl_date_last        TEXT,
        wl_media_type       TEXT,
        mb_recording_id     TEXT,
        mb_confidence       INTEGER,
        mb_status           TEXT,
        wl_artist_id        INTEGER REFERENCES wl_artists(wl_artist_id),
        wl_content_type     TEXT
    );

    -- One row per unique song title. Multiple videos (from any artist) link here.
    -- wl_match_basis: how the song was first identified ('title+artist' or 'title_only').
    CREATE TABLE IF NOT EXISTS wl_songs (
        wl_song_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_cleaned_title    TEXT,
        wl_artist_name      TEXT,               -- canonical artist (from first/highest-played video)
        wl_feat_artist      TEXT,
        wl_video_count      INTEGER DEFAULT 0,
        wl_match_basis      TEXT,
        mb_recording_id     TEXT,
        mb_song_name        TEXT,
        mb_artist_id        TEXT,
        mb_confidence       INTEGER,
        mb_status           TEXT,
        wl_notes            TEXT,
        wl_artist_id        INTEGER REFERENCES wl_artists(wl_artist_id)
    );

    -- Junction: one song → many videos.
    -- wl_match_type: 'exact' (verbatim title+artist), 'normalized' (same after lowercasing),
    --                'title_only' (same title, different artist — cross-artist link).
    CREATE TABLE IF NOT EXISTS wl_song_video (
        wl_sv_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_song_id          INTEGER REFERENCES wl_songs(wl_song_id),
        wl_vid_id           INTEGER REFERENCES wl_videos(wl_vid_id),
        wl_match_type       TEXT,
        UNIQUE(wl_song_id, wl_vid_id)
    );
    """)
    con.commit()


def load_watch_history(con):
    print("Loading watch-history.json ...", flush=True)
    with open(WH_PATH, encoding="utf-8") as f:
        events = json.load(f)

    rows = []
    for e in events:
        subs = e.get("subtitles") or []
        ch_name = subs[0].get("name") if subs else None
        ch_url  = subs[0].get("url")  if subs else None
        rows.append((
            e.get("header"),
            e.get("title"),
            e.get("titleUrl"),
            ch_name,
            ch_url,
            e.get("time"),
        ))

    con.executemany(
        "INSERT INTO wh_events (wh_header, wh_title, wh_title_url, wh_channel_name, wh_channel_url, wh_time) VALUES (?,?,?,?,?,?)",
        rows,
    )
    con.commit()
    print(f"  Inserted {len(rows):,} rows into wh_events")


def load_data_json(con):
    print("Loading data.json ...", flush=True)
    with open(DJ_PATH, encoding="utf-8") as f:
        d = json.load(f)

    # dj_meta
    con.execute("INSERT INTO dj_meta (dj_generated, dj_total) VALUES (?,?)",
                (d.get("generated"), d.get("total")))

    # dj_cat_counts
    for cat, cnt in (d.get("cat_counts") or {}).items():
        con.execute("INSERT INTO dj_cat_counts (dj_category, dj_count) VALUES (?,?)", (cat, cnt))

    # dj_recent
    recent_rows = [
        (r.get("t"), r.get("id"), r.get("ch"), r.get("ts"), r.get("cat"), r.get("url"))
        for r in (d.get("recent") or [])
    ]
    con.executemany(
        "INSERT INTO dj_recent (dj_title, dj_video_id, dj_channel, dj_date, dj_category, dj_url) VALUES (?,?,?,?,?,?)",
        recent_rows,
    )
    print(f"  Inserted {len(recent_rows):,} rows into dj_recent")

    # dj_artists + dj_artist_videos
    artist_count = 0
    av_count = 0
    for artist in (d.get("artists") or []):
        cur = con.execute(
            "INSERT INTO dj_artists (dj_name, dj_slug, dj_plays, dj_latest, dj_channel_count) VALUES (?,?,?,?,?)",
            (artist.get("name"), artist.get("slug"), artist.get("plays"),
             artist.get("latest"), artist.get("channel_count")),
        )
        artist_id = cur.lastrowid
        artist_count += 1
        vids = artist.get("videos") or []
        for v in vids:
            con.execute(
                "INSERT INTO dj_artist_videos (dj_artist_id, dj_title, dj_video_id, dj_date) VALUES (?,?,?,?)",
                (artist_id, v.get("t"), v.get("id"), v.get("ts")),
            )
            av_count += 1
    print(f"  Inserted {artist_count:,} rows into dj_artists, {av_count:,} into dj_artist_videos")

    # dj_other_channels + dj_other_videos
    oc_count = 0
    ov_count = 0
    for ch in (d.get("other_channels") or []):
        cur = con.execute(
            "INSERT INTO dj_other_channels (dj_name, dj_category, dj_channel_url, dj_slug, dj_plays, dj_latest) VALUES (?,?,?,?,?,?)",
            (ch.get("name"), ch.get("cat"), ch.get("curl"), ch.get("slug"),
             ch.get("plays"), ch.get("latest")),
        )
        oc_id = cur.lastrowid
        oc_count += 1
        for v in (ch.get("videos") or []):
            con.execute(
                "INSERT INTO dj_other_videos (dj_oc_id, dj_title, dj_video_id, dj_date, dj_category) VALUES (?,?,?,?,?)",
                (oc_id, v.get("t"), v.get("id"), v.get("ts"), v.get("cat")),
            )
            ov_count += 1
    print(f"  Inserted {oc_count:,} rows into dj_other_channels, {ov_count:,} into dj_other_videos")

    con.commit()


def load_admin_data(con):
    print("Loading admin_data.json ...", flush=True)
    with open(AD_PATH, encoding="utf-8") as f:
        d = json.load(f)

    # ad_stats
    s = d.get("stats") or {}
    con.execute(
        "INSERT INTO ad_stats VALUES (?,?,?,?,?,?,?)",
        (s.get("channels_total"), s.get("channels_music"), s.get("videos_total"),
         s.get("videos_music"), s.get("songs_total"),
         s.get("channels_mb"), s.get("songs_mb")),
    )

    # ad_channels
    ch_rows = [
        (c.get("url"), c.get("name"), c.get("plays"), c.get("mb_status"),
         c.get("mb_name"), c.get("mb_confidence"),
         c.get("music_videos"), c.get("pending_videos"))
        for c in (d.get("channels") or [])
    ]
    con.executemany(
        "INSERT INTO ad_channels (ad_url, ad_name, ad_plays, ad_mb_status, ad_mb_name, ad_mb_confidence, ad_music_videos, ad_pending_videos) VALUES (?,?,?,?,?,?,?,?)",
        ch_rows,
    )
    con.commit()
    print(f"  Inserted {len(ch_rows):,} rows into ad_channels")


def load_watchlog_db(con):
    """Upsert wl_videos, wl_songs, wl_artists, and wl_song_video from watchlog.db.

    Song matching order:
      1. title + artist match  → match_type 'exact' or 'normalized'
      2. title-only match      → match_type 'title_only' (cross-artist link to existing song)
      3. no match              → new song record created

    Curator-owned fields (wl_artist_id on videos and songs) are never
    overwritten after first assignment.
    """
    print("Loading watchlog.db ...", flush=True)

    src = sqlite3.connect(WATCHLOG_DB_PATH)
    src.row_factory = sqlite3.Row
    src_cur = src.cursor()
    src_cur.execute("""
        SELECT video_id, cleaned_title, title, channel_url, norm_name,
               feat_artist, play_count, date_first, date_last, media_type,
               mb_recording_id, mb_confidence, mb_status
        FROM   videos
        WHERE  category = 'music'
        ORDER  BY play_count DESC, cleaned_title
    """)
    videos = src_cur.fetchall()
    src.close()

    # --- Build YouTube Music video ID set (AUDIO_ONLY signal) ---
    yt_music_ids = set()
    for (url,) in con.execute(
        "SELECT wh_title_url FROM wh_events WHERE wh_header='YouTube Music' AND wh_title_url IS NOT NULL"
    ):
        if url and 'watch?v=' in url:
            yt_music_ids.add(url.split('watch?v=')[1].split('&')[0])

    # --- Load existing state from wl.db ---

    # youtube_video_id → wl_vid_id
    existing_vids = {}
    for row in con.execute("SELECT wl_vid_id, wl_video_id FROM wl_videos"):
        existing_vids[row[1]] = row[0]

    # title_key → (wl_song_id, canon_artist_key, canon_title, canon_artist)
    existing_songs = {}
    for row in con.execute("""
        SELECT wl_song_id,
               LOWER(TRIM(wl_cleaned_title)),
               LOWER(TRIM(COALESCE(wl_artist_name, ''))),
               wl_cleaned_title,
               COALESCE(wl_artist_name, '')
        FROM wl_songs
    """):
        existing_songs[row[1]] = (row[0], row[2], row[3], row[4])

    # name_lower → wl_artist_id
    existing_artists = {}
    for row in con.execute("SELECT wl_artist_id, LOWER(TRIM(wl_name)) FROM wl_artists"):
        existing_artists[row[1]] = row[0]

    new_vids = updated_vids = new_songs = new_artists = 0
    junction_rows = []  # (wl_song_id, wl_vid_id, match_type)

    for v in videos:
        cleaned_title = (v["cleaned_title"] or "").strip()
        artist_name   = (v["norm_name"]      or "").strip()
        feat_artist   = (v["feat_artist"]    or "").strip() or None
        video_id      = v["video_id"]

        title_key  = cleaned_title.lower()
        artist_key = artist_name.lower()

        # --- Ensure wl_artists row exists for this norm_name ---
        if artist_key and artist_key not in existing_artists:
            slug_val = _slugify(artist_name)
            cur = con.execute(
                "INSERT OR IGNORE INTO wl_artists (wl_name, wl_slug, mb_status) VALUES (?,?,'pending')",
                (artist_name, slug_val),
            )
            if cur.lastrowid:
                existing_artists[artist_key] = cur.lastrowid
                new_artists += 1
            else:
                # Slug collision — different name maps to same slug; fetch by slug
                row = con.execute(
                    "SELECT wl_artist_id FROM wl_artists WHERE wl_slug=?", (slug_val,)
                ).fetchone()
                if row:
                    existing_artists[artist_key] = row[0]

        artist_id   = existing_artists.get(artist_key)
        content_type = _content_type(video_id, v["title"], v["media_type"], yt_music_ids)

        # --- Upsert wl_videos ---
        if video_id not in existing_vids:
            cur = con.execute(
                """INSERT INTO wl_videos
                   (wl_video_id, wl_cleaned_title, wl_title, wl_channel_url,
                    wl_artist_name, wl_feat_artist, wl_play_count,
                    wl_date_first, wl_date_last, wl_media_type,
                    mb_recording_id, mb_confidence, mb_status,
                    wl_artist_id, wl_content_type)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (video_id, cleaned_title, v["title"], v["channel_url"],
                 artist_name, feat_artist, v["play_count"],
                 v["date_first"], v["date_last"], v["media_type"],
                 v["mb_recording_id"], v["mb_confidence"], v["mb_status"],
                 artist_id, content_type),
            )
            wl_vid_id = cur.lastrowid
            existing_vids[video_id] = wl_vid_id
            new_vids += 1
        else:
            wl_vid_id = existing_vids[video_id]
            # Update pipeline fields; wl_artist_id excluded (curator-owned).
            # wl_content_type: backfill if NULL, preserve if already set by curator.
            con.execute(
                """UPDATE wl_videos SET
                   wl_cleaned_title=?, wl_title=?, wl_channel_url=?,
                   wl_artist_name=?, wl_feat_artist=?, wl_play_count=?,
                   wl_date_first=?, wl_date_last=?, wl_media_type=?,
                   mb_recording_id=?, mb_confidence=?, mb_status=?,
                   wl_content_type=COALESCE(wl_content_type, ?)
                   WHERE wl_video_id=?""",
                (cleaned_title, v["title"], v["channel_url"],
                 artist_name, feat_artist, v["play_count"],
                 v["date_first"], v["date_last"], v["media_type"],
                 v["mb_recording_id"], v["mb_confidence"], v["mb_status"],
                 content_type, video_id),
            )
            updated_vids += 1

        # --- Song matching ---
        if title_key in existing_songs:
            wl_song_id, canon_artist_key, canon_title, canon_artist = existing_songs[title_key]
            if artist_key == canon_artist_key:
                match_type = (
                    "exact" if cleaned_title == canon_title and artist_name == canon_artist
                    else "normalized"
                )
            else:
                match_type = "title_only"
        else:
            # New song — first video for this title sets the canonical form
            cur = con.execute(
                """INSERT INTO wl_songs
                   (wl_cleaned_title, wl_artist_name, wl_feat_artist,
                    wl_match_basis, wl_artist_id)
                   VALUES (?,?,?,?,?)""",
                (cleaned_title, artist_name, feat_artist,
                 "title+artist" if artist_name else "title_only",
                 artist_id),
            )
            wl_song_id = cur.lastrowid
            existing_songs[title_key] = (wl_song_id, artist_key, cleaned_title, artist_name)
            new_songs += 1
            match_type = "exact"

        junction_rows.append((wl_song_id, wl_vid_id, match_type))

    # --- Insert junction rows (ignore duplicates from previous runs) ---
    con.executemany(
        "INSERT OR IGNORE INTO wl_song_video (wl_song_id, wl_vid_id, wl_match_type) VALUES (?,?,?)",
        junction_rows,
    )

    # --- Refresh video counts on all songs ---
    con.execute("""
        UPDATE wl_songs
        SET wl_video_count = (
            SELECT COUNT(*) FROM wl_song_video sv
            WHERE sv.wl_song_id = wl_songs.wl_song_id
        )
    """)

    con.commit()
    print(f"  Artists: {new_artists:,} new in wl_artists")
    print(f"  Videos:  {new_vids:,} new, {updated_vids:,} updated in wl_videos")
    print(f"  Songs:   {new_songs:,} new in wl_songs")
    print(f"  Junction: {len(junction_rows):,} rows processed in wl_song_video")


def main():
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA journal_mode=WAL")
    try:
        migrate_schema(con)
        reset_pipeline_tables(con)
        create_schema(con)
        load_watch_history(con)
        load_data_json(con)
        # Apply curator category overrides (wl_channel_cats survives rebuild)
        overrides = con.execute(
            "UPDATE dj_other_channels "
            "SET dj_category = (SELECT wl_category FROM wl_channel_cats WHERE wl_channel_url = dj_channel_url) "
            "WHERE dj_channel_url IN (SELECT wl_channel_url FROM wl_channel_cats)"
        ).rowcount
        if overrides:
            con.commit()
            print(f"  Applied {overrides} channel category overrides from wl_channel_cats")
        load_admin_data(con)
        load_watchlog_db(con)
        print("\nDone. Tables in wl.db:")
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            (cnt,) = con.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()
            print(f"  {name:<28} {cnt:>8,} rows")
    finally:
        con.close()


if __name__ == "__main__":
    main()
