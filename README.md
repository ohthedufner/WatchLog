# WatchLog

Your YouTube watch history, made browsable.

WatchLog takes a Google Takeout export and turns it into a personal music and video history viewer — browse by artist, song, and channel, see play counts and recently watched, and curate your own metadata: content types, artist relationships, notes, and more. Everything runs locally. Your data stays yours.

**[Live demo →](https://ohthedufner.github.io/WatchLog/)**

---

## What makes it interesting

**It's your data, organized the way a music fan thinks.** Not a playlist manager, not a recommendation engine — just your actual history, searchable and browsable with real play counts and timeline data pulled from what you've actually watched.

**It separates what you watched from what it means.** The pipeline cleans raw YouTube titles into proper song names, extracts featured artists, strips noise suffixes, and matches recordings against MusicBrainz. A song watched 40 times on three different channels is still one song.

**The curator layer is built in.** Running the local server activates a Viewer / Curator toggle on every page. In Curator mode you can tag content types, link related artists, add notes, and categorize channels — all stored in a database that survives pipeline rebuilds. The viewer never touches your source data.

**Themes are a CSS swap, not a rebuild.** Two themes ship today (Neon and Day), switchable from the nav bar, persisted in `localStorage`. The visual layer is isolated in `watchlog.css` using CSS custom properties — adding or replacing a theme is a CSS-only change.

**No frameworks, no lock-in.** Pure HTML/CSS/JS frontend. Python + SQLite backend. Open formats throughout. If the tool disappears tomorrow, nothing is lost.

---

## Pages

Home · Artists · Songs · Channels · Search

Player modes: embedded YouTube IFrame or direct YouTube tab.

---

## Documentation

- **[SETUP.md](SETUP.md)** — install, configure, and run WatchLog for the first time
- **[USAGE.md](USAGE.md)** — day-to-day operation: adding new data, running the pipeline, serving the site
- **[CURATING.md](CURATING.md)** — everything in Curator mode: content types, See Also links, channel categories, notes

---

## License

MIT — see [LICENSE](LICENSE).  
Data files processed by this tool belong to their respective owners.
