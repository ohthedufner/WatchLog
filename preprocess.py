"""
preprocess.py
=============
Dufner's YouTube History Preprocessor
Parses Google Takeout watch-history JSON and produces:
  - name_file.txt          (channel/artist index)
  - name_title_file.txt    (video catalog)
  - dataset_info.txt       (run manifest / statistics)
  - category_review.txt    (unsure channels for manual tagging)

Usage:
  python3 preprocess.py <input.json> [--out ./output] [--append existing_name_file.txt]

Delimiter: pipe  |
On subsequent runs, pass --append to merge with a previous name_file.txt
so that date_first_played and total_plays are preserved and extended.
"""

import json
import re
import os
import sys
import argparse
from datetime import datetime, timezone
from collections import defaultdict


# ===========================================================================
# CONFIGURATION
# ===========================================================================

DELIMITER = "|"
_RULES_FILE = os.path.join(os.path.dirname(__file__), "cleaning_rules.yaml")


def _safe(s: str) -> str:
    """Replace pipe and newline characters in field values so they don't break the delimiter or line structure."""
    if not s:
        return s
    return s.replace('|', ' - ').replace(chr(10), ' ').replace(chr(13), '')


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] in ('"', "'") and s[-1] == s[0]:
        return s[1:-1]
    return s


def _load_channel_name_suffixes(path):
    """Load channel_name_suffixes list from cleaning_rules.yaml."""
    suffixes = []
    in_section = False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.rstrip()
                stripped = line.lstrip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line[0].isspace():
                    in_section = (line.rstrip(": \t") == "channel_name_suffixes")
                elif in_section and stripped.startswith("- "):
                    suffixes.append(_unquote(stripped[2:]))
    except FileNotFoundError:
        pass
    return suffixes or [" - Topic", "VEVO"]


_CHANNEL_NAME_SUFFIXES = _load_channel_name_suffixes(_RULES_FILE)

# Title prefixes to strip (case-insensitive)
TITLE_PREFIX_RE = re.compile(r'^watched\s+this\s+|^watched\s+', re.IGNORECASE)

# Channel name normalization: built from cleaning_rules.yaml channel_name_suffixes
_suffix_pattern = "|".join(
    r'\s*' + re.escape(s.lstrip()) if s.startswith(" ") else re.escape(s)
    for s in _CHANNEL_NAME_SUFFIXES
)
NORMALIZE_SUFFIXES = re.compile(f'(?:{_suffix_pattern})$', re.IGNORECASE)

# ---------------------------------------------------------------------------
# CATEGORIZATION RULES
# ---------------------------------------------------------------------------
# Each rule is checked in order. First match wins.
# Category values: music | tv | tech | news | unsure

MUSIC_CHANNEL_SUFFIXES = tuple(_CHANNEL_NAME_SUFFIXES)

MUSIC_TITLE_KEYWORDS = [
    'official music video', 'official audio', 'official video',
    'music video', 'lyric video', 'lyrics video', ' lyrics',
    'live @', 'live at ', ' ft.', ' feat.',
    'album', ' ep ', ' ep)', '(ep)',
    'sessions', '(mv)', '[mv]',
    'official live', 'live performance',
    'acoustic version', 'official acoustic',
]

TV_CHANNELS = [
    'fox news', 'cnn', 'msnbc', 'cnbc', 'bbc', 'abc news', 'nbc news',
    'pbs news', 'sky news', 'reuters', 'bloomberg', 'food network',
    'discovery', 'hgtv', 'history channel', 'nat geo',
    'comedy central', 'adult swim',
]

TECH_TITLE_KEYWORDS = [
    'tutorial', 'how to', 'how-to', 'setup', 'set up', 'install',
    'review', 'explained', 'programming', 'coding', 'docker',
    'linux', 'python', 'javascript', 'react', 'homelab', 'home lab',
    'networking', 'server', 'raspberry pi', 'kubernetes', 'git ',
    'vs code', 'terminal', 'command line', 'bash', 'powershell',
]

