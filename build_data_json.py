"""
build_data_json.py
==================
Reads preprocess.py output files and produces data.json for the web site.
Optionally joins MusicBrainz enrichment from watchlog.db.

Usage:
  python build_data_json.py --channels name_file.txt --videos name_title_file.txt
  python build_data_json.py --channels name_file.txt --videos name_title_file.txt --db watchlog.db
  python build_data_json.py --channels name_file.txt --videos name_title_file.txt --out data.json
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

DELIMITER      = "|"
RECENT_COUNT   = 150
MAX_VIDS_MUSIC = 500   # videos per artist (keeps JSON manageable)
MAX_VIDS_OTHER = 100   # videos per non-music channel


# ===========================================================================
# HELPERS
# ===========================================================================

def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower()).strip('-')

def read_pipe_file(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    if not lines:
        return rows
    headers = [h.strip() for h in lines[0].split(DELIMITER)]
    for line in lines[1:]:
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split(DELIMITER)
        while len(parts) < len(headers):
            parts.append('')
        rows.append({headers[i]: parts[i] for i in range(len(headers))})
    return rows


# ===========================================================================
# MUSICBRAINZ ENRICHMENT LOADER
# ===========================================================================

def load_mb_data(db_path):
    """
    Pull MB enrichment from watchlog.db.
    Returns (ch_mb, vid_mb) dicts keyed by channel_url and video_id.
    Returns ({}, {}) if db not found.
    """
    if not db_path or not os.path.exists(db_path):
        return {}, {}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    ch_mb = {}
    for r in conn.execute(
        "SELECT * FROM channels WHERE mb_status IN ('accepted','review')"
    ):
        ch_mb[r['channel_url']] = dict(r)

    vid_mb = {}
    for r in conn.execute(
        "SELECT * FROM videos WHERE mb_status IN ('accepted','review')"
    ):
        vid_id = r['video_id']
        if vid_id:
            vid_mb[vid_id] = dict(r)

    conn.close()
    print(f"  [db] Loaded {len(ch_mb)} channel MB records, {len(vid_mb)} video MB records from {db_path}")
    return ch_mb, vid_mb


# ===========================================================================
# BUILD
# ===========================================================================

def build(ch_rows, vid_rows, ch_mb, vid_mb):
    # ── Channel index ────────────────────────────────────────────────────
    channels = {}
    for r in ch_rows:
        url = r.get('channel_url', '').strip() or f"__name__{r['raw_name']}"
        mb  = ch_mb.get(url, {})
        channels[url] = {
            'norm_name':   r.get('norm_name', ''),
            'raw_name':    r.get('raw_name', ''),
            'channel_url': url,
            'category':    r.get('category', 'unsure'),
            'total_plays': int(r.get('total_plays', 0) or 0),
            'title_count': int(r.get('title_count', 0) or 0),
            'date_first':  r.get('date_first', ''),
            'date_last':   r.get('date_last', ''),
            # MB artist fields
            'mb_id':       mb.get('mb_artist_id'),
            'mb_name':     mb.get('mb_artist_name'),
            'mb_country':  mb.get('mb_country'),
            'mb_type':     mb.get('mb_type'),
            'mb_begin':    mb.get('mb_begin_date'),
            'mb_end':      mb.get('mb_end_date'),
            'mb_disambig': mb.get('mb_disambiguation'),
            'mb_tags':     json.loads(mb.get('mb_tags') or '[]'),
            'mb_conf':     mb.get('mb_confidence'),
        }

    # ── Video catalog ────────────────────────────────────────────────────
    # Enrich each video row with MB data if available
    enriched_vids = []
    for r in vid_rows:
        url = r.get('channel_url', '').strip() or f"__name__{r['raw_name']}"
        vid_id = r.get('video_id', '').strip()
        mb = vid_mb.get(vid_id, {})
        enriched_vids.append({
            'video_id':       vid_id or None,
            'norm_name':      r.get('norm_name', ''),
            'raw_name':       r.get('raw_name', ''),
            'channel_url':    url,
            'category':       r.get('category', 'unsure'),
            'title':          r.get('title', ''),
            'title_url':      r.get('title_url', ''),
            'date_first':     r.get('date_first', ''),
            'date_last':      r.get('date_last', ''),
            'play_count':     int(r.get('play_count', 0) or 0),
            # Cleaned / derived (from watchlog.db if available)
            'cleaned_title':  mb.get('cleaned_title') or r.get('title', ''),
            'feat_artist':    mb.get('feat_artist') or '',
            'media_type':     mb.get('media_type') or '',
            # MB recording fields
            'mb_recording_id':  mb.get('mb_recording_id'),
            'mb_song_name':     mb.get('mb_song_name'),
            'mb_artist_credit': mb.get('mb_artist_credit'),
            'mb_release_title': mb.get('mb_release_title'),
            'mb_release_date':  mb.get('mb_release_date'),
            'mb_release_type':  mb.get('mb_release_type'),
            'mb_isrc':          mb.get('mb_isrc'),
            'mb_duration_ms':   mb.get('mb_duration_ms'),
            'mb_confidence':    mb.get('mb_confidence'),
        })

    # Group by channel
    chan_vids = defaultdict(list)
    for v in enriched_vids:
        chan_vids[v['channel_url']].append(v)

    for url in chan_vids:
        chan_vids[url].sort(key=lambda v: v['date_last'] or '', reverse=True)

    # ── Compact video object for JSON ─────────────────────────────────────
    def compact_vid(v, include_cat=False):
        cv = {'t': v['title'], 'id': v['video_id'] or '', 'ts': v['date_last']}
        if include_cat and v['category']:   cv['cat'] = v['category']
        if v.get('media_type'):             cv['mt']  = v['media_type']
        if v.get('mb_song_name'):           cv['ms']  = v['mb_song_name']
        if v.get('mb_isrc'):                cv['isrc']= v['mb_isrc']
        if v.get('feat_artist'):            cv['feat']= v['feat_artist']
        if v.get('mb_release_date'):        cv['rd']  = v['mb_release_date']
        if v.get('mb_release_type'):        cv['rt']  = v['mb_release_type']
        return cv

    # ── Artists array (music channels) ───────────────────────────────────
    artists = []
    for url, ch in channels.items():
        if ch['category'] != 'music':
            continue
        vids = chan_vids.get(url, [])
        a = {
            'name':          ch['norm_name'],
            'slug':          slug(ch['norm_name']),
            'plays':         ch['total_plays'],
            'latest':        ch['date_last'],
            'channel_count': 1,
            'curl':          url,
            'videos':        [compact_vid(v) for v in vids[:MAX_VIDS_MUSIC]],
        }
        if ch.get('mb_id'):
            a['mb_id']      = ch['mb_id']
            a['mb_country'] = ch['mb_country']
            a['mb_type']    = ch['mb_type']
            a['mb_begin']   = ch['mb_begin']
            a['mb_end']     = ch['mb_end']
            a['mb_disambig']= ch['mb_disambig']
            a['mb_tags']    = ch['mb_tags']
            a['mb_conf']    = ch['mb_conf']
        artists.append(a)

    artists.sort(key=lambda a: -(a['plays'] or 0))

    # ── Other channels array ─────────────────────────────────────────────
    other_channels = []
    for url, ch in channels.items():
        if ch['category'] == 'music':
            continue
        vids = chan_vids.get(url, [])
        c = {
            'name':   ch['norm_name'],
            'cat':    ch['category'],
            'curl':   url,
            'slug':   slug(ch['norm_name']),
            'plays':  ch['total_plays'],
            'latest': ch['date_last'],
            'videos': [compact_vid(v, include_cat=True) for v in vids[:MAX_VIDS_OTHER]],
        }
        if ch.get('mb_id'):
            c['mb_id']      = ch['mb_id']
            c['mb_country'] = ch['mb_country']
            c['mb_type']    = ch['mb_type']
            c['mb_conf']    = ch['mb_conf']
        other_channels.append(c)

    other_channels.sort(key=lambda c: -(c['plays'] or 0))

    # ── Songs array (deduplicated music videos) ───────────────────────────
    songs_map = {}   # key → song dict
    for url, vids in chan_vids.items():
        ch = channels.get(url, {})
        if ch.get('category') != 'music':
            continue
        for v in vids:
            key = (v.get('mb_recording_id')
                   or f"{v['norm_name']}|||{(v.get('cleaned_title') or v['title']).lower().strip()}")
            if key not in songs_map:
                songs_map[key] = {
                    'sid':       key[:80],
                    'title':     v.get('mb_song_name') or v.get('cleaned_title') or v['title'],
                    'raw_title': v['title'],
                    'artist':    v['norm_name'],
                    'aslug':     slug(v['norm_name']),
                    'feat':      v.get('feat_artist') or '',
                    'isrc':      v.get('mb_isrc'),
                    'rel_date':  v.get('mb_release_date'),
                    'rel_title': v.get('mb_release_title'),
                    'rel_type':  v.get('mb_release_type'),
                    'dur_ms':    v.get('mb_duration_ms'),
                    'mt':        v.get('media_type') or '',
                    'mb_id':     v.get('mb_recording_id'),
                    'mb_conf':   v.get('mb_confidence'),
                    'plays':     v['play_count'],
                    'latest':    v['date_last'],
                    'vids':      [v['video_id']] if v.get('video_id') else [],
                }
            else:
                s = songs_map[key]
                s['plays'] += v['play_count']
                if (v['date_last'] or '') > (s['latest'] or ''):
                    s['latest'] = v['date_last']
                if v.get('video_id') and v['video_id'] not in s['vids']:
                    s['vids'].append(v['video_id'])

    songs = sorted(songs_map.values(), key=lambda s: -(s['plays'] or 0))

    # ── Recent array ─────────────────────────────────────────────────────
    all_recent = []
    for url, vids in chan_vids.items():
        ch = channels.get(url, {})
        for v in vids:
            item = {
                't':   v['title'],
                'id':  v['video_id'] or '',
                'ch':  v['norm_name'],
                'ts':  v['date_last'],
                'cat': v['category'],
                'url': v['title_url'],
            }
            if v.get('media_type'):   item['mt'] = v['media_type']
            if v.get('mb_song_name'): item['ms'] = v['mb_song_name']
            all_recent.append(item)

    all_recent.sort(key=lambda v: v['ts'] or '', reverse=True)
    recent = all_recent[:RECENT_COUNT]

    # ── Category counts ───────────────────────────────────────────────────
    cat_counts = defaultdict(int)
    for v in enriched_vids:
        cat_counts[v['category']] += v['play_count']

    return {
        'generated':     datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'total':         sum(cat_counts.values()),
        'cat_counts':    dict(cat_counts),
        'recent':        recent,
        'artists':       artists,
        'other_channels': other_channels,
        'songs':         songs,
    }


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description='Build data.json from preprocess.py output')
    parser.add_argument('--channels', required=True, metavar='NAME_FILE',
                        help='Path to name_file.txt')
    parser.add_argument('--videos', required=True, metavar='VIDEO_FILE',
                        help='Path to name_title_file.txt')
    parser.add_argument('--db', default='watchlog.db', metavar='DB',
                        help='Path to watchlog.db for MB enrichment (optional)')
    parser.add_argument('--out', default='data.json',
                        help='Output path (default: data.json)')
    args = parser.parse_args()

    for p in (args.channels, args.videos):
        if not os.path.exists(p):
            print(f'ERROR: file not found: {p}')
            sys.exit(1)

    print('Loading channels...')
    ch_rows = read_pipe_file(args.channels)
    print(f'  {len(ch_rows)} channels')

    print('Loading videos...')
    vid_rows = read_pipe_file(args.videos)
    print(f'  {len(vid_rows)} videos')

    print('Loading MB enrichment...')
    ch_mb, vid_mb = load_mb_data(args.db)

    print('Building data...')
    out = build(ch_rows, vid_rows, ch_mb, vid_mb)

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

    size_kb = os.path.getsize(args.out) // 1024
    print(f'\nWrote {args.out} ({size_kb} KB)')
    print(f'  total:    {out["total"]:,}')
    print(f'  artists:  {len(out["artists"]):,}')
    print(f'  channels: {len(out["other_channels"]):,}')
    print(f'  songs:    {len(out["songs"]):,}')
    print(f'  recent:   {len(out["recent"])}')
    cats = out['cat_counts']
    for cat in sorted(cats, key=lambda c: -cats[c]):
        print(f'    {cat:<14} {cats[cat]:>7,}')


if __name__ == '__main__':
    main()
