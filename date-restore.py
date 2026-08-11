#!/usr/bin/env python3

import json
import os
import re
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


MOVIES = Path(os.environ.get("MOVIES_DIR", "/media/movies"))
TV = Path(os.environ.get("TV_DIR", "/media/tv"))
INDEX_FILE = Path(os.environ.get("INDEX_FILE", "/media/media-timestamps.json"))

SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL", "300"))

VIDEO_EXTENSIONS = {
    ext.strip().lower()
    if ext.strip().startswith(".")
    else "." + ext.strip().lower()
    for ext in os.environ.get("VIDEO_EXTENSIONS", "mkv,mp4").split(",")
    if ext.strip()
}

EPISODE_RE = re.compile(r"(S\d{2}E\d{2}(?:-E\d{2})?)", re.IGNORECASE)


def main():
    index = load_index()
    scan(index)

    handler = MediaHandler(index)

    observer = Observer()
    if MOVIES.exists():
        print(f"Watching {MOVIES}")
        observer.schedule(handler, str(MOVIES), recursive=True)
    if TV.exists():
        print(f"Watching {TV}")
        observer.schedule(handler, str(TV), recursive=True)
    observer.start()

    print(f"Watching for file changes. Scan every {SCAN_INTERVAL}s")

    try:
        while observer.is_alive():
            observer.join(SCAN_INTERVAL)
            scan(index)
    finally:
        observer.stop()
        observer.join()


def load_index():
    if not INDEX_FILE.exists():
        print(f"Existing index not found at {INDEX_FILE}")
        return {}
    print(f"Loading index from {INDEX_FILE}")
    with INDEX_FILE.open() as f:
        return json.load(f)


def save_index(index):
    print(f"Saving index to {INDEX_FILE}")
    temp_file = INDEX_FILE.with_suffix(".tmp")
    with temp_file.open("w") as f:
        json.dump(index, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_file, INDEX_FILE)


def scan(index):
    found = 0
    added = 0
    restored = 0
    kept = 0

    if MOVIES.exists():
        print(f"Scanning {MOVIES}")
        for movie_dir in MOVIES.iterdir():
            if not movie_dir.is_dir():
                continue

            for filepath in movie_dir.iterdir():
                key = get_key(filepath)
                if not key:
                    continue

                mtime = get_mtime(filepath)
                if mtime is None:
                    continue

                found += 1

                if key not in index:
                    index[key] = mtime
                    added += 1
                    print(f"New: {key}")
                elif mtime != index[key]:
                    restore_mtime(filepath, index[key])
                    restored += 1
                else:
                    kept +=1

    if TV.exists():
        print(f"Scanning {TV}")
        for show_dir in TV.iterdir():
            if not show_dir.is_dir():
                continue

            for season_dir in show_dir.iterdir():
                if not season_dir.is_dir():
                    continue

                for filepath in season_dir.iterdir():
                    key = get_key(filepath)
                    if not key:
                        continue

                    mtime = get_mtime(filepath)
                    if mtime is None:
                        continue

                    found += 1

                    if key not in index:
                        index[key] = mtime
                        added += 1
                        print(f"New: {key}")
                    elif mtime != index[key]:
                        restore_mtime(filepath, index[key])
                        restored += 1
                    else:
                        kept +=1

    if added:
        save_index(index)

    print(
        f"Scan complete: "
        f"{found} found, "
        f"{added} new, "
        f"{restored} restored, "
        f"{kept} kept, "
        f"{len(index)} indexed"
    )


def get_key(filepath):
    if filepath.suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    # Movie: /movies/TITLE (YEAR)/TITLE (YEAR) - METADATA.EXT
    if filepath.parent.parent == MOVIES:
        return f"movies/{filepath.parent.name}"

    # TV: /tv/TITLE YEAR/Season XX/TITLE YEAR - SXXEXX - METADATA.EXT
    if filepath.parent.parent.parent == TV:
        match = EPISODE_RE.search(filepath.stem)
        if match:
            episode = match.group(1).upper()
            return f"tv/{filepath.parent.parent.name}/{episode}"

    return None


def get_mtime(filepath):
    try:
        return filepath.stat().st_mtime
    except FileNotFoundError:
        return None


def restore_mtime(filepath, timestamp):
    try:
        stat = filepath.stat()
        if stat.st_mtime != timestamp:
            print(f"Changing mtime of {filepath} to {timestamp}")
            os.utime(filepath, (stat.st_atime, timestamp))
    except FileNotFoundError:
        pass


class MediaHandler(FileSystemEventHandler):
    def __init__(self, index):
        self.index = index

    def on_created(self, event):
        self.handle(event, event.src_path)

    def on_moved(self, event):
        self.handle(event, event.dest_path)

    def handle(self, event, path):
        if event.is_directory:
            return

        filepath = Path(path)
        key = get_key(filepath)
        if key is None:
            return

        timestamp = self.index.get(key)

        if timestamp is None:
            print(f"Ignoring new video until next full scan: {filepath}")
            return

        restore_mtime(filepath, timestamp)

if __name__ == "__main__":
    main()