TECH_CHANNELS = [
    'networkchuck', 'smart home solver', 'resinchemtech', 'linus tech tips',
    'techlinked', 'level1techs', 'wendell',
]


def categorize(raw_name: str, title: str, header: str) -> str:
    """Return category string for a single record."""
    name_l = raw_name.lower()
    title_l = title.lower()

    # YouTube Music header is always music
    if header == 'YouTube Music':
        return 'music'

    # YouTube TV header is always tv
    if header == 'YouTube TV':
        return 'tv'

    # Channel suffix signals
    for suffix in MUSIC_CHANNEL_SUFFIXES:
        if raw_name.endswith(suffix):
            return 'music'

    # Music title keywords
    if any(kw in title_l for kw in MUSIC_TITLE_KEYWORDS):
        return 'music'

    # TV / news channels
    if any(ch in name_l for ch in TV_CHANNELS):
        return 'tv'

    # Tech channels
    if any(ch in name_l for ch in TECH_CHANNELS):
        return 'tech'

    # Tech title keywords
    if any(kw in title_l for kw in TECH_TITLE_KEYWORDS):
        return 'tech'

    return 'unsure'


# ===========================================================================
# PARSING
# ===========================================================================

def extract_video_id(title_url: str) -> str:
    """Pull the video ID from a YouTube watch URL."""
    if not title_url:
        return ''
    # Decode unicode-escaped = sign
    url = title_url.replace('\\u003d', '=')
    m = re.search(r'[?&]v=([a-zA-Z0-9_-]{6,})', url)
    return m.group(1) if m else ''


def clean_title(raw: str) -> str:
    """Remove leading 'Watched'/'Watched this' prefix."""
    return TITLE_PREFIX_RE.sub('', raw).strip()


def normalize_name(raw: str) -> str:
    """Return a cleaned display name (suffixes stripped, whitespace normalized)."""
    return NORMALIZE_SUFFIXES.sub('', raw).strip()


def parse_records(data: list) -> list:
    """
    Parse raw JSON list into a flat list of record dicts.
    Each record:
        video_id, raw_name, norm_name, channel_url, title, title_url,
        date (YYYY-MM-DD), datetime_iso, header, category,
        subtitles_raw (full original subtitles list as JSON string)
    """
    records = []

    for entry in data:
        header = entry.get('header', 'YouTube')
        raw_title = entry.get('title', '')
        title_url = entry.get('titleUrl', '').replace('\\u003d', '=')
        time_str = entry.get('time', '')
        subtitles = entry.get('subtitles', [])

        # Clean title
        title = clean_title(raw_title)

        # Skip community posts (Viewed entries) -- not video watches
        if raw_title.lower().startswith('viewed '):
            continue

        # Skip completely empty / unavailable records
        if not title or title.startswith('https://') or 'no longer available' in title.lower():
            title_from_url = extract_video_id(title_url)
            if not title_from_url:
                continue  # truly nothing usable
            title = f'[unavailable: {title_from_url}]'

        # Video ID
        video_id = extract_video_id(title_url)

        # Date
        try:
            dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
            date_str = dt.strftime('%Y-%m-%d')
            datetime_iso = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            date_str = ''
            datetime_iso = time_str

        # Handle multiple subtitles (YouTube TV live channels)
        # We generate one record per subtitle entry so each show/channel is tracked
        if not subtitles:
            subtitles = [{'name': '[unknown]', 'url': ''}]

        # Preserve raw subtitles as a compact JSON string for the file
        subtitles_raw = json.dumps(subtitles, separators=(',', ':'))

        # For YouTube TV with multiple subtitles, use the first (show name)
        # but record all names
        primary_sub = subtitles[0]
        raw_name = primary_sub.get('name', '[unknown]')
        channel_url = primary_sub.get('url', '')

        norm_name = normalize_name(raw_name)
        category = categorize(raw_name, title, header)

        records.append({
            'video_id':       video_id,
            'raw_name':       raw_name,
            'norm_name':      norm_name,
            'channel_url':    channel_url,
            'title':          title,
            'title_url':      title_url,
            'date':           date_str,
            'datetime_iso':   datetime_iso,
            'header':         header,
            'category':       category,
            'subtitles_raw':  subtitles_raw,
        })

    return records


