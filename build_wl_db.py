"""
build_wl_db.py — Extract JSON source files into wl.db (SQLite)

Table prefix convention (per field naming standard):
  wh_  watch-history.json   (Google Takeout raw events)
  dj_  data.json            (aggregated display data)
  ad_  admin_data.json      (admin/music-channel detail)
  wl_  watchlog.db / user-edited data (songs, videos, links, curator tables)

Rebuild strategy:
  Pipeline tables (wh_, dj_, ad_, wl_songs/videos/song_video) are dropped and
  recreated on every run.  User-edited tables (wl_artist_links, future curator
  tables) use CREATE TABLE IF NOT EXISTS and are NEVER dropped — their data
  survives rebuilds.
"""

import json
import sqlite3
import os

DB_PATH         = os.path.join(os.path.dirname(__file__), "wl.db")
WH_PATH         = os.path.join(os.path.dirname(__file__), "Google_Takeout", "watch-history.json")
DJ_PATH         = os.path.join(os.path.dirname(__file__), "data.json")
AD_PATH         = os.path.join(os.path.dirname(__file__), "admin_data.json")
WATCHLOG_DB_PATH = os.path.join(os.path.dirname(__file__), "watchlog.db")


# Pipeline tables dropped and recreated on every build.
# Order matters for FK safety (children before parents).
_PIPELINE_TABLES = [
    "wl_song_video", "wl_videos", "wl_songs",
    "dj_artist_videos", "dj_artists",
    "dj_other_videos", "dj_other_channels",
    "dj_recent", "dj_cat_counts", "dj_meta",
    "ad_channels", "ad_stats",
    "wh_events",
]


