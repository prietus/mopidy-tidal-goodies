"""HTTP endpoints exposed by mopidy-tidal-goodies.

Routes mounted under ``/tidal_goodies/`` (Mopidy http convention takes the
ext_name as prefix). Examples:

    POST   /tidal_goodies/favorites/albums      { "id": "12345" }
    DELETE /tidal_goodies/favorites/albums/12345
    GET    /tidal_goodies/favorites/albums

All endpoints reuse the authenticated tidalapi.Session that mopidy-tidal has
already loaded — clients don't need to hold any Tidal credentials.
"""
import json
import logging

from tornado.web import HTTPError, RequestHandler

from .tidal import TidalUnavailable, get_session

logger = logging.getLogger(__name__)

# Tidal entity kinds we expose. Each must map to:
#   - tidalapi.Favorites methods named add_<kind>, remove_<kind>, <kind>s
KINDS = ("album", "track", "artist", "playlist")


def factory(config, core):
    return [
        (
            r"/favorites/(album|track|artist|playlist)s",
            FavoritesCollectionHandler,
            {"core": core},
        ),
        (
            r"/favorites/(album|track|artist|playlist)s/([^/]+)",
            FavoritesItemHandler,
            {"core": core},
        ),
    ]


class _Base(RequestHandler):
    def initialize(self, core):
        self.core = core

    def write_error(self, status_code, **kwargs):
        self.set_header("Content-Type", "application/json")
        msg = self._reason
        # Tornado stores our HTTPError reason; surface it to clients as JSON.
        self.finish(json.dumps({"error": msg}))

    def _session(self):
        try:
            return get_session(self.core)
        except TidalUnavailable as e:
            raise HTTPError(503, reason=str(e))


class FavoritesCollectionHandler(_Base):
    def get(self, kind):
        session = self._session()
        items = getattr(session.user.favorites, f"{kind}s")()
        self.set_header("Content-Type", "application/json")
        self.write(json.dumps([_summarize(kind, x) for x in items]))

    def post(self, kind):
        session = self._session()
        try:
            body = json.loads(self.request.body or b"{}")
        except json.JSONDecodeError as e:
            raise HTTPError(400, reason=f"invalid JSON: {e}")
        item_id = body.get("id")
        if not item_id:
            raise HTTPError(400, reason="missing 'id' in body")
        getattr(session.user.favorites, f"add_{kind}")(item_id)
        self.set_status(204)


class FavoritesItemHandler(_Base):
    def delete(self, kind, item_id):
        session = self._session()
        getattr(session.user.favorites, f"remove_{kind}")(item_id)
        self.set_status(204)


def _summarize(kind, x):
    """Tidalapi objects don't JSON-serialize cleanly; pull a small summary."""
    summary = {"id": str(getattr(x, "id", ""))}
    name = getattr(x, "name", None)
    if name:
        summary["name"] = name
    artist = getattr(x, "artist", None)
    if artist is not None:
        summary["artist"] = getattr(artist, "name", None)
    return summary