# ===========================================================================
# AGGREGATION
# ===========================================================================

def build_name_index(records: list) -> dict:
    """
    Build per-channel aggregate keyed by channel_url (falls back to raw_name).
    Returns dict: key -> {raw_name, norm_name, channel_url, category,
                          title_ids (set), play_count, date_first, date_last}
    """
    index = {}

    for r in records:
        # Key: channel_url preferred; fall back to raw_name so unknowns still group
        key = r['channel_url'] if r['channel_url'] else f'__name__{r["raw_name"]}'

        if key not in index:
            index[key] = {
                'raw_name':    r['raw_name'],
                'norm_name':   r['norm_name'],
                'channel_url': r['channel_url'],
                'category':    r['category'],
                'title_ids':   set(),
                'play_count':  0,
                'date_first':  r['date'],
                'date_last':   r['date'],
            }

        entry = index[key]
        entry['play_count'] += 1
        if r['video_id']:
            entry['title_ids'].add(r['video_id'])
        if r['date'] and r['date'] < entry['date_first']:
            entry['date_first'] = r['date']
        if r['date'] and r['date'] > entry['date_last']:
            entry['date_last'] = r['date']
        # Keep most common / most recent name in case of drift
        # (raw_name from the latest record wins -” revisit if needed)

    return index


def build_title_index(records: list) -> dict:
    """
    Build per-video aggregate keyed by video_id (falls back to title).
    Returns dict: key -> {video_id, raw_name, norm_name, channel_url,
                          title, title_url, category,
                          play_count, date_first, date_last}
    """
    index = {}

    for r in records:
        key = r['video_id'] if r['video_id'] else f'__title__{r["title"]}'

        if key not in index:
            index[key] = {
                'video_id':    r['video_id'],
                'raw_name':    r['raw_name'],
                'norm_name':   r['norm_name'],
                'channel_url': r['channel_url'],
                'title':       r['title'],
                'title_url':   r['title_url'],
                'category':    r['category'],
                'play_count':  0,
                'date_first':  r['date'],
                'date_last':   r['date'],
            }

        entry = index[key]
        entry['play_count'] += 1
        if r['date'] and r['date'] < entry['date_first']:
            entry['date_first'] = r['date']
        if r['date'] and r['date'] > entry['date_last']:
            entry['date_last'] = r['date']

    return index


# ===========================================================================
# APPEND / MERGE with previous run
# ===========================================================================

def load_existing_name_file(path: str) -> dict:
    """
    Load a previous name_file.txt and return a dict keyed by channel_url
    so play counts and date_first can be preserved across data refreshes.
    """
    existing = {}
    if not os.path.exists(path):
        print(f"  [append] Previous file not found at {path}, starting fresh.")
        return existing

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    # Skip header
    for line in lines[1:]:
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split(DELIMITER)
        if len(parts) < 8:
            continue
        # Columns: raw_name|norm_name|channel_url|category|title_count|total_plays|date_first|date_last
        key = parts[2] if parts[2] else f'__name__{parts[0]}'
        existing[key] = {
            'raw_name':    parts[0],
            'norm_name':   parts[1],
            'channel_url': parts[2],
            'category':    parts[3],
            'title_count': int(parts[4]) if parts[4].isdigit() else 0,
            'total_plays': int(parts[5]) if parts[5].isdigit() else 0,
            'date_first':  parts[6],
            'date_last':   parts[7],
        }

    print(f"  [append] Loaded {len(existing)} existing channels from {path}")
    return existing


