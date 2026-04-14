#!/usr/bin/env python3
"""
apply_rules.py — apply category_rules.txt to to_categorize.csv

Usage:
    python manual_editing/apply_rules.py
    python manual_editing/apply_rules.py --merge-from some_fixed.csv

--merge-from FILE
    Merge manual categorizations from FILE before applying keyword rules.
    Entries with category X in the source file are converted to O.
    Only blank (or X) rows in to_categorize.csv are updated — manual
    edits you have already made are never overwritten.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(HERE, 'category_rules.txt')
DATA_FILE  = os.path.join(HERE, 'to_categorize.csv')

HEADER_COMMENT = """\
# WatchLog Channel Categorization
# ==========================================================
# CATEGORIES:
#   M = Music         T = Tech / Smart Home / DIY
#   D = DIY / Making  F = Food & Cooking
#   C = Comedy        N = News / Politics
#   G = Gaming        V = TV / Video
#   O = Other         (blank) = Not yet categorized
#
# HOW TO USE:
#   1. Fill in the 'cat' column for each row you want to categorize.
#      Leave blank to keep as "unsure" — sorted by play count, top first.
#   2. Save the file (keep as CSV).
#   3. To re-apply rules after updating category_rules.txt:
#         python manual_editing/apply_rules.py
#      This auto-fills blank rows that match keywords, without touching
#      anything you have already categorized manually.
#   4. To define a new category: add it to category_rules.txt, then
#      add it to the CATEGORIES legend above.
# ==========================================================
"""


def load_rules():
    """Parse category_rules.txt. Returns list of (code, [keywords])."""
    rules = []
    with open(RULES_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '|' not in line:
                continue
            code, _, kw_str = line.partition('|')
            code = code.strip().upper()
            keywords = [k.strip().lower() for k in kw_str.split(',') if k.strip()]
            if code and keywords:
                rules.append((code, keywords))
    return rules


def match_rule(channel_name, rules):
    """Return first matching category code, or '' if none."""
    name_lc = channel_name.lower()
    for code, keywords in rules:
        for kw in keywords:
            if kw in name_lc:
                return code
    return ''


def read_csv_rows(filepath):
    """
    Read a CSV file. Skips # comment lines and finds the header row by
    looking for a row whose first cell is 'cat'. Returns list of rows
    (each row is a list of strings).
    """
    rows = []
    header_found = False
    with open(filepath, encoding='utf-8', newline='') as f:
        for raw_line in f:
            stripped = raw_line.rstrip('\r\n')
            if stripped.startswith('#'):
                continue
            parsed = next(csv.reader([stripped]))
            if not header_found:
                if parsed and parsed[0].strip().lower() == 'cat':
                    header_found = True
                continue  # skip old-style legend / empty rows before header
            rows.append(parsed)
    return rows


def load_merge_source(filepath):
    """
    Read a CSV file and return {channel_name: category} for all rows
    that have a non-empty category. Category X is converted to O.
    """
    mapping = {}
    header_found = False
    with open(filepath, encoding='utf-8', newline='') as f:
        for raw_line in f:
            stripped = raw_line.rstrip('\r\n')
            if stripped.startswith('#'):
                continue
            parsed = next(csv.reader([stripped]))
            if not parsed:
                continue
            if not header_found:
                if parsed and parsed[0].strip().lower() == 'cat':
                    header_found = True
                continue
            if len(parsed) < 2:
                continue
            cat  = parsed[0].strip().upper()
            name = parsed[1].strip()
            if cat == 'X':
                cat = 'O'
            if name and cat:
                mapping[name] = cat
    return mapping


def write_csv(filepath, rows):
    """Write to_categorize.csv with the standard # header block."""
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        f.write(HEADER_COMMENT)
        writer = csv.writer(f, lineterminator='\n')
        writer.writerow(['cat', 'channel name', 'plays', 'videos', 'channel url'])
        for row in rows:
            # Normalise to exactly 5 columns
            padded = (row + ['', '', '', '', ''])[:5]
            writer.writerow(padded)


def main():
    merge_path = None
    args = sys.argv[1:]
    if '--merge-from' in args:
        idx = args.index('--merge-from')
        if idx + 1 < len(args):
            src = args[idx + 1]
            merge_path = src if os.path.isabs(src) else os.path.join(HERE, src)

    rules = load_rules()
    print(f'Loaded {len(rules)} category rule(s).')

    rows = read_csv_rows(DATA_FILE)
    print(f'Loaded {len(rows)} channel rows.')

    merge_map = {}
    if merge_path:
        merge_map = load_merge_source(merge_path)
        print(f'Loaded {len(merge_map)} manual categorization(s) from {os.path.basename(merge_path)}.')

    merged_count = 0
    rule_count   = 0
    still_blank  = 0

    for row in rows:
        while len(row) < 5:
            row.append('')

        cat  = row[0].strip().upper()
        name = row[1].strip()

        # Apply merge source first (only fills blank / X slots)
        if name in merge_map and (not cat or cat == 'X'):
            row[0] = merge_map[name]
            merged_count += 1
            cat = row[0]

        # Apply keyword rules to remaining blank / X slots
        if not cat or cat == 'X':
            matched = match_rule(name, rules)
            if matched:
                row[0] = matched
                rule_count += 1
                cat = matched

        if not row[0].strip():
            still_blank += 1

    write_csv(DATA_FILE, rows)

    print()
    print(f'  Merged from file  : {merged_count}')
    print(f'  Auto by rules     : {rule_count}')
    print(f'  Still uncategorized: {still_blank}')
    print()
    print('to_categorize.csv updated.')


if __name__ == '__main__':
    main()
