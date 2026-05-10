"""Bridge to mopidy-tidal's authenticated session.

mopidy-tidal doesn't expose its tidalapi.Session via a public API; we reach
into the backend actor. Across mopidy-tidal versions the session attribute has
been named differently — probe known names in order.

Pykka note: Mopidy backends are actors. ``core.backends`` returns a list of
backend ActorRefs. To read attributes from a different thread we go through
``ref.proxy()`` which marshals attribute access into actor messages.
"""
import logging

logger = logging.getLogger(__name__)

# Attribute names the tidalapi.Session has lived under in different
# mopidy-tidal releases. Probed in order; first one whose `.user` is non-None
# wins.
_SESSION_ATTRS = ("_active_session", "_session", "session")


class TidalUnavailable(RuntimeError):
    """Raised when mopidy-tidal isn't loaded, isn't logged in, or the session
    attribute can't be located."""


def get_session(core):
    backend = _find_tidal_backend(core)
    if backend is None:
        raise TidalUnavailable("mopidy-tidal backend not loaded")
    proxy = backend.proxy() if hasattr(backend, "proxy") else backend
    for attr in _SESSION_ATTRS:
        try:
            session = _resolve(getattr(proxy, attr, None))
        except Exception:
            continue
        if session is not None and getattr(session, "user", None) is not None:
            return session
    raise TidalUnavailable(
        f"mopidy-tidal backend found but no session attribute matched "
        f"({_SESSION_ATTRS}); is the user logged in?"
    )


def _find_tidal_backend(core):
    backends = _resolve(core.backends)
    if not backends:
        return None
    for b in backends:
        try:
            schemes = _resolve(b.uri_schemes if not hasattr(b, "proxy") else b.proxy().uri_schemes)
        except Exception:
            continue
        if schemes and "tidal" in schemes:
            return b
    return None


def _resolve(value):
    """Resolve a Pykka future if it is one, otherwise pass through."""
    get = getattr(value, "get", None)
    if callable(get):
        return get()
    return value
