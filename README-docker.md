# WatchLog — Docker Quick Start

## Requirements
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running

## Start the server

```bash
docker compose up --build
```

Open your browser to **http://localhost:8000**

The project folder is mounted as a volume — any changes to files (including `wl.db`) are live without rebuilding.

## Stop the server

```bash
docker compose down
```

## Rebuild after dependency changes

Only needed if you add new pip packages:

```bash
docker compose up --build
```

## Running pipeline scripts inside the container

```bash
docker compose exec watchlog python build_wl_db.py
docker compose exec watchlog python build_data_json.py
```

Or run them directly on your host with `py -3 script.py` — the DB files are shared via the volume mount.

## Notes

- Port 8000 is used by both the Docker container and the plain `python server.py` command. Do not run both at the same time.
- `wl.db` is never copied into the image — it lives only in your project folder and is accessed via the volume mount.
- WAL mode is enabled on `wl.db` at startup — safe for pipeline scripts to run while the server is running.