def reset_pipeline_tables(con):
    """Drop all pipeline tables. User-edited tables (wl_artist_links etc.) are untouched."""
    for t in _PIPELINE_TABLES:
        con.execute(f"DROP TABLE IF EXISTS [{t}]")
    con.commit()
    print("Pipeline tables cleared (user data preserved).")


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
    -- wl_ tables  (source: watchlog.db — pipeline/curation database)
    -- ----------------------------------------------------------------

    -- One row per music video (music category only).
    -- wl_artist_name comes from watchlog.db videos.norm_name (channel-derived).
    CREATE TABLE IF NOT EXISTS wl_videos (
        wl_vid_id           INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_video_id         TEXT,           -- YouTube video ID
        wl_cleaned_title    TEXT,
        wl_title            TEXT,           -- raw title
        wl_channel_url      TEXT,
        wl_artist_name      TEXT,           -- norm_name from watchlog.db
        wl_feat_artist      TEXT,
        wl_play_count       INTEGER,
        wl_date_first       TEXT,
        wl_date_last        TEXT,
        wl_media_type       TEXT,
        mb_recording_id     TEXT,
        mb_confidence       INTEGER,
        mb_status           TEXT
    );

    -- One row per unique song, identified by (normalized cleaned_title, normalized artist).
    -- Canonical title/artist form is taken from the highest-played matching video.
    -- wl_match_basis: 'title+artist' when both present, 'title_only' when artist is blank.
    -- No MusicBrainz data yet — mb_ fields reserved for future matching.
    CREATE TABLE IF NOT EXISTS wl_songs (
        wl_song_id          INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_cleaned_title    TEXT,
        wl_artist_name      TEXT,
        wl_feat_artist      TEXT,
        wl_video_count      INTEGER DEFAULT 0,
        wl_match_basis      TEXT,
        mb_recording_id     TEXT,
        mb_song_name        TEXT,
        mb_artist_id        TEXT,
        mb_confidence       INTEGER,
        mb_status           TEXT,
        wl_notes            TEXT
    );

    -- Junction: one song → many videos.
    -- No UNIQUE constraint on (wl_song_id, wl_vid_id) so that later MusicBrainz
    -- matching can produce multiple candidate rows for ambiguous cases.
    -- wl_match_type: 'exact' (title+artist matched verbatim),
    --                'normalized' (matched after lowercasing/trimming).
    CREATE TABLE IF NOT EXISTS wl_song_video (
        wl_sv_id            INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_song_id          INTEGER REFERENCES wl_songs(wl_song_id),
        wl_vid_id           INTEGER REFERENCES wl_videos(wl_vid_id),
        wl_match_type       TEXT
    );

    -- ----------------------------------------------------------------
    -- wl_ user-edited tables  (NEVER dropped — survive pipeline rebuilds)
    -- ----------------------------------------------------------------

    -- Artist "See also" relationships.
    -- Uses dj_slug as the stable key (deterministic from artist name,
    -- survives DB rebuilds unlike auto-increment dj_artist_id).
    -- Relationship is directional; UI adds both directions when mutual.
    -- wl_label defaults to 'See also'; future values: 'Member of', 'Side project'.
    CREATE TABLE IF NOT EXISTS wl_artist_links (
        wl_al_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_from_slug    TEXT NOT NULL,
        wl_to_slug      TEXT NOT NULL,
        wl_label        TEXT NOT NULL DEFAULT 'See also',
        UNIQUE(wl_from_slug, wl_to_slug)
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
    """Populate wl_videos, wl_songs, and wl_song_video from watchlog.db.

    Matching strategy:
      - Group music videos by (LOWER(TRIM(cleaned_title)), LOWER(TRIM(norm_name))).
      - Each unique group becomes one wl_songs row.
      - Canonical title/artist form taken from the highest-played video in the group
        (source query is ordered by play_count DESC).
      - Same title + different artist → separate song records (covers / genuine duplicates).
      - Junction rows are inserted without a UNIQUE constraint so future MB matching
        can append additional candidate rows for ambiguous cases.
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

    # --- Pass 1: build song registry -----------------------------------------
    # song_key  → index into canonical_songs list (first-seen = highest play count)
    song_registry  = {}   # (title_key, artist_key) → canonical index
    canonical_songs = []  # list of dicts: {wl_cleaned_title, wl_artist_name, ...}

    # track per-video which song_key it belongs to (same order as `videos`)
    video_song_keys = []

    for v in videos:
        cleaned_title = (v["cleaned_title"] or "").strip()
        artist_name   = (v["norm_name"]      or "").strip()
        feat_artist   = (v["feat_artist"]    or "").strip()

        title_key  = cleaned_title.lower()
        artist_key = artist_name.lower()
        song_key   = (title_key, artist_key)

        if song_key not in song_registry:
            song_registry[song_key] = len(canonical_songs)
            canonical_songs.append({
                "wl_cleaned_title": cleaned_title,
                "wl_artist_name":   artist_name,
                "wl_feat_artist":   feat_artist or None,
                "wl_match_basis":   "title+artist" if artist_name else "title_only",
            })

        video_song_keys.append(song_key)

    # --- Pass 2: insert wl_songs ---------------------------------------------
    song_db_ids = {}  # song_key → wl_song_id
    for song_key, idx in song_registry.items():
        s = canonical_songs[idx]
        cur = con.execute(
            """INSERT INTO wl_songs
               (wl_cleaned_title, wl_artist_name, wl_feat_artist, wl_match_basis)
               VALUES (?, ?, ?, ?)""",
            (s["wl_cleaned_title"], s["wl_artist_name"],
             s["wl_feat_artist"],   s["wl_match_basis"]),
        )
        song_db_ids[song_key] = cur.lastrowid

    # --- Pass 3: insert wl_videos + collect junction rows --------------------
    junction_rows = []  # (wl_song_id, wl_vid_id, wl_match_type)

    for v, song_key in zip(videos, video_song_keys):
        vid_cur = con.execute(
            """INSERT INTO wl_videos
               (wl_video_id, wl_cleaned_title, wl_title, wl_channel_url,
                wl_artist_name, wl_feat_artist, wl_play_count,
                wl_date_first, wl_date_last, wl_media_type,
                mb_recording_id, mb_confidence, mb_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (v["video_id"], v["cleaned_title"], v["title"], v["channel_url"],
             v["norm_name"], v["feat_artist"], v["play_count"],
             v["date_first"], v["date_last"], v["media_type"],
             v["mb_recording_id"], v["mb_confidence"], v["mb_status"]),
        )
        wl_vid_id  = vid_cur.lastrowid
        wl_song_id = song_db_ids[song_key]

        # Determine match type: exact if the video's own values already match
        # the canonical form verbatim; normalized otherwise.
        canon = canonical_songs[song_registry[song_key]]
        if (v["cleaned_title"] or "").strip() == canon["wl_cleaned_title"] and \
           (v["norm_name"]      or "").strip() == canon["wl_artist_name"]:
            match_type = "exact"
        else:
            match_type = "normalized"

        junction_rows.append((wl_song_id, wl_vid_id, match_type))

    con.executemany(
        "INSERT INTO wl_song_video (wl_song_id, wl_vid_id, wl_match_type) VALUES (?,?,?)",
        junction_rows,
    )

    # --- Update wl_video_count on each song -----------------------------------
    con.execute("""
        UPDATE wl_songs
        SET    wl_video_count = (
            SELECT COUNT(*) FROM wl_song_video sv
            WHERE  sv.wl_song_id = wl_songs.wl_song_id
        )
    """)

    con.commit()
    print(f"  Inserted {len(song_db_ids):,} rows into wl_songs")
    print(f"  Inserted {len(videos):,} rows into wl_videos")
    print(f"  Inserted {len(junction_rows):,} rows into wl_song_video")


def main():
    con = sqlite3.connect(DB_PATH)
    try:
        reset_pipeline_tables(con)
        create_schema(con)
        load_watch_history(con)
        load_data_json(con)
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
