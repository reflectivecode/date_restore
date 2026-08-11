# Date Restore

A small filesystem watcher that preserves the original modification time of movies and TV episodes when they are replaced by an upgraded version with the same or different filename.

This is useful when upgrading a movie or episode causes the new file to receive a new filesystem modification time. Media servers such as Jellyfin may use filesystem timestamps when determining when media was added.

*Important:* Configure Jellyfin to "Use file creation date" to determine the date added behavior for new content. This setting can be found under Dashboard -> Libraries -> Display

Date Restore maintains an index of the original modification time for each movie and episode. When an existing media file is replaced, the original timestamp is restored.

## How It Works

Date Restore watches two media directory trees (configurable):

```text
/media/movies
/media/tv
```

Movies are expected to have this structure:

```text
movies/
└── Movie Title (2025)/
    └── Movie Title (2025) - metadata.mkv
```

TV shows are expected to have this structure:

```text
tv/
└── Show Title (2025)/
    └── Season 01/
        └── Show Title (2025) - S01E01 - Episode Title - metadata.mkv
```

The directory depth is fixed.

Only files with extensions configured by `VIDEO_EXTENSIONS` are considered. By default `.mkv` and `.mp4`

### Movie identity

A movie is identified by its movie directory:

```text
movies/Movie Title (2025)
```

### TV episode identity

An episode is identified by the show directory and episode number:

```text
tv/Show Title (2025)/S01E01
```

Multi-episode files are kept as a single entry:

```text
tv/Show Title (2025)/S01E01-E02
```

The filename's other release metadata is not relevant.

## Index

The project maintains a JSON index containing the original modification time for each movie and episode.

Example:

```json
{
  "movies/Another Movie (2024)": 1724198400.0,
  "movies/The First Movie (2001)": 1755304302.123,
  "tv/Best Show (2025)/S01E08": 1754684111.456,
  "tv/Best Show (2025)/S01E09": 1754684112.789,
  "tv/Best Show (2025)/S01E10-E11": 1754684113.654
}
```

The index is loaded into memory when the program starts.

### Periodic scan

Every `SCAN_INTERVAL` seconds (300s by default), the filesystem is scanned.

For each video file:

* If it is not in the index, its current modification time is recorded.
* If it is already in the index, its modification time is restored from the index.

The periodic scan is the **only mechanism that adds entries to the index**.

This is intentional. It prevents a newly imported file from establishing a new timestamp through a race with the filesystem watcher.

### Filesystem watcher

The inotify watcher handles changes immediately.

When a video file is created or moved into a watched directory:

* If the movie/episode exists in the index, its original modification time is restored.
* If it does not exist in the index, nothing is done.

The next periodic scan will discover and index new media.

## Environment Variables

### `MOVIES_DIR`

Root directory containing movies.

Default: `/media/movies`

### `TV_DIR`

Root directory containing TV shows.

Default: `/media/tv`

### `INDEX_FILE`

Path to the JSON index.

Default: `/media/media-timestamps.json`


### `SCAN_INTERVAL`

Number of seconds between filesystem scans.

Default: `300`

### `VIDEO_EXTENSIONS`

Comma-separated list of video file extensions.

Default: `mkv,mp4`

The value can be specified with or without the leading period.

For example:

```text
VIDEO_EXTENSIONS=mkv,mp4
```

or:

```text
VIDEO_EXTENSIONS=.mkv,.mp4
```

Both result in:

```text
.mkv
.mp4
```

Additional formats can be configured:

```text
VIDEO_EXTENSIONS=mkv,mp4,m4v,avi
```


## Docker

The latest Docker image is automatically built and pushed to both of these registries:

```text
ghcr.io/reflectivecode/date-restore:latest
```

and

```text
reflectivecode/date-restore:latest
```

The container needs access to the media directories because it reads and modifies their filesystem timestamps. The container does not need to run as root nor does it need any network access. The container can run in a readonly filesystem as long as it has write access to the media directories and the index file.

For example:

```bash
docker run -d \
  --name date-restore \
  --restart unless-stopped \
  --read-only \
  --network=none \
  -e MOVIES_DIR=/media/movies \
  -e TV_DIR=/media/tv \
  -e INDEX_FILE=/media/media-timestamps.json \
  -e SCAN_INTERVAL=300 \
  -e VIDEO_EXTENSIONS=mkv,mp4 \
  -v /host_path/media:/media \
  ghcr.io/reflectivecode/date-restore:latest
```

### Running as a specific user

The container should normally run as the same user that owns the media files, or as a user with permission to modify their timestamps.

For example:

```bash
docker run -d \
  --name date-restore \
  --restart unless-stopped \
  --read-only \
  --network=none \
  --user "$(id -u):$(id -g)" \
  -e MOVIES_DIR=/media/movies \
  -e TV_DIR=/media/tv \
  -e INDEX_FILE=/media/media-timestamps.json \
  -e SCAN_INTERVAL=300 \
  -e VIDEO_EXTENSIONS=mkv,mp4 \
  -v /host_path/media:/media \
  ghcr.io/reflectivecode/date-restore:latest
```

## Docker Compose

Example `compose.yml`:

```yaml
services:
  date-restore:
    image: ghcr.io/reflectivecode/date-restore:latest
    container_name: date-restore
    restart: unless-stopped
    read_only: true
    network_mode: none
    user: "${PUID}:${PGID}"
    environment:
      MOVIES_DIR: /media/movies
      TV_DIR: /media/tv
      INDEX_FILE: /media/media-timestamps.json
      SCAN_INTERVAL: "300"
      VIDEO_EXTENSIONS: mkv,mp4

    volumes:
      - /host_path/media:/media

```
Create a `.env` file next to the Compose file:

```text
PUID=1000
PGID=1000
```

Replace those values with the UID and GID that should have permission to modify the media files.


## Important Notes

### Modification time, not creation time

Date Restore does **not** modify the filesystem creation/birth time.

Instead, it records the original file's **modification time (****`mtime`****)** and restores that timestamp when the media is upgraded.

The filesystem creation time remains unchanged.

### New media

New media is deliberately not handled immediately by the inotify watcher.

For example:

```text
New movie file added
        ↓
inotify detects it
        ↓
not in index
        ↓
nothing happens
        ↓
periodic scan
        ↓
movie is added to index
```

This prevents a race where the watcher could accidentally establish an incorrect timestamp.

### Upgraded media

For an existing movie:

```text
Original:
Movie (2025) - [1080p][x264]-Group.mkv
mtime = 2025-08-15 21:31:42

          ↓ Upgrade

New:
Movie (2025) - [2160p][x265]-OtherGroup.mkv
mtime = 2026-08-10 01:20:00

          ↓ Date Restore

New:
Movie (2025) - [2160p][x265]-OtherGroup.mkv
mtime = 2025-08-15 21:31:42
```

The index remains:

```
{
  "movies/Movie (2025)": 1755304302.123
}
```
