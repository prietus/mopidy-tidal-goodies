# Mopidy-Tidal-Goodies

[![PyPI](https://img.shields.io/pypi/v/mopidy-tidal-goodies)](https://pypi.org/project/mopidy-tidal-goodies/)

HTTP endpoints for things [mopidy-tidal](https://github.com/EbbLabs/mopidy-tidal)
doesn't (yet) expose: favoriting, mutable playlists, personalized mixes.

It's a companion package — it does **not** replace `mopidy-tidal`. It reuses
the Tidal session that `mopidy-tidal` has already authenticated, so clients
talking to it don't need their own OAuth flow or Tidal credentials.

## Why this exists

`mopidy-tidal` covers browse + search + playback well, but the Tidal API
surface is much larger. Adding everything upstream is slow (review cycles,
maintainer scope), and a fair amount of it is too client-specific to belong
there. This package fills the gap on your own server, on your own release
cadence.

## Install

On your Mopidy host:

```sh
pip install git+https://github.com/prietus/mopidy-tidal-goodies.git
```

Then enable in `mopidy.conf`:

```ini
[tidal_goodies]
enabled = true
```

Restart Mopidy. Endpoints are mounted under `/tidal_goodies/` on whatever
port your `[http]` extension is bound to (typically `6680`).

## Endpoints

### Discovery

```
GET    /tidal_goodies/_health
```

Returns version + which features are active. Use this to decide which UI
features to show in your client.

```json
{
  "version": "0.2.0",
  "features": {
    "favorites": true,
    "favorites_active": true,
    "stats": true
  }
}
```

`favorites_active` is `false` when `mopidy-tidal` isn't loaded or isn't
logged in — favorites endpoints will return `503` in that case. `stats`
works for any backend (independent of Tidal).

### Favorites

```
GET    /tidal_goodies/favorites/albums
POST   /tidal_goodies/favorites/albums          {"id": "<tidal album id>"}
DELETE /tidal_goodies/favorites/albums/<id>
```

Same shape for `tracks`, `artists`, `playlists`. The `id` is the Tidal numeric
id — for an album whose Mopidy URI is `tidal:album:12345`, send `"12345"`.

Responses:
- `GET` → `200` with JSON array of `{id, name, artist?}` summaries.
- `POST`/`DELETE` → `204` on success.
- `503` if `mopidy-tidal` isn't loaded or isn't logged in.

### Stats

Listening history captured on every `track_playback_ended` event from any
Mopidy backend (Tidal, local, file, podcast, ...). Stored in SQLite under
`<mopidy data_dir>/tidal_goodies/history.db`.

```
GET    /tidal_goodies/stats/recent?limit=50
GET    /tidal_goodies/stats/most-played?limit=50&since=<unix>
GET    /tidal_goodies/stats/totals
```

A play is marked `completed` if it ran ≥50% of the track length OR ≥4 minutes
(Last.fm-style scrobble rule).

## Roadmap

- **v0.1** — favorites.
- **v0.2** — listening history / stats. *(current)*
- **v0.3** — mutable Tidal playlists (create / add / remove / reorder).
- **v0.4** — discovery: Your Mixes, mood radios.
- **v0.5** — admin: force session refresh, cache stats.

## License

Apache 2.0 — see [LICENSE](LICENSE).
