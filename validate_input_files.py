"""
validate_input_files.py — Pre-flight validator for Google Takeout watch-history.json

Run this before preprocess.py to catch problems early.

Usage:
    py -3 validate_input_files.py [input.json] [--db wl.db]

    input.json  defaults to Google_Takeout/watch-history.json
    --db        path to existing wl.db for overlap detection (optional)

Exit codes:
    0  — all checks passed (warnings may still be printed)
    1  — one or more errors found
"""

import json
import os
import sys
import argparse
import sqlite3
from datetime import datetime, timezone

# Windows cp1252 consoles crash on Unicode — reconfigure stdout to UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KNOWN_HEADERS   = {"YouTube", "YouTube Music", "YouTube TV"}
REQUIRED_FIELDS = {"header", "title", "time"}
TIME_FORMAT     = "%Y-%m-%dT%H:%M:%S.%fZ"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_time(ts):
    """Return a datetime (UTC) or None if unparseable."""
    if not ts:
        return None
    try:
        return datetime.strptime(ts, TIME_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        # Some records omit milliseconds
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d") if dt else "unknown"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_file(path):
    errors = []
    if not os.path.exists(path):
        errors.append(f"File not found: {path}")
        return None, errors
    if not path.lower().endswith(".json"):
        errors.append(f"Expected a .json file, got: {path}")
    return path, errors


def check_json(path):
    errors = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON: {e}")
        return None, errors
    except UnicodeDecodeError as e:
        errors.append(f"Encoding error (expected UTF-8): {e}")
        return None, errors
    if not isinstance(data, list):
        errors.append(f"Expected a JSON array at the top level, got {type(data).__name__}")
        return None, errors
    return data, errors


def check_records(data):
    errors = []
    warnings = []
    bad_header = []
    missing_fields = []
    bad_time = []
    no_subtitles = 0
    times = []

    for i, record in enumerate(data):
        if not isinstance(record, dict):
            errors.append(f"  Record {i}: not an object (got {type(record).__name__})")
            continue

        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            missing_fields.append((i, sorted(missing)))
            continue

        hdr = record.get("header", "")
        if hdr not in KNOWN_HEADERS:
            bad_header.append((i, hdr))

        ts = record.get("time", "")
        dt = parse_time(ts)
        if dt is None:
            bad_time.append((i, ts))
        else:
            times.append(dt)

        if not record.get("subtitles"):
            no_subtitles += 1

    # Summarize field errors (cap at 10 shown)
    if missing_fields:
        shown = missing_fields[:10]
        for idx, fields in shown:
            errors.append(f"  Record {idx}: missing required fields: {', '.join(fields)}")
        if len(missing_fields) > 10:
            errors.append(f"  ... and {len(missing_fields) - 10} more records with missing fields")

    if bad_header:
        shown = bad_header[:10]
        for idx, hdr in shown:
            warnings.append(f"  Record {idx}: unexpected header value '{hdr}'")
        if len(bad_header) > 10:
            warnings.append(f"  ... and {len(bad_header) - 10} more unexpected header values")

    if bad_time:
        shown = bad_time[:10]
        for idx, ts in shown:
            errors.append(f"  Record {idx}: unparseable time '{ts}'")
        if len(bad_time) > 10:
            errors.append(f"  ... and {len(bad_time) - 10} more unparseable times")

    if no_subtitles:
        warnings.append(
            f"  {no_subtitles}/{len(data)} records have no subtitles (channel unknown) — "
            "these are treated as deleted/unavailable videos"
        )

    return times, errors, warnings


def check_overlap(times, db_path):
    """Compare incoming date range against wh_events already in wl.db."""
    warnings = []
    errors = []

    if not times:
        return errors, warnings

    if not os.path.exists(db_path):
        warnings.append(f"  wl.db not found at {db_path} — skipping overlap check")
        return errors, warnings

    try:
        con = sqlite3.connect(db_path)
        row = con.execute(
            "SELECT MIN(wh_time), MAX(wh_time) FROM wh_events"
        ).fetchone()
        con.close()
    except sqlite3.Error as e:
        warnings.append(f"  Could not read wl.db for overlap check: {e}")
        return errors, warnings

    if not row or row[0] is None:
        warnings.append("  wl.db has no wh_events rows — no overlap to check")
        return errors, warnings

    db_min = parse_time(row[0]) or parse_time(row[0].replace(" ", "T") + "Z")
    db_max = parse_time(row[1]) or parse_time(row[1].replace(" ", "T") + "Z")

    in_min = min(times)
    in_max = max(times)

    if db_min and db_max:
        if in_max < db_min:
            warnings.append(
                f"  Incoming data ends {fmt_dt(in_max)}, before existing data starts "
                f"{fmt_dt(db_min)} — no overlap but also no continuity gap"
            )
        elif in_min > db_max:
            warnings.append(
                f"  Incoming data starts {fmt_dt(in_min)}, after existing data ends "
                f"{fmt_dt(db_max)} — gap of {(in_min - db_max).days} days"
            )
        else:
            overlap_start = max(in_min, db_min)
            overlap_end   = min(in_max, db_max)
            warnings.append(
                f"  Overlap detected: {fmt_dt(overlap_start)} to {fmt_dt(overlap_end)} "
                "already exists in wl.db — duplicate events will be imported "
                "(deduplicated by wh_video_id + wh_time in build_wl_db.py if supported)"
            )

    return errors, warnings


# ---------------------------------------------------------------------------
# Header breakdown
# ---------------------------------------------------------------------------

def header_breakdown(data):
    counts = {}
    for record in data:
        if isinstance(record, dict):
            hdr = record.get("header", "(missing)")
            counts[hdr] = counts.get(hdr, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Validate Google Takeout watch-history.json")
    parser.add_argument(
        "input",
        nargs="?",
        default=os.path.join(os.path.dirname(__file__), "Google_Takeout", "watch-history.json"),
        help="Path to watch-history.json (default: Google_Takeout/watch-history.json)",
    )
    parser.add_argument(
        "--db",
        default=os.path.join(os.path.dirname(__file__), "wl.db"),
        help="Path to existing wl.db for overlap detection (default: wl.db)",
    )
    args = parser.parse_args()

    all_errors   = []
    all_warnings = []

    print(f"Validating: {args.input}")
    print("-" * 60)

    # 1. File exists
    _, errs = check_file(args.input)
    all_errors.extend(errs)
    if errs:
        _report(all_errors, all_warnings)
        return 1

    # 2. Valid JSON, top-level list
    data, errs = check_json(args.input)
    all_errors.extend(errs)
    if errs:
        _report(all_errors, all_warnings)
        return 1

    print(f"Total records: {len(data)}")

    # 3. Header breakdown
    breakdown = header_breakdown(data)
    for hdr, count in sorted(breakdown.items()):
        print(f"  {hdr}: {count:,}")

    # 4. Record-level checks
    times, errs, warns = check_records(data)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    # 5. Date range
    if times:
        print(f"Date range: {fmt_dt(min(times))} to {fmt_dt(max(times))}")
    else:
        all_errors.append("No valid timestamps found in records")

    # 6. Overlap check
    errs, warns = check_overlap(times, args.db)
    all_errors.extend(errs)
    all_warnings.extend(warns)

    return _report(all_errors, all_warnings)


def _report(errors, warnings):
    print()
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(w)
        print()
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(e)
        print()
        print("Result: FAILED — fix errors before running preprocess.py")
        return 1
    else:
        print("Result: OK — safe to run preprocess.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
