"""
build_demo_json.py
==================
Generates the GitHub Pages demo dataset.

Output files: data.demo.json and admin_data.demo.json
These do NOT overwrite the local data.json / admin_data.json.

To publish the demo to GitHub, run:
    python deploy_demo.py
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH         = os.path.join(os.path.dirname(__file__), "wl.db")
DATA_JSON_PATH  = os.path.join(os.path.dirname(__file__), "data.demo.json")
ADMIN_JSON_PATH = os.path.join(os.path.dirname(__file__), "admin_data.demo.json")

# Artists to include (slug values)
DEMO_ARTIST_SLUGS = {
    "ren",
    "the-big-push",
    "gorillaz",
    "renmakesstuff",
    "gz-23-gorillaz-live-archive",
    "whatsnextgorillaz",
    "talking-heads",
}

# Artist names as stored in wl_videos/wl_songs (used for song/video filtering)
DEMO_ARTIST_NAMES = {"Ren", "The Big Push", "Gorillaz", "RenMakesStuff",
                     "GZ 23 (Gorillaz Live Archive)", "whatsnextgorillaz",
                     "Talking Heads"}

# Artists whose AUDIO_ONLY records are excluded from the video list on the artist page
AUDIO_EXCLUDED_SLUGS = {"talking-heads"}

# Artist IDs for the above (used for video/song filtering)
DEMO_ARTIST_IDS = None  # resolved at runtime

MAX_ARTIST_VIDS = 100
MAX_RECENT      = 30


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


# Demo See Also links — added programmatically so the feature shows in the demo
DEMO_SEE_ALSO = [
    # (from_slug, to_slug, label)
    ("ren",           "the-big-push",  "See also"),
    ("the-big-push",  "ren",           "See also"),
    ("ren",           "renmakesstuff", "See also"),
    ("gorillaz",      "gz-23-gorillaz-live-archive", "See also"),
]


def get_demo_artist_ids(con, slugs):
    placeholders = ",".join("?" * len(slugs))
    rows = con.execute(
        f"SELECT dj_artist_id FROM dj_artists WHERE dj_slug IN ({placeholders})",
        list(slugs),
    ).fetchall()
    return {r[0] for r in rows}


def build_demo_data(con):
    global DEMO_ARTIST_IDS
    DEMO_ARTIST_IDS = get_demo_artist_ids(con, DEMO_ARTIST_SLUGS)

    # ── see-also (from hardcoded demo links) ────────────────────────────────
    see_also_by_slug = defaultdict(list)
    for from_slug, to_slug, label in DEMO_SEE_ALSO:
        row = con.execute(
            "SELECT dj_name FROM dj_artists WHERE dj_slug = ?", (to_slug,)
        ).fetchone()
        name = row[0] if row else to_slug
        see_also_by_slug[from_slug].append({"slug": to_slug, "name": name, "label": label})

    # ── artist videos ────────────────────────────────────────────────────────
    placeholders = ",".join("?" * len(DEMO_ARTIST_IDS))
    av_by_artist = defaultdict(list)
    for r in con.execute(f"""
        SELECT av.dj_artist_id, av.dj_title, av.dj_video_id, av.dj_date,
               a.dj_slug, wv.wl_content_type
        FROM   dj_artist_videos av
        JOIN   dj_artists a  ON a.dj_artist_id  = av.dj_artist_id
        LEFT JOIN wl_videos wv ON wv.wl_video_id = av.dj_video_id
        WHERE  av.dj_artist_id IN ({placeholders})
        ORDER  BY av.dj_date DESC
    """, list(DEMO_ARTIST_IDS)):
        aid, title, vid, date, artist_slug, content_type = r
        if artist_slug in AUDIO_EXCLUDED_SLUGS and content_type == "AUDIO_ONLY":
            continue
        av_by_artist[aid].append({"t": title, "id": vid or "", "ts": date})

    # ── artists ──────────────────────────────────────────────────────────────
    artists = []
    for r in con.execute(f"""
        SELECT dj_artist_id, dj_name, dj_slug, dj_plays, dj_latest, dj_channel_count
        FROM   dj_artists
        WHERE  dj_slug IN ({",".join("?" * len(DEMO_ARTIST_SLUGS))})
        ORDER  BY dj_plays DESC
    """, list(DEMO_ARTIST_SLUGS)):
        aid, name, sg, plays, latest, ch_count = r
        vids = av_by_artist.get(aid, [])[:MAX_ARTIST_VIDS]
        a = {
            "name":          name,
            "slug":          sg or slug(name),
            "plays":         plays or 0,
            "latest":        latest,
            "channel_count": ch_count or 1,
            "videos":        vids,
        }
        links = see_also_by_slug.get(sg or slug(name))
        if links:
            a["see_also"] = links
        artists.append(a)

    # ── songs (only for demo artists) ────────────────────────────────────────
    name_placeholders = ",".join("?" * len(DEMO_ARTIST_NAMES))
    songs = []
    for r in con.execute(f"""
        SELECT
            s.wl_song_id,
            COALESCE(s.mb_song_name, s.wl_cleaned_title)  AS title,
            s.wl_cleaned_title                             AS raw_title,
            s.wl_artist_name                               AS artist,
            s.wl_feat_artist                               AS feat,
            s.mb_recording_id                              AS mb_id,
            s.mb_confidence                                AS mb_conf,
            SUM(v.wl_play_count)                           AS plays,
            MAX(NULLIF(v.wl_date_last, ''))                AS latest,
            GROUP_CONCAT(v.wl_video_id)                    AS vids_csv,
            MAX(v.wl_media_type)                           AS mt
        FROM wl_songs s
        JOIN wl_song_video sv ON sv.wl_song_id = s.wl_song_id
        JOIN wl_videos v      ON v.wl_vid_id   = sv.wl_vid_id
        WHERE s.wl_artist_name IN ({name_placeholders})
        GROUP BY s.wl_song_id
        ORDER BY plays DESC
    """, list(DEMO_ARTIST_NAMES)):
        sid, title, raw_title, artist, feat, mb_id, mb_conf, plays, latest, vids_csv, mt = r
        vids = [v for v in (vids_csv or "").split(",") if v]
        song = {
            "sid":    sid,
            "title":  title,
            "artist": artist or "",
            "aslug":  slug(artist),
            "plays":  plays or 0,
            "vids":   vids,
        }
        if raw_title and raw_title != title: song["raw_title"] = raw_title
        if latest:  song["latest"]  = latest
        if feat:    song["feat"]    = feat
        if mt:      song["mt"]      = mt
        if mb_id:   song["mb_id"]   = mb_id
        if mb_conf: song["mb_conf"] = mb_conf
        songs.append(song)

    # ── recent (curated static list for demo) ────────────────────────────────
    # Hand-picked top songs with confirmed video IDs, ordered for a good demo.
    recent = [
        {"t": "Ren - Hi Ren",                      "id": "mnbXfRACsVM", "ch": "Ren",          "ts": "2026-03-08", "cat": "Music", "url": ""},
        {"t": "Ren - What You Want",                "id": "jrjp4Du0rEc", "ch": "Ren",          "ts": "2026-03-08", "cat": "Music", "url": ""},
        {"t": "Gorillaz - Feel Good Inc.",          "id": "HyHNuVaZJ-k", "ch": "Gorillaz",     "ts": "2026-03-08", "cat": "Music", "url": ""},
        {"t": "Ren - Murderer",                     "id": "hscHqw7CIFo", "ch": "Ren",          "ts": "2026-03-07", "cat": "Music", "url": ""},
        {"t": "The Big Push - It's Alright",        "id": "CCKf6O7asss", "ch": "The Big Push", "ts": "2026-03-06", "cat": "Music", "url": ""},
        {"t": "Gorillaz - Clint Eastwood",          "id": "1V_xRb0x9aw", "ch": "Gorillaz",     "ts": "2026-03-06", "cat": "Music", "url": ""},
        {"t": "Ren - The Hunger",                   "id": "1T_fLytBFM4", "ch": "Ren",          "ts": "2026-03-05", "cat": "Music", "url": ""},
        {"t": "Ren - Illest Of Our Time",           "id": "tB-JGSdBerE", "ch": "Ren",          "ts": "2026-03-04", "cat": "Music", "url": ""},
        {"t": "The Big Push - Sympathy For The Devil", "id": "CR5FyWeuS90", "ch": "The Big Push", "ts": "2026-03-03", "cat": "Music", "url": ""},
        {"t": "Gorillaz - DARE",                    "id": "uAOR6ib95kQ", "ch": "Gorillaz",     "ts": "2026-03-02", "cat": "Music", "url": ""},
        {"t": "Ren - Animal Flow",                  "id": "F4mUnmFbVNg", "ch": "Ren",          "ts": "2026-03-01", "cat": "Music", "url": ""},
        {"t": "Gorillaz - Stylo",                   "id": "nhPaWIeULKk", "ch": "Gorillaz",     "ts": "2026-02-28", "cat": "Music", "url": ""},
        {"t": "Ren - Money Game Part 2",            "id": "jJmV1A4O1eM", "ch": "Ren",          "ts": "2026-02-27", "cat": "Music", "url": ""},
        {"t": "The Big Push - Why My Woman?",       "id": "BsZrM4nruII", "ch": "The Big Push", "ts": "2026-02-26", "cat": "Music", "url": ""},
        {"t": "Gorillaz - 19-2000",                 "id": "WXR-bCF5dbM", "ch": "Gorillaz",     "ts": "2026-02-25", "cat": "Music", "url": ""},
        {"t": "Ren - Dominoes",                     "id": "bbbjWEnC3Gc", "ch": "Ren",          "ts": "2026-02-24", "cat": "Music", "url": ""},
        {"t": "The Big Push - Girls Just Want To Have Fun", "id": "OqEHMinvxMk", "ch": "The Big Push", "ts": "2026-02-23", "cat": "Music", "url": ""},
        {"t": "Ren - Penitence",                    "id": "R-7UHDoKlMw", "ch": "Ren",          "ts": "2026-02-22", "cat": "Music", "url": ""},
        {"t": "Talking Heads - Psycho Killer",      "id": "CJ54eImz88w", "ch": "Talking Heads", "ts": "2026-02-21", "cat": "Music", "url": ""},
        {"t": "Talking Heads - Burning Down the House", "id": "_3eC35LoF4U", "ch": "Talking Heads", "ts": "2026-02-20", "cat": "Music", "url": ""},
        {"t": "Talking Heads - Once in a Lifetime", "id": "5IsSpAOD6K8", "ch": "Talking Heads", "ts": "2026-02-19", "cat": "Music", "url": ""},
        {"t": "Talking Heads - Road to Nowhere",    "id": "LQiOA7euaYA", "ch": "Talking Heads", "ts": "2026-02-18", "cat": "Music", "url": ""},
    ]

    # ── channels (demo artists as music channels) ────────────────────────────
    channels = [
        {
            "name":   a["name"],
            "slug":   a["slug"],
            "cat":    "music",
            "plays":  a["plays"],
            "videos": a["videos"][:10],
        }
        for a in artists
    ]

    # ── cat_counts and total ─────────────────────────────────────────────────
    total_plays = sum(a["plays"] for a in artists)
    cat_counts = {"Music": total_plays}

    return {
        "generated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total":      total_plays,
        "cat_counts": cat_counts,
        "recent":     recent,
        "artists":    artists,
        "channels":   channels,
        "songs":      songs,
    }


def build_demo_admin(con):
    demo_artist_count = len(DEMO_ARTIST_SLUGS)
    np = ",".join("?" * len(DEMO_ARTIST_NAMES))
    song_count = con.execute(f"""
        SELECT COUNT(DISTINCT s.wl_song_id)
        FROM wl_songs s
        WHERE s.wl_artist_name IN ({np})
    """, list(DEMO_ARTIST_NAMES)).fetchone()[0]

    video_count = con.execute(f"""
        SELECT COUNT(*) FROM wl_videos
        WHERE wl_artist_name IN ({np})
    """, list(DEMO_ARTIST_NAMES)).fetchone()[0]

    stats = {
        "channels_total": demo_artist_count,
        "channels_music": demo_artist_count,
        "videos_total":   video_count,
        "videos_music":   video_count,
        "songs_total":    song_count,
        "songs_mb":       0,
        "channels_mb":    2,  # Gorillaz channels are MB-accepted
    }

    placeholders = ",".join("?" * len(DEMO_ARTIST_SLUGS))
    channels = []
    for r in con.execute(f"""
        SELECT ad.ad_url, ad.ad_name, ad.ad_plays, ad.ad_mb_status,
               ad.ad_mb_name, ad.ad_mb_confidence, ad.ad_music_videos, ad.ad_pending_videos
        FROM   ad_channels ad
        JOIN   dj_artists dj ON dj.dj_name = ad.ad_name
        WHERE  dj.dj_slug IN ({placeholders})
        ORDER  BY ad.ad_plays DESC
    """, list(DEMO_ARTIST_SLUGS)):
        url, name, plays, mb_status, mb_name, mb_conf, music_vids, pending = r
        channels.append({
            "url":            url,
            "name":           name,
            "plays":          plays or 0,
            "mb_status":      mb_status or "pending",
            "mb_name":        mb_name,
            "mb_confidence":  mb_conf,
            "music_videos":   music_vids or 0,
            "pending_videos": pending or 0,
        })

    return {"stats": stats, "channels": channels}


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found — run build_wl_db.py first")
        return

    con = sqlite3.connect(DB_PATH)
    try:
        print("Building data.demo.json ...")
        data = build_demo_data(con)
        with open(DATA_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        sz = os.path.getsize(DATA_JSON_PATH) // 1024
        print(f"  Wrote {DATA_JSON_PATH} ({sz} KB)")
        print(f"    total plays:  {data['total']:,}")
        print(f"    artists:      {len(data['artists'])}")
        print(f"    songs:        {len(data['songs'])}")
        print(f"    recent:       {len(data['recent'])}")

        print()
        print("Building admin_data.demo.json ...")
        admin = build_demo_admin(con)
        with open(ADMIN_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(admin, f, ensure_ascii=False, separators=(",", ":"))
        sz = os.path.getsize(ADMIN_JSON_PATH) // 1024
        s = admin["stats"]
        print(f"  Wrote {ADMIN_JSON_PATH} ({sz} KB)")
        print(f"    channels: {s['channels_total']}, videos: {s['videos_music']}, songs: {s['songs_total']}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