def merge_name_index(new_index: dict, existing: dict) -> dict:
    """
    Merge new_index into existing so that:
    - date_first is the earliest across both
    - total_plays accumulates (new plays added to old total)
    - date_last is updated if newer
    - title_count is updated (may grow)
    Returns merged dict.
    """
    merged = dict(existing)  # start with old data

    for key, new in new_index.items():
        if key in merged:
            old = merged[key]
            # Preserve earliest date_first
            if new['date_first'] and (not old['date_first'] or new['date_first'] < old['date_first']):
                old['date_first'] = new['date_first']
            # Update date_last
            if new['date_last'] and new['date_last'] > old.get('date_last', ''):
                old['date_last'] = new['date_last']
            # Add new plays
            old['total_plays'] = old.get('total_plays', 0) + new['play_count']
            # Update title count (best effort -” we don't have the full set from old run)
            old['title_count'] = max(old.get('title_count', 0), len(new['title_ids']))
            # Update name in case it changed
            old['raw_name'] = new['raw_name']
            old['norm_name'] = new['norm_name']
        else:
            # Brand new channel
            merged[key] = {
                'raw_name':    new['raw_name'],
                'norm_name':   new['norm_name'],
                'channel_url': new['channel_url'],
                'category':    new['category'],
                'title_count': len(new['title_ids']),
                'total_plays': new['play_count'],
                'date_first':  new['date_first'],
                'date_last':   new['date_last'],
            }

    return merged


# ===========================================================================
# WRITING OUTPUT FILES
# ===========================================================================

def write_name_file(path: str, name_index: dict, is_merged: bool = False):
    """
    name_file.txt
    Columns: raw_name | norm_name | channel_url | category |
             title_count | total_plays | date_first | date_last
    Sorted by total_plays descending.
    """
    D = DELIMITER

    # Normalise dict so all entries have the same keys regardless of source
    rows = []
    for key, v in name_index.items():
        rows.append({
            'raw_name':    v.get('raw_name', ''),
            'norm_name':   v.get('norm_name', ''),
            'channel_url': v.get('channel_url', ''),
            'category':    v.get('category', 'unsure'),
            'title_count': v.get('title_count', len(v.get('title_ids', []))),
            'total_plays': v.get('total_plays', v.get('play_count', 0)),
            'date_first':  v.get('date_first', ''),
            'date_last':   v.get('date_last', ''),
        })

    rows.sort(key=lambda x: -x['total_plays'])

    header = D.join([
        'raw_name', 'norm_name', 'channel_url', 'category',
        'title_count', 'total_plays', 'date_first', 'date_last'
    ])

    with open(path, 'w', encoding='utf-8') as f:
        f.write(header + '\n')
        for r in rows:
            line = D.join([
                _safe(r['raw_name']),
                _safe(r['norm_name']),
                r['channel_url'],
                r['category'],
                str(r['title_count']),
                str(r['total_plays']),
                r['date_first'],
                r['date_last'],
            ])
            f.write(line + '\n')

    print(f"  Wrote {len(rows)} channels -> {path}")


def write_name_title_file(path: str, title_index: dict):
    """
    name_title_file.txt
    Columns: norm_name | raw_name | channel_url | category |
             title | title_url | video_id |
             date_first | date_last | play_count
    Sorted by norm_name asc, then play_count desc.
    """
    D = DELIMITER

    rows = list(title_index.values())
    rows.sort(key=lambda x: (x['norm_name'].lower(), -x['play_count']))

    header = D.join([
        'norm_name', 'raw_name', 'channel_url', 'category',
        'title', 'title_url', 'video_id',
        'date_first', 'date_last', 'play_count'
    ])

    with open(path, 'w', encoding='utf-8') as f:
        f.write(header + '\n')
        for r in rows:
            line = D.join([
                _safe(r['norm_name']),
                _safe(r['raw_name']),
                r['channel_url'],
                r['category'],
                _safe(r['title']),
                r['title_url'],
                r['video_id'],
                r['date_first'],
                r['date_last'],
                str(r['play_count']),
            ])
            f.write(line + '\n')

    print(f"  Wrote {len(rows)} unique videos -> {path}")


