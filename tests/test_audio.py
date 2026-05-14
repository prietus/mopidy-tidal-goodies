"""Unit tests for :mod:`mopidy_tidal_goodies.audio` — pure-function logic,
no Mopidy required."""
from pathlib import Path

import pytest

from mopidy_tidal_goodies import audio


# Realistic /proc/asound/cards content from a Mopidy box with onboard HDA +
# a Topping D90 III SABRE plugged in over USB.
CARDS_FIXTURE = """\
 0 [PCH            ]: HDA-Intel - HDA Intel PCH
                      HDA Intel PCH at 0xf0700000 irq 130
 1 [D90III         ]: USB-Audio - Topping D90 III SABRE
                      Topping D90 III SABRE at usb-0000:00:14.0-3, high speed
"""


@pytest.fixture
def cards(tmp_path):
    p = tmp_path / "cards"
    p.write_text(CARDS_FIXTURE)
    return p


# ── _parse_bin ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spec,expected_sink,expected_params",
    [
        ("alsasink device=hw:1,0", "alsasink", {"device": "hw:1,0"}),
        ("alsasink", "alsasink", {}),
        ("  alsasink   device=hw:Topping  ", "alsasink", {"device": "hw:Topping"}),
        ("pulsesink", "pulsesink", {}),
        ("pipewiresink target-object=Topping", "pipewiresink", {"target-object": "Topping"}),
        ('alsasink device="hw:1,0"', "alsasink", {"device": "hw:1,0"}),
        ("alsasink device=hw:1,0 sync=false", "alsasink", {"device": "hw:1,0", "sync": "false"}),
        ("alsasink device=hw:1,0 ! fakesink", "alsasink", {"device": "hw:1,0"}),
        ("", None, {}),
        ("   ", None, {}),
    ],
)
def test_parse_bin(spec, expected_sink, expected_params):
    sink, params = audio._parse_bin(spec)
    assert sink == expected_sink
    assert params == expected_params


# ── _alsa_target ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "device,expected",
    [
        ("hw:1,0", "1"),
        ("hw:1", "1"),
        ("hw:Topping", "Topping"),
        ("plughw:1,0", "1"),
        ("plughw:Topping", "Topping"),
        ("hw:CARD=D90III,DEV=0", "D90III"),
        ("default:CARD=D90III", "D90III"),
        ("default", None),
        ("", None),
    ],
)
def test_alsa_target(device, expected):
    assert audio._alsa_target(device) == expected


# ── _read_cards ────────────────────────────────────────────────────────────


def test_read_cards_parses_proc(cards):
    parsed = audio._read_cards(cards)
    assert parsed == {
        0: {"index": 0, "id": "PCH", "name": "HDA Intel PCH"},
        1: {"index": 1, "id": "D90III", "name": "Topping D90 III SABRE"},
    }


def test_read_cards_missing_file_is_empty(tmp_path):
    assert audio._read_cards(tmp_path / "nope") == {}


# ── _resolve_alsa_card ─────────────────────────────────────────────────────


def test_resolve_by_index(cards):
    assert audio._resolve_alsa_card("hw:1,0", cards) == {
        "index": 1, "id": "D90III", "name": "Topping D90 III SABRE",
    }


def test_resolve_by_id(cards):
    assert audio._resolve_alsa_card("hw:D90III", cards) == {
        "index": 1, "id": "D90III", "name": "Topping D90 III SABRE",
    }


def test_resolve_plughw(cards):
    assert audio._resolve_alsa_card("plughw:0,0", cards) == {
        "index": 0, "id": "PCH", "name": "HDA Intel PCH",
    }


def test_resolve_card_form(cards):
    assert audio._resolve_alsa_card("hw:CARD=D90III,DEV=0", cards) == {
        "index": 1, "id": "D90III", "name": "Topping D90 III SABRE",
    }


def test_resolve_unknown_returns_none(cards):
    assert audio._resolve_alsa_card("hw:99", cards) is None
    assert audio._resolve_alsa_card("hw:DoesNotExist", cards) is None


def test_resolve_default_returns_none(cards):
    assert audio._resolve_alsa_card("default", cards) is None


def test_resolve_missing_proc_returns_none(tmp_path):
    assert audio._resolve_alsa_card("hw:1,0", tmp_path / "missing") is None


# ── describe (end-to-end) ──────────────────────────────────────────────────


def test_describe_alsasink_resolves_card(cards):
    info = audio.describe({"output": "alsasink device=hw:1,0"}, cards_path=cards)
    assert info == {
        "sink": "alsasink",
        "device": "hw:1,0",
        "card": {"index": 1, "id": "D90III", "name": "Topping D90 III SABRE"},
    }


def test_describe_alsasink_by_id(cards):
    info = audio.describe({"output": "alsasink device=hw:D90III"}, cards_path=cards)
    assert info["card"]["name"] == "Topping D90 III SABRE"


def test_describe_pulsesink_has_no_card(cards):
    info = audio.describe({"output": "pulsesink"}, cards_path=cards)
    assert info == {"sink": "pulsesink", "device": None, "card": None}


def test_describe_pipewire_passthrough(cards):
    info = audio.describe(
        {"output": "pipewiresink target-object=Topping"}, cards_path=cards
    )
    assert info["sink"] == "pipewiresink"
    assert info["device"] is None
    assert info["card"] is None


def test_describe_alsasink_default_device(cards):
    info = audio.describe({"output": "alsasink device=default"}, cards_path=cards)
    assert info == {"sink": "alsasink", "device": "default", "card": None}


def test_describe_no_config_returns_none(cards):
    assert audio.describe(None, cards_path=cards) is None
    assert audio.describe({}, cards_path=cards) is None
    assert audio.describe({"output": ""}, cards_path=cards) is None


def test_describe_unknown_card_keeps_device(cards):
    info = audio.describe({"output": "alsasink device=hw:42,0"}, cards_path=cards)
    assert info == {"sink": "alsasink", "device": "hw:42,0", "card": None}
