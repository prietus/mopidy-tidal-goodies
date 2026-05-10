"""Listening history capture + storage.

Hooks into Mopidy's CoreListener events from a Pykka frontend actor and writes
each play to SQLite. The HTTP handlers in ``handlers.py`` read from the same
DB to serve recent / most-played / totals views.

We record on ``track_playback_ended`` because that's when ``time_position``
reflects the actual played duration. ``track_playback_paused`` /
``track_playback_resumed`` aren't needed — Mopidy collapses pauses into the
final ``time_position`` on the ended event.

Independent from mopidy-tidal: this works for any backend (local, file,
spotify, podcast, ...) so a server with no Tidal still gets stats.
"""
import logging
import pathlib
import sqlite3
import time

import pykka
from mopidy.core import CoreListener

logger = logging.getLogger(__name__)


def db_path_from_config(config) -> pathlib.Path:
    """Resolve the SQLite path under Mopidy's data_dir/<ext_name>/."""
    base = pathlib.Path(config["core"]["data_dir"]) / "tidal_goodies"
    base.mkdir(parents=True, exist_ok=True)
    return base / "history.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
  id            INTEGER PRIMARY KEY,
  played_at     INTEGER NOT NULL,           -- unix seconds
  track_uri     TEXT NOT NULL,
  track_name    TEXT NOT NULL DEFAULT '',
  artist        TEXT NOT NULL DEFAULT '',
  album         TEXT NOT NULL DEFAULT '',
  duration_ms   INTEGER NOT NULL DEFAULT 0,
  played_ms     INTEGER NOT NULL DEFAULT 0,
  completed     INTEGER NOT NULL DEFAULT 0  -- 1 if played >= 50% (scrobble-ish)
);
CREATE INDEX IF NOT EXISTS idx_plays_played_at ON plays(played_at DESC);
CREATE INDEX IF NOT EXISTS idx_plays_track_uri ON plays(track_uri);
"""


def open_db(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


class PlaybackHistoryFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core):
        super().__init__()
        self.config = config
        self.core = core
        self.path = db_path_from_config(config)
        self.conn: sqlite3.Connection | None = None

    def on_start(self):
        try:
            self.conn = open_db(self.path)
            logger.info("tidal-goodies stats: history at %s", self.path)
        except Exception as e:
            logger.exception("tidal-goodies stats: failed to open DB: %s", e)
            self.conn = None

    def on_stop(self):
        if self.conn is not None:
            self.conn.close()

    # CoreListener events ────────────────────────────────────────────────

    def track_playback_ended(self, tl_track, time_position):
        if self.conn is None or tl_track is None or tl_track.track is None:
            return
        track = tl_track.track
        artist = ", ".join(a.name for a in (track.artists or []) if a.name)
        album = track.album.name if track.album and track.album.name else ""
        duration_ms = int(track.length or 0)
        played_ms = int(time_position or 0)
        # Scrobble-like rule: ≥50% of length OR ≥4 minutes counts as completed.
        completed = 1 if (
            duration_ms > 0
            and (played_ms >= duration_ms // 2 or played_ms >= 240_000)
        ) else 0
        try:
            self.conn.execute(
                "INSERT INTO plays (played_at, track_uri, track_name, artist,"
                " album, duration_ms, played_ms, completed)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    int(time.time()),
                    track.uri,
                    track.name or "",
                    artist,
                    album,
                    duration_ms,
                    played_ms,
                    completed,
                ),
            )
        except Exception as e:
            logger.warning("tidal-goodies stats: insert failed: %s", e)