def write_dataset_info(path: str, records: list, name_index: dict,
                       title_index: dict, source_file: str,
                       append_mode: bool, run_ts: str):
    """
    dataset_info.txt -” human-readable run manifest.
    """
    dates = sorted([r['date'] for r in records if r['date']])
    first_date = dates[0] if dates else 'unknown'
    last_date  = dates[-1] if dates else 'unknown'

    cats = defaultdict(int)
    for r in records:
        cats[r['category']] += 1

    headers_cnt = defaultdict(int)
    for r in records:
        headers_cnt[r['header']] += 1

    lines = [
        "# Dufner YouTube History -” Dataset Info",
        f"# Generated: {run_ts}",
        "",
        "[run]",
        f"source_file       = {os.path.basename(source_file)}",
        f"append_mode       = {append_mode}",
        f"run_timestamp     = {run_ts}",
        "",
        "[this_dataset]",
        f"first_date        = {first_date}",
        f"last_date         = {last_date}",
        f"total_records     = {len(records)}",
        "",
        "[sources]",
    ]
    for h, c in sorted(headers_cnt.items()):
        lines.append(f"  {h:<20s} = {c}")

    lines += [
        "",
        "[categories_this_run]",
    ]
    for cat in ('music', 'tv', 'tech', 'unsure'):
        lines.append(f"  {cat:<20s} = {cats.get(cat, 0)}")

    lines += [
        "",
        "[aggregates]",
        f"unique_channels   = {len(name_index)}",
        f"unique_videos     = {len(title_index)}",
        "",
        "# NOTE: If this was an append run, unique_channels reflects the",
        "# merged total across all processed datasets.",
    ]

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  Wrote manifest -> {path}")


def write_category_review(path: str, name_index: dict):
    """
    category_review.txt
    Lists every channel in the 'unsure' category, sorted by play count.
    Edit this file to assign correct categories, then feed it back in
    via channel_overrides.txt (future feature).
    """
    D = DELIMITER

    unsure = [
        v for v in name_index.values()
        if v.get('category', 'unsure') == 'unsure'
    ]

    # Normalise play count field name
    for v in unsure:
        if 'total_plays' not in v:
            v['total_plays'] = v.get('play_count', 0)
        if 'title_count' not in v:
            v['title_count'] = len(v.get('title_ids', []))

    unsure.sort(key=lambda x: -x['total_plays'])

    header = D.join([
        '# EDIT category column below',
        'norm_name', 'channel_url', 'total_plays', 'title_count',
        'category (edit me)',
    ])

    lines = [
        "# category_review.txt",
        "# Channels that could not be auto-categorized.",
        "# Edit the last column, then save as channel_overrides.txt",
        "# Valid categories: music | tv | tech | unsure",
        "#",
        "norm_name" + D + "raw_name" + D + "channel_url" + D +
        "total_plays" + D + "title_count" + D + "category",
    ]

    for v in unsure:
        lines.append(D.join([
            v.get('norm_name', ''),
            v.get('raw_name', ''),
            v.get('channel_url', ''),
            str(v['total_plays']),
            str(v['title_count']),
            'unsure',
        ]))

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    print(f"  Wrote {len(unsure)} unsure channels -> {path}")



# ===========================================================================
# HTML PARSING (Google Takeout watch-history.html format)
# ===========================================================================

HTML_DATE_RE = re.compile(
    r'([A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2}:\d{2}[\s  ]*[AP]M)'
)


def _strip_tags(s):
    return re.sub(r'<[^>]+>', '', s)


