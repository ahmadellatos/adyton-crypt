"""Tes mesin tema (dark/light) di ui/styles.py — murni logika, tanpa qtbot."""

import pytest

pytest.importorskip("PySide6")

import ui.styles as styles


@pytest.fixture(autouse=True)
def _restore_dark():
    """Kembalikan ke dark setelah tiap tes (state token bersifat module-global)."""
    yield
    styles.set_active_theme("dark")


def test_palette_key_parity():
    # Tiap token light WAJIB punya pasangan dark senama (cegah drift/typo).
    assert set(styles._DARK) == set(styles._LIGHT)
    assert len(styles._DARK) > 40


def test_set_active_theme_swaps_tokens():
    styles.set_active_theme("light")
    assert styles.ACTIVE_THEME == "light"
    assert styles.IS_LIGHT is True
    assert styles.CLR_CARD == "#FFFFFF"
    assert styles.CLR_ACCENT == "#149AA6"  # teal lebih dalam
    assert styles.CLR_ON_ACCENT == "#FFFFFF"

    styles.set_active_theme("dark")
    assert styles.ACTIVE_THEME == "dark"
    assert styles.IS_LIGHT is False
    assert styles.CLR_CARD == "#1B2F36"
    assert styles.CLR_ACCENT == "#4FBFC9"


def test_cta_track_dark_in_both_themes():
    # Track progress harus gelap di KEDUA tema agar teks putih CTA tetap terbaca.
    styles.set_active_theme("light")
    assert styles.CLR_CTA_TRACK == "#3C5A60"
    styles.set_active_theme("dark")
    assert styles.CLR_CTA_TRACK == "#13242A"


def test_resolve_theme_passthrough():
    assert styles.resolve_theme("dark") == "dark"
    assert styles.resolve_theme("light") == "light"
    assert styles.resolve_theme("system") in ("dark", "light")
    assert styles.resolve_theme("garbage") == "dark"  # fallback aman


def test_overlay_color_follows_theme():
    styles.set_active_theme("light")
    assert styles.overlay_color(16).getRgb() == (15, 45, 51, 16)  # wash gelap di light
    styles.set_active_theme("dark")
    assert styles.overlay_color(16).getRgb() == (255, 255, 255, 16)  # wash putih di dark


def test_accent_color_follows_theme():
    styles.set_active_theme("light")
    assert styles.accent_color(30).getRgb() == (20, 154, 166, 30)
    styles.set_active_theme("dark")
    assert styles.accent_color(30).getRgb() == (79, 191, 201, 30)


def test_load_stylesheet_reflects_active_palette():
    styles.set_active_theme("light")
    qss_light = styles.load_stylesheet()
    assert "#FFFFFF" in qss_light  # kartu putih
    assert "#1B2F36" not in qss_light  # tak ada permukaan dark

    styles.set_active_theme("dark")
    qss_dark = styles.load_stylesheet()
    assert "#1B2F36" in qss_dark
