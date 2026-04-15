"""
build_data_json.py
==================
Generates data.json and admin_data.json from wl.db.

Sources (all from wl.db):
  dj_*  →  artists, other_channels, recent, cat_counts, total
  wl_*  →  songs  (wl_songs + wl_videos via wl_song_video)
  ad_*  →  admin_data.json (stats, channel list)

No longer reads flat pipe files or watchlog.db directly.
Run build_wl_db.py first to ensure wl.db is current.
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

MAX_ARTIST_VIDS  = 500   # videos kept per artist in JSON
MAX_CHAN_VIDS    = 100   # videos kept per non-music channel in JSON
MAX_MUSIC_CH_VIDS = 20  # videos kept per music channel in JSON


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')


# ============================================================
# data.json
# ============================================================

def build_data(con):
    # ── category counts & total ──────────────────────────────
    cat_counts = {}
    for row in con.execute("SELECT dj_category, dj_count FROM dj_cat_counts"):
        cat_counts[row[0]] = row[1]
    total = sum(cat_counts.values())

    # ── recent ───────────────────────────────────────────────
    recent = []
    for r in con.execute("""
        SELECT dj_title, dj_video_id, dj_channel, dj_date, dj_category, dj_url
        FROM   dj_recent
        ORDER  BY dj_date DESC
    """):
        item = {
            't':   r[0],
            'id':  r[1] or '',
            'ch':  r[2],
            'ts':  r[3],
            'cat': r[4],
            'url': r[5],
        }
        recent.append(item)

    # ── see-also links index (from_slug → [{slug, name, label}]) ────
    see_also_by_slug = defaultdict(list)
    for r in con.execute("""
        SELECT al.wl_from_slug, al.wl_to_slug, al.wl_label, a.dj_name
        FROM   wl_artist_links al
        JOIN   dj_artists a ON a.dj_slug = al.wl_to_slug
        ORDER  BY a.dj_plays DESC
    """):
        see_also_by_slug[r[0]].append({
            'slug':  r[1],
            'name':  r[2],
            'label': r[3],
        })

    # ── artist videos index (artist_id → [compact vids]) ─────
    av_by_artist = defaultdict(list)
    for r in con.execute("""
        SELECT dj_artist_id, dj_title, dj_video_id, dj_date
        FROM   dj_artist_videos
        ORDER  BY dj_date DESC
    """):
        av_by_artist[r[0]].append({'t': r[1], 'id': r[2] or '', 'ts': r[3]})

    # ── artists ──────────────────────────────────────────────
    artists = []
    for r in con.execute("""
        SELECT dj_artist_id, dj_name, dj_slug, dj_plays, dj_latest, dj_channel_count
        FROM   dj_artists
        ORDER  BY dj_plays DESC
    """):
        aid, name, sg, plays, latest, ch_count = r
        vids = av_by_artist.get(aid, [])[:MAX_ARTIST_VIDS]
        a = {
            'name':          name,
            'slug':          sg or slug(name),
            'plays':         plays or 0,
            'latest':        latest,
            'channel_count': ch_count or 1,
            'videos':        vids,
        }
        links = see_also_by_slug.get(sg or slug(name))
        if links:
            a['see_also'] = links
        artists.append(a)

    # ── other-channel videos index (oc_id → [compact vids]) ──
    ov_by_chan = defaultdict(list)
    for r in con.execute("""
        SELECT dj_oc_id, dj_title, dj_video_id, dj_date, dj_category
        FROM   dj_other_videos
        ORDER  BY dj_date DESC
    """):
        ov_by_chan[r[0]].append({
            't':   r[1],
            'id':  r[2] or '',
            'ts':  r[3],
            'cat': r[4],
        })

    # ── music channels (from ad_channels + wl_videos) ───────
    mv_by_url = defaultdict(list)
    for r in con.execute("""
        SELECT wl_channel_url, wl_title, wl_video_id, wl_date_last
        FROM   wl_videos
        WHERE  wl_channel_url IS NOT NULL
        ORDER  BY wl_date_last DESC NULLS LAST
    """):
        url, title, vid_id, date = r
        if len(mv_by_url[url]) < MAX_MUSIC_CH_VIDS:
            mv_by_url[url].append({
                't':  title or '[Unavailable]',
                'id': vid_id or '',
                'ts': date,
            })

    channels = []
    for r in con.execute("""
        SELECT ad_url, ad_name, ad_plays, ad_mb_name, ad_mb_confidence, ad_music_videos
        FROM   ad_channels
        ORDER  BY ad_plays DESC
    """):
        url, name, plays, mb_name, mb_conf, music_vids = r
        vids = mv_by_url.get(url, [])
        latest = next((v['ts'] for v in vids if v['ts']), None)
        ch = {
            'name':         name,
            'slug':         slug(name),
            'url':          url,
            'plays':        plays or 0,
            'music_videos': music_vids or 0,
            'videos':       vids,
        }
        if latest:   ch['latest']   = latest
        if mb_name:  ch['mb_name']  = mb_name
        if mb_conf:  ch['mb_conf']  = mb_conf
        channels.append(ch)

    # ── other channels ───────────────────────────────────────
    other_channels = []
    for r in con.execute("""
        SELECT dj_oc_id, dj_name, dj_category, dj_channel_url, dj_slug, dj_plays, dj_latest
        FROM   dj_other_channels
        ORDER  BY dj_plays DESC
    """):
        oc_id, name, cat, curl, sg, plays, latest = r
        vids = ov_by_chan.get(oc_id, [])[:MAX_CHAN_VIDS]
        other_channels.append({
            'name':   name,
            'cat':    cat,
            'curl':   curl,
            'slug':   sg or slug(name),
            'plays':  plays or 0,
            'latest': latest,
            'videos': vids,
        })

    # ── songs (from wl_songs + wl_videos via wl_song_video) ──
    songs = []
    for r in con.execute("""
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
        GROUP BY s.wl_song_id
        ORDER BY plays DESC
    """):
        sid, title, raw_title, artist, feat, mb_id, mb_conf, plays, latest, vids_csv, mt = r
        vids = [v for v in (vids_csv or '').split(',') if v]
        song = {
            'sid':   sid,
            'title': title,
            'artist': artist or '',
            'aslug':  slug(artist),
            'plays':  plays or 0,
            'vids':   vids,
        }
        if raw_title and raw_title != title: song['raw_title'] = raw_title
        if latest:  song['latest']  = latest
        if feat:    song['feat']    = feat
        if mt:      song['mt']      = mt
        if mb_id:   song['mb_id']   = mb_id
        if mb_conf: song['mb_conf'] = mb_conf
        songs.append(song)

    return {
        'generated':      datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'total':          total,
        'cat_counts':     cat_counts,
        'recent':         recent,
        'artists':        artists,
        'channels':       channels,
        'other_channels': other_channels,
        'songs':          songs,
    }


# ============================================================
# admin_data.json
# ============================================================

def build_admin(con):
    # Compute stats directly from wl.db — no circular ad_stats dependency.
    channels_music = con.execute("SELECT COUNT(*) FROM ad_channels").fetchone()[0]
    videos_music   = con.execute("SELECT COUNT(*) FROM wl_videos").fetchone()[0]
    videos_total   = con.execute("SELECT SUM(dj_count) FROM dj_cat_counts").fetchone()[0] or 0
    songs_total    = con.execute("SELECT COUNT(*) FROM wl_songs").fetchone()[0]
    songs_mb       = con.execute(
        "SELECT COUNT(*) FROM wl_songs WHERE mb_recording_id IS NOT NULL"
    ).fetchone()[0]
    channels_mb    = con.execute(
        "SELECT COUNT(*) FROM ad_channels WHERE ad_mb_status = 'accepted'"
    ).fetchone()[0]
    # channels_total = all channels in watch history (music + non-music)
    channels_total = (
        con.execute("SELECT COUNT(*) FROM ad_channels").fetchone()[0] +
        con.execute("SELECT COUNT(*) FROM dj_other_channels").fetchone()[0]
    )

    stats = {
        'channels_total': channels_total,
        'channels_music': channels_music,
        'videos_total':   videos_total,
        'videos_music':   videos_music,
        'songs_total':    songs_total,
        'songs_mb':       songs_mb,
        'channels_mb':    channels_mb,
    }

    channels = []
    for r in con.execute("""
        SELECT ad_url, ad_name, ad_plays, ad_mb_status,
               ad_mb_name, ad_mb_confidence, ad_music_videos, ad_pending_videos
        FROM   ad_channels
        ORDER  BY ad_plays DESC
    """):
        url, name, plays, mb_status, mb_name, mb_conf, music_vids, pending = r
        channels.append({
            'url':            url,
            'name':           name,
            'plays':          plays or 0,
            'mb_status':      mb_status or 'pending',
            'mb_name':        mb_name,
            'mb_confidence':  mb_conf,
            'music_videos':   music_vids or 0,
            'pending_videos': pending or 0,
        })

    return {'stats': stats, 'channels': channels}


# ============================================================
# main
# ============================================================

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found — run build_wl_db.py first")
        return

    con = sqlite3.connect(DB_PATH)
    try:
        print("Building data.json from wl.db ...")
        data = build_data(con)
        with open(DATA_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        sz = os.path.getsize(DATA_JSON_PATH) // 1024
        print(f"  Wrote {DATA_JSON_PATH} ({sz} KB)")
        print(f"    total:          {data['total']:,}")
        print(f"    artists:        {len(data['artists']):,}")
        print(f"    channels:       {len(data['channels']):,}")
        print(f"    other_channels: {len(data['other_channels']):,}")
        print(f"    songs:          {len(data['songs']):,}")
        print(f"    recent:         {len(data['recent']):,}")

        print()
        print("Building admin_data.json from wl.db ...")
        admin = build_admin(con)
        with open(ADMIN_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(admin, f, ensure_ascii=False, separators=(',', ':'))
        sz = os.path.getsize(ADMIN_JSON_PATH) // 1024
        s = admin['stats']
        print(f"  Wrote {ADMIN_JSON_PATH} ({sz} KB)")
        print(f"    channels:  {s['channels_total']:,} total / {s['channels_music']:,} music")
        print(f"    videos:    {s['videos_total']:,} total / {s['videos_music']:,} music")
        print(f"    songs:     {s['songs_total']:,} total / {s['songs_mb']:,} with MB ID")
        print(f"    channels_mb: {s['channels_mb']:,}")
        print(f"    channels in list: {len(admin['channels']):,}")
    finally:
        con.close()


if __name__ == '__main__':
    main()
