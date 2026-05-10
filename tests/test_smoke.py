"""Smoke tests — Extension class loads cleanly. Real handler tests need a
running Mopidy with mopidy-tidal authenticated, so they live as an integration
suite to be added later."""
from mopidy_tidal_goodies import Extension


def test_extension_metadata():
    ext = Extension()
    assert ext.dist_name == "Mopidy-Tidal-Goodies"
    assert ext.ext_name == "tidal_goodies"
    assert ext.version


def test_default_config_loads():
    ext = Extension()
    cfg = ext.get_default_config()
    assert "[tidal_goodies]" in cfg
    assert "enabled = true" in cfg
