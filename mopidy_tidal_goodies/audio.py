"""Resolve Mopidy's ``[audio] output`` to a human-readable device record.

Mopidy's ``output`` is a GStreamer bin spec — anything that ``gst-launch-1.0``
would accept as a sink. Common shapes:

    alsasink device=hw:1,0
    alsasink device=hw:CARD=D90III,DEV=0
    alsasink device=plughw:Topping
    pulsesink
    autoaudiosink
    pipewiresink target-object=Topping

For ``alsasink`` we extract the card and look it up in
``/proc/asound/cards``. For other sinks (or non-Linux hosts) we return what
we can parse and leave ``card`` as ``None`` so the client can fall back to
the raw device string.
"""
import logging
import re
import shlex
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CARDS_PATH = Path("/proc/asound/cards")


def describe(audio_config, cards_path=DEFAULT_CARDS_PATH):
    """Return ``{sink, device, card}`` for the configured output, or ``None``.

    ``audio_config`` is the ``config["audio"]`` dict Mopidy passes to the
    HTTP factory.
    """
    output = (audio_config or {}).get("output")
    if not output:
        return None
    sink, params = _parse_bin(output)
    if not sink:
        return None
    device = params.get("device")
    card = None
    if sink in ("alsasink", "alsasrc") and device:
        card = _resolve_alsa_card(device, cards_path)
    return {"sink": sink, "device": device, "card": card}


def _parse_bin(spec):
    """``alsasink device=hw:1,0 sync=false`` → (``alsasink``, ``{...}``).

    Only the leading element of the pipeline is inspected (i.e. text before
    the first ``!``). ``shlex`` handles quoted values like ``device="hw:1,0"``.
    """
    head = spec.strip().split("!", 1)[0].strip()
    if not head:
        return None, {}
    try:
        tokens = shlex.split(head, posix=True)
    except ValueError:
        return None, {}
    if not tokens:
        return None, {}
    sink = tokens[0]
    params = {}
    for tok in tokens[1:]:
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        params[k.strip()] = v.strip()
    return sink, params


# /proc/asound/cards first-line format:
#  1 [D90III         ]: USB-Audio - Topping D90 III SABRE
_CARDS_LINE = re.compile(
    r"^\s*(?P<index>\d+)\s*\[(?P<id>[^\]]+)\]\s*:\s*"
    r"(?P<kind>\S+)\s*-\s*(?P<longname>.+?)\s*$"
)


def _resolve_alsa_card(device, cards_path):
    """Map an ALSA device string to a ``{index, id, name}`` record.

    Accepts ``hw:N``, ``hw:N,M``, ``hw:CardID``, ``hw:CARD=CardID,DEV=N``,
    and the ``plughw:``/``default:`` variants. Returns ``None`` if the card
    can't be identified (e.g. ``default``, non-Linux, unparseable).
    """
    target = _alsa_target(device)
    if target is None:
        return None
    cards = _read_cards(cards_path)
    if not cards:
        return None
    if target.isdigit():
        return cards.get(int(target))
    for c in cards.values():
        if c["id"] == target:
            return c
    return None


def _alsa_target(device):
    """Strip ``hw:``/``plughw:``/``default:`` and pull the card portion.

    Returns ``None`` for plain ``default`` (no card binding) or empty.
    """
    rest = re.sub(r"^(plughw|hw|default):", "", device.strip(), count=1)
    if not rest or rest == "default":
        return None
    # CARD=X,DEV=Y form
    m = re.search(r"CARD=([^,]+)", rest)
    if m:
        return m.group(1).strip()
    # N,M or just N/CardID form
    return rest.split(",", 1)[0].strip() or None


def _read_cards(path):
    try:
        text = Path(path).read_text()
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        m = _CARDS_LINE.match(line)
        if not m:
            continue
        idx = int(m["index"])
        out[idx] = {
            "index": idx,
            "id": m["id"].strip(),
            "name": m["longname"].strip(),
        }
    return out
