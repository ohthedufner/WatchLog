"""
build_demo_json.py
==================
Generates demo data.json and admin_data.json for GitHub Pages demonstration.

Includes only: Ren, The Big Push, Gorillaz, and their related channels.
Adds curated See Also links so the feature is visible in the demo.
Sanitizes recent list to only include videos from demo artists.

Run from the project root:
    python build_demo_json.py
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from collections import defaultdict

DB_PATH         = os.path.join(os.path.dirname(__file__), "wl.db")
DATA_JSON_PATH  = os.path.join(os.path.dirname(__file__), "data.json")
ADMIN_JSON_PATH = os.path.join(os.path.dirname(__file__), "admin_data.json")

# Artists to include (slug values)
DEMO_ARTIST_SLUGS = {
    "ren",
    "the-big-push",
    "gorillaz",
    "renmakesstuff",
    "gz-23-gorillaz-live-archive",
    "whatsnextgorillaz",
}

# Artist names as stored in wl_videos/wl_songs (used for song/video filtering)
DEMO_ARTIST_NAMES = {"Ren", "The Big Push", "Gorillaz", "RenMakesStuff",
                     "GZ 23 (Gorillaz Live Archive)", "whatsnextgorillaz"}

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
        SELECT dj_artist_id, dj_title, dj_video_id, dj_date
        FROM   dj_artist_videos
        WHERE  dj_artist_id IN ({placeholders})
        ORDER  BY dj_date DESC
    """, list(DEMO_ARTIST_IDS)):
        av_by_artist[r[0]].append({"t": r[1], "id": r[2] or "", "ts": r[3]})

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

    # ── recent (filter to demo artists only) ─────────────────────────────────
    recent = []
    demo_names_lower = set()
    for r in con.execute(f"""
        SELECT dj_name FROM dj_artists
        WHERE dj_slug IN ({",".join("?" * len(DEMO_ARTIST_SLUGS))})
    """, list(DEMO_ARTIST_SLUGS)):
        demo_names_lower.add(r[0].lower())

    for r in con.execute("""
        SELECT dj_title, dj_video_id, dj_channel, dj_date, dj_category, dj_url
        FROM   dj_recent
        ORDER  BY dj_date DESC
    """):
        if r[2].lower() in demo_names_lower:
            recent.append({
                "t":   r[0],
                "id":  r[1] or "",
                "ch":  r[2],
                "ts":  r[3],
                "cat": r[4],
                "url": r[5],
            })
            if len(recent) >= MAX_RECENT:
                break

    # ── cat_counts and total ─────────────────────────────────────────────────
    total_plays = sum(a["plays"] for a in artists)
    cat_counts = {"Music": total_plays}

    return {
        "generated":      datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total":          total_plays,
        "cat_counts":     cat_counts,
        "recent":         recent,
        "artists":        artists,
        "other_channels": [],
        "songs":          songs,
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
        print("Building demo data.json ...")
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
        print("Building demo admin_data.json ...")
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
