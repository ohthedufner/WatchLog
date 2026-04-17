"""
server.py — Local WatchLog editing server

Serves the static site AND provides a REST API for writing to wl.db.
Run this instead of a plain HTTP server when you need to edit data.

Usage:
    python server.py          (default port 8000)
    python server.py 8080

API endpoints:
    GET  /api/health
    GET  /api/artists?q=<search>
    GET  /api/artist-links/<slug>
    POST /api/artist-links          body: {from_slug, to_slug, label?, mutual?}
    DELETE /api/artist-links/<id>
"""

import os
import sqlite3
import sys
from flask import Flask, jsonify, request, send_from_directory, abort

BASE   = os.path.dirname(os.path.abspath(__file__))
DB     = os.path.join(BASE, "wl.db")

app = Flask(__name__)


# ── DB helper ─────────────────────────────────────────────────────────────────

def get_db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("""CREATE TABLE IF NOT EXISTS wl_channel_cats (
        wl_cc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
        wl_channel_url  TEXT NOT NULL UNIQUE,
        wl_category     TEXT NOT NULL
    )""")
    con.commit()
    return con


@app.route("/api/video-content-type", methods=["POST"])
def set_video_content_type():
    data         = request.get_json(force=True) or {}
    video_id     = (data.get("video_id")     or "").strip()
    content_type = (data.get("content_type") or "").strip().upper()
    VALID = {'MUSIC_VIDEO','AUDIO_ONLY','LYRIC_VIDEO','VISUALIZER','MEDLEY',
             'MUSIC_SET','BTS','SPOKEN','REACTION','BIO','CLIPS'}
    if not video_id or (content_type not in VALID and not content_type.startswith('OTHER_')):
        return jsonify({"ok": False, "error": "invalid input"}), 400
    con = get_db()
    con.execute("UPDATE wl_videos SET wl_content_type=? WHERE wl_video_id=?", (content_type, video_id))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ── Static file serving ───────────────────────────────────────────────────────

@app.route("/")
def root():
    return send_from_directory(BASE, "index.html")

@app.route("/<path:filename>")
def static_file(filename):
    # Block directory traversal
    safe = os.path.realpath(os.path.join(BASE, filename))
    if not safe.startswith(os.path.realpath(BASE)):
        abort(403)
    return send_from_directory(BASE, filename)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"ok": True, "mode": "local"})


# ── Artists (search for link targets) ─────────────────────────────────────────

@app.route("/api/artists")
def artists():
    q = request.args.get("q", "").strip()
    con = get_db()
    if q:
        rows = con.execute(
            """SELECT dj_artist_id, dj_name, dj_slug, dj_plays
               FROM   dj_artists
               WHERE  LOWER(dj_name) LIKE ?
                 AND  dj_name != '[unknown]'
               ORDER  BY dj_plays DESC
               LIMIT  25""",
            (f"%{q.lower()}%",),
        ).fetchall()
    else:
        rows = con.execute(
            """SELECT dj_artist_id, dj_name, dj_slug, dj_plays
               FROM   dj_artists
               WHERE  dj_name != '[unknown]'
               ORDER  BY dj_plays DESC
               LIMIT  50""",
        ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


# ── Artist links (See Also) ───────────────────────────────────────────────────

@app.route("/api/artist-links/<slug>")
def get_links(slug):
    con = get_db()
    rows = con.execute(
        """SELECT al.wl_al_id, al.wl_from_slug, al.wl_to_slug, al.wl_label,
                  COALESCE(a.dj_name, al.wl_to_slug) AS dj_name,
                  COALESCE(a.dj_plays, 0)             AS dj_plays
           FROM   wl_artist_links al
           LEFT JOIN dj_artists a ON a.dj_slug = al.wl_to_slug
           WHERE  al.wl_from_slug = ?
           ORDER  BY COALESCE(a.dj_plays, 0) DESC""",
        (slug,),
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/artist-links", methods=["POST"])
def add_link():
    data      = request.get_json(force=True) or {}
    from_slug = (data.get("from_slug") or "").strip()
    to_slug   = (data.get("to_slug")   or "").strip()
    label     = (data.get("label")     or "See also").strip()
    mutual    = bool(data.get("mutual", False))

    if not from_slug or not to_slug:
        return jsonify({"ok": False, "error": "from_slug and to_slug required"}), 400
    if from_slug == to_slug:
        return jsonify({"ok": False, "error": "Cannot link an artist to itself"}), 400

    con = get_db()
    created = []
    try:
        cur = con.execute(
            "INSERT INTO wl_artist_links (wl_from_slug, wl_to_slug, wl_label) VALUES (?,?,?)",
            (from_slug, to_slug, label),
        )
        created.append(cur.lastrowid)

        if mutual:
            try:
                cur2 = con.execute(
                    "INSERT INTO wl_artist_links (wl_from_slug, wl_to_slug, wl_label) VALUES (?,?,?)",
                    (to_slug, from_slug, label),
                )
                created.append(cur2.lastrowid)
            except sqlite3.IntegrityError:
                pass  # reverse link already exists — fine

        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        return jsonify({"ok": False, "error": "Link already exists"}), 409

    con.close()
    return jsonify({"ok": True, "created": created}), 201


@app.route("/api/unknown-channels")
def unknown_channels():
    con = get_db()
    rows = con.execute(
        """SELECT dj_name, dj_channel_url, dj_plays, dj_category
           FROM   dj_other_channels
           WHERE  dj_category IN ('unsure', '')
           ORDER  BY dj_plays DESC"""
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/channel-category", methods=["POST"])
def set_channel_category():
    data     = request.get_json(force=True) or {}
    url      = (data.get("channel_url") or "").strip()
    category = (data.get("category")    or "").strip()
    if not url or not category:
        return jsonify({"ok": False, "error": "channel_url and category required"}), 400

    con = get_db()
    # Persist in user-editable table (survives pipeline rebuild)
    con.execute(
        "INSERT INTO wl_channel_cats (wl_channel_url, wl_category) VALUES (?,?)"
        " ON CONFLICT(wl_channel_url) DO UPDATE SET wl_category=excluded.wl_category",
        (url, category),
    )
    # Apply immediately to live dj_other_channels
    con.execute(
        "UPDATE dj_other_channels SET dj_category=? WHERE dj_channel_url=?",
        (category, url),
    )
    con.commit()
    con.close()
    return jsonify({"ok": True})




@app.route("/api/artist-links/<int:link_id>", methods=["DELETE"])
def delete_link(link_id):
    con = get_db()
    con.execute("DELETE FROM wl_artist_links WHERE wl_al_id = ?", (link_id,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"WatchLog local server: http://localhost:{port}/")
    print(f"Database: {DB}")
    print("Ctrl-C to stop.\n")
    app.run(host="0.0.0.0", port=port, debug=False)