def _unescape(s):
    return (s.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
             .replace('&quot;', '"').replace('&#39;', "'")
             .replace('&nbsp;', ' ').replace('&emsp;', '  '))


def _parse_html_date(s):
    """Parse 'Mar 6, 2026, 5:49:02 PM' -> ('YYYY-MM-DD', 'YYYY-MM-DDTHH:MM:SSZ')."""
    s = re.sub(r'[  \s]+', ' ', s).strip()
    s = re.sub(r'\s+[A-Z]{2,4}$', '', s).strip()
    try:
        dt = datetime.strptime(s, '%b %d, %Y, %I:%M:%S %p')
        return dt.strftime('%Y-%m-%d'), dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    except ValueError:
        return '', s


def parse_html_records(html_content: str) -> list:
    """
    Parse watch-history.html into the same record format as parse_records().
    Each outer-cell block contains one watch event.
    """
    records = []

    outer_cells = re.split(r'<div class="outer-cell[^"]*">', html_content)

    for cell in outer_cells[1:]:
        # --- Header: YouTube / YouTube Music / YouTube TV ---
        hm = re.search(r'<p class="mdl-typography--title">(.*?)<br>', cell, re.DOTALL)
        header = 'YouTube'
        if hm:
            ht = _strip_tags(hm.group(1)).strip()
            if 'Music' in ht:
                header = 'YouTube Music'
            elif 'TV' in ht:
                header = 'YouTube TV'

        # --- Content cell (not the right-side empty cell) ---
        cm = re.search(
            r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)</div>',
            cell, re.DOTALL
        )
        if not cm:
            continue
        content = cm.group(1)

        # --- Skip community posts (Viewed) ---
        prefix_m = re.match(r'^\s*([^<]+)', content)
        if prefix_m and 'Viewed' in prefix_m.group(1):
            continue

        # --- Video link ---
        vm = re.search(
            r'<a href="(https://(?:www|music)\.youtube\.com/watch[^"]+)">([^<]+)</a>',
            content
        )
        title_url = ''
        video_id  = ''
        raw_title = ''
        if vm:
            title_url = vm.group(1).replace('=', '=')
            raw_title = _unescape(vm.group(2))
            video_id  = extract_video_id(title_url)
        else:
            # Unavailable: URL may appear as plain text
            um = re.search(r'https://www\.youtube\.com/watch\S+', content)
            if um:
                title_url = um.group(0).rstrip('<')
                video_id  = extract_video_id(title_url)
            # Title: text after Watched keyword
            wm = re.search(r'Watched[^\w]*(.*?)(?:<br>|$)', _strip_tags(content))
            if wm:
                raw_title = wm.group(1).strip()

        title = clean_title(raw_title)

        if not title or title.startswith('https://') or 'no longer available' in title.lower():
            if video_id:
                title = f'[unavailable: {video_id}]'
            else:
                continue

        # --- Channel link ---
        chm = re.search(
            r'<a href="(https://www\.youtube\.com/(?:channel|user|c)/[^"]+)">([^<]+)</a>',
            content
        )
        channel_url = ''
        raw_name    = '[unknown]'
        if chm:
            channel_url = chm.group(1)
            raw_name    = _unescape(chm.group(2))

        # --- Date ---
        dm = HTML_DATE_RE.search(content)
        date_str = ''
        datetime_iso = ''
        if dm:
            date_str, datetime_iso = _parse_html_date(dm.group(1))

        norm_name = normalize_name(raw_name)
        category  = categorize(raw_name, title, header)
        subtitles_raw = json.dumps(
            [{'name': raw_name, 'url': channel_url}], separators=(',', ':')
        )

        records.append({
            'video_id':      video_id,
            'raw_name':      raw_name,
            'norm_name':     norm_name,
            'channel_url':   channel_url,
            'title':         title,
            'title_url':     title_url,
            'date':          date_str,
            'datetime_iso':  datetime_iso,
            'header':        header,
            'category':      category,
            'subtitles_raw': subtitles_raw,
        })

    return records

# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Dufner YouTube History Preprocessor"
    )
    parser.add_argument('input', help='Path to watch-history JSON file')
    parser.add_argument('--out', default='.', help='Output directory (default: current dir)')
    parser.add_argument(
        '--append',
        metavar='PREV_NAME_FILE',
        help='Path to a previous name_file.txt to merge play counts into'
    )
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    run_ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    print(f"\n{'='*60}")
    print(f"  Dufner YouTube History Preprocessor")
    print(f"  Input:  {args.input}")
    print(f"  Output: {args.out}")
    print(f"  Mode:   {'APPEND' if args.append else 'FRESH'}")
    print(f"{'='*60}\n")

    # --- Load and parse (auto-detect format) ---
    if args.input.lower().endswith('.html'):
        print("Loading HTML...")
        with open(args.input, encoding='utf-8', errors='replace') as f:
            html_content = f.read()
        print("Parsing records...")
        records = parse_html_records(html_content)
    else:
        print("Loading JSON...")
        with open(args.input, encoding='utf-8') as f:
            raw_data = json.load(f)
        print(f"  {len(raw_data)} raw entries loaded.")
        print("Parsing records...")
        records = parse_records(raw_data)
    print(f"  {len(records)} usable records after cleaning.")

    # --- Aggregate ---
    print("Building indexes...")
    name_index  = build_name_index(records)
    title_index = build_title_index(records)
    print(f"  {len(name_index)} unique channels.")
    print(f"  {len(title_index)} unique videos.")

    # --- Append merge ---
    append_mode = bool(args.append)
    if append_mode:
        print(f"\nMerging with previous run...")
        existing = load_existing_name_file(args.append)

        # Overlap check
        existing_dates = [v['date_last'] for v in existing.values() if v.get('date_last')]
        new_dates = sorted([r['date'] for r in records if r['date']])
        if existing_dates and new_dates:
            prev_last = max(existing_dates)
            new_first = new_dates[0]
            if new_first <= prev_last:
                print(f"\n  *** OVERLAP WARNING ***")
                print(f"  Previous data ends:  {prev_last}")
                print(f"  New data starts:     {new_first}")
                print(f"  Dates overlap -” duplicate plays may be counted.")
                print(f"  Consider trimming your new export before appending.\n")
            else:
                print(f"  Date check passed: prev ends {prev_last}, new starts {new_first}")

        name_index = merge_name_index(name_index, existing)
        print(f"  Merged total: {len(name_index)} channels.")

    # --- Write files ---
    print("\nWriting output files...")
    write_name_file(
        os.path.join(args.out, 'name_file.txt'),
        name_index,
        is_merged=append_mode
    )
    write_name_title_file(
        os.path.join(args.out, 'name_title_file.txt'),
        title_index
    )
    write_dataset_info(
        os.path.join(args.out, 'dataset_info.txt'),
        records, name_index, title_index,
        source_file=args.input,
        append_mode=append_mode,
        run_ts=run_ts
    )
    write_category_review(
        os.path.join(args.out, 'category_review.txt'),
        name_index
    )

    # --- Summary ---
    cats = defaultdict(int)
    for r in records:
        cats[r['category']] += 1

    dates = sorted([r['date'] for r in records if r['date']])

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Date range : {dates[0] if dates else "unknown"} -> {dates[-1] if dates else "unknown"}")
    print(f"  Records    : {len(records):,}")
    print(f"  Channels   : {len(name_index):,}")
    print(f"  Videos     : {len(title_index):,}")
    print(f"  music      : {cats.get('music',0):,}")
    print(f"  tv         : {cats.get('tv',0):,}")
    print(f"  tech       : {cats.get('tech',0):,}")
    print(f"  unsure     : {cats.get('unsure',0):,}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
