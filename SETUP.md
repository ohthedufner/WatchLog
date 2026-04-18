# WatchLog — Setup Guide

This covers everything you do once: install, configure your categories, run the pipeline for the first time, and open the site.

For day-to-day operation after setup, see [USAGE.md](USAGE.md).

---

## Requirements

- Python 3.10 or later
- Flask (`pip install flask`)
- A Google Takeout export from your YouTube account

---

## Step 1: Install

Clone the repository and install the one dependency:

```bash
git clone https://github.com/ohthedufner/WatchLog.git
cd WatchLog
pip install flask
```

---

## Step 2: Export your YouTube history

1. Go to [Google Takeout](https://takeout.google.com)
2. Deselect everything, then select only **YouTube and YouTube Music**
3. Under YouTube options, select only **history** and choose **JSON** format
4. Download and unzip the export
5. Place `watch-history.json` in the `Google_Takeout/` folder inside your WatchLog directory

---

## Step 3: Define your categories

> **Coming soon — not yet available in the UI.** This step will be done through the admin page before the pipeline runs. For now, the default categories are applied automatically: Music and Other are always present. Additional categories (News, Tech, TV, etc.) can be assigned during channel categorization after the first run.

Categories tell WatchLog how to organize your non-music channels. **Music** and **Other** are fixed and always present. You'll be able to define up to 6 additional categories of your own (News, Tech, Gaming, etc.).

This step is done before processing so that keyword-based auto-categorization has a target list to work against from the start.

---

## Step 4: Verify your data

> **Coming soon.** This step will be available as part of the admin page setup flow.

Before running the full pipeline, a verification step checks your Takeout file and shows a summary:

```
Found:  7,300 watch events
        2,007 channels
        Date range: 2018-01-04 → 2026-03-08
        Format: JSON (standard)
```

If the counts look wrong, you can catch it here before committing to a full build.

**For now:** open `watch-history.json` and confirm it contains an array of objects with `header`, `title`, and `time` fields.

---

## Step 5: Run the pipeline

```bash
python preprocess.py
python build_watchlog_db.py
python build_wl_db.py
python build_data_json.py
```

This takes a few minutes on first run (MusicBrainz lookups are rate-limited to 1 request/second and cached after the first run).

What gets built:

```
preprocess.py          →  flat pipe-delimited files from your Takeout JSON
build_watchlog_db.py   →  watchlog.db  (title cleaning, MusicBrainz enrichment)
build_wl_db.py         →  wl.db        (presentation database, your source of truth)
build_data_json.py     →  data.json + admin_data.json
```

---

## Step 6: Open the site

**View-only** (no editing features):

```bash
python -m http.server 8000
```

**With Curator mode** (enables editing features on every page):

```bash
python server.py
```

Open `http://localhost:8000` in your browser.

After the first run, the music side of the site will have data immediately. Many of your channels will show as "Other" — that's expected. See [channel categorization in CURATING.md](CURATING.md#channel-categorization) for how to work through them at your own pace.

---

## What's next

- **[USAGE.md](USAGE.md)** — how to add new Takeout exports as your history grows
- **[CURATING.md](CURATING.md)** — how to use Curator mode to tag, link, and annotate your data
