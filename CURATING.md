# WatchLog — Curating Guide

Curator mode lets you annotate and organize your data directly in the browser. Everything you change is stored in `wl.db` and survives pipeline rebuilds — your curation work is permanent.

---

## Enabling Curator mode

Curator features require the local Flask server:

```bash
python server.py
```

Open `http://localhost:8000`. When the server is running, the nav bar shows a **Viewer / Curator** toggle. Switch to Curator mode to enable editing on any page.

> **On the live demo:** Curator features are not available — the demo is a static site with no server. Any page that would normally offer editing will explain this when you visit it.

---

## Content type tagging

Every music video has a content type. WatchLog assigns a default on import based on title keywords, but you can correct any of them.

**Where:** Artist detail page or song detail page, in Curator mode — each video row has a content type dropdown.

**Available types:**

| Type | Description |
|---|---|
| `MUSIC_VIDEO` | Official or fan music video |
| `AUDIO_ONLY` | Audio with no video component |
| `LYRIC_VIDEO` | Lyrics displayed on screen |
| `VISUALIZER` | Abstract/animated visuals |
| `MEDLEY` | Multiple songs in one video |
| `MUSIC_SET` | Concert or multi-song performance |
| `BTS` | Behind the scenes |
| `SPOKEN` | Primarily spoken word |
| `REACTION` | Creator reacting to a song or video |
| `BIO` | Biographical or history content |
| `CLIPS` | Fan compilations or clip collections |
| `OTHER_XXXXXXXX` | Freeform 8-character tag (e.g. `OTHER_ACOUSTIC`) |

Changes save immediately. Your assignments are never overwritten by the pipeline.

---

## Artist "See Also" links

See Also links connect related artists on their detail pages — side projects, collaborators, bands a solo artist came from.

**Where:** Artist detail page, in Curator mode — a search field and chip list appear in the See Also section.

- Search by name to find the target artist
- Add as one-way or mutual (adds both directions in one step)
- Remove any link with the × on its chip
- Links use the artist slug as a stable key and survive artist name changes

---

## Channel categorization

Channels are auto-categorized during preprocessing, but many will land in **Other** — channels the auto-rules didn't recognize. Working through these improves what shows up on the Channels page and ensures miscategorized content gets moved to the right place.

> **Coming soon — not yet in the admin UI.** Currently done via the API or flat file workflow. A categorization table with per-row dropdowns and keyword rules is planned as the next admin page feature (see PLAN.md 3B.1).

**How it will work:**
- Admin page shows a filterable table of all channels: name, play count, current category, uncategorized flag
- Assign a category per row via dropdown — saves immediately
- Keyword rules panel lets you match groups of channels by keyword and apply categories in bulk
- Progress indicator shows how many channels still need review
- You can categorize in batches over multiple sessions — the site works fine in the meantime
- After categorizing a batch, trigger a rebuild to see changes reflected in the site

**Music and Other are fixed.** They are always present and cannot be removed. Additional categories are user-defined during initial setup.

---

## Notes

> **Coming soon — schema exists, UI not yet built.**

Each song and video will have a freeform notes field, editable in-page in Curator mode. Notes are plain text — no markup. Stored in `wl_songs.wl_notes` and `wl_videos.wl_notes`.

---

## Artist content (bios, narrative arcs)

> **Coming soon — not yet built.**

Each artist will have a Markdown file in `content/artists/` with a YAML frontmatter section (slug, channels, tags) and free prose for biography, narrative arcs, and other long-form content.

These files are the source of truth — stored in Git, portable, renderable anywhere. A curator-mode editor on the artist detail page will let you edit them in-browser without opening a text editor. Saving writes the `.md` file to disk; you commit to Git when ready.

---

## What curator edits survive a pipeline rebuild

| Feature | Survives rebuild? |
|---|---|
| Content type assignments | Yes — stored in `wl_videos.wl_content_type` |
| See Also links | Yes — stored in `wl_artist_links` |
| Channel category overrides | Yes — stored in `wl_channel_cats` |
| Notes | Yes — stored in `wl_songs.wl_notes`, `wl_videos.wl_notes` |
| Artist content files | Yes — Markdown files on disk, not in the pipeline |

The pipeline never touches curator tables. They use `CREATE TABLE IF NOT EXISTS` and are preserved on every run.
