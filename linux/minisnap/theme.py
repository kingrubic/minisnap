"""Look and feel: CSS for the big coloured buttons, the capture overlay, the mode bar and the
recording bar. Light/dark follows Adw.StyleManager (libadwaita 1.5 has no CSS media queries,
so a small extra stylesheet is swapped when the scheme changes)."""

import os

from . import _gi  # noqa: F401
from gi.repository import Adw, Gdk, Gtk

# Same colours as windows/src (EditorForm big buttons, CaptureOverlay bar).
BLUE = (25, 110, 225)
GREEN = (30, 145, 75)
GRAY = (75, 85, 99)
BAR_GRAY = (70, 72, 80)
RED = (232, 38, 38)
PURPLE = (150, 70, 200)
TEAL = (0, 135, 145)
ORANGE = (235, 100, 30)
ACCENT = (255, 120, 30)   # overlay selection frame

BASE_CSS = """
.ms-big-button {
  border-radius: 9px;
  padding: 6px 16px;
  min-height: 42px;
  font-weight: bold;
  color: white;
  background-image: none;
  box-shadow: none;
}
.ms-big-button label { color: white; }
.ms-big-button:disabled { opacity: 0.55; }
.ms-launch-button { min-height: 58px; padding: 8px 14px; border-radius: 12px; }
.ms-launch-button label { font-size: 1.05em; }

.ms-blue { background-color: rgb(25,110,225); }
.ms-blue:hover { background-color: rgb(70,145,235); }
.ms-blue:active { background-color: rgb(22,99,202); }
.ms-green { background-color: rgb(30,145,75); }
.ms-green:hover { background-color: rgb(75,170,110); }
.ms-green:active { background-color: rgb(27,130,67); }
.ms-gray { background-color: rgb(75,85,99); }
.ms-gray:hover { background-color: rgb(110,119,131); }
.ms-gray:active { background-color: rgb(67,76,89); }
.ms-red { background-color: rgb(215,45,45); }
.ms-red:hover { background-color: rgb(228,90,90); }
.ms-red:active { background-color: rgb(193,40,40); }
.ms-purple { background-color: rgb(140,65,190); }
.ms-purple:hover { background-color: rgb(165,105,205); }
.ms-purple:active { background-color: rgb(126,58,171); }
.ms-teal { background-color: rgb(0,135,145); }
.ms-teal:hover { background-color: rgb(50,160,168); }
.ms-teal:active { background-color: rgb(0,121,130); }
.ms-orange { background-color: rgb(235,100,30); }
.ms-orange:hover { background-color: rgb(240,135,80); }
.ms-orange:active { background-color: rgb(211,90,27); }

/* Editor tool buttons: icon above a small caption, like the Windows toolbar. */
.ms-tool-button { padding: 3px 6px; min-width: 52px; }
.ms-tool-button label { font-size: 0.85em; }
.ms-tool-button:checked { background-color: alpha(@accent_bg_color, 0.20); }
.ms-tool-row { padding: 4px 8px; }
.ms-props-row { padding: 2px 8px; }
.ms-props-row > label { margin-left: 4px; margin-right: 2px; }
.ms-swatch { padding: 2px; min-width: 26px; min-height: 26px; }
.ms-statusbar { padding: 3px 10px; font-size: 0.9em; }
.ms-statusbar label { opacity: 0.85; }
.ms-zoom-label { min-width: 46px; }

/* Capture overlay */
.ms-overlay { background-color: black; }
.ms-modebar {
  background-color: rgb(34,35,40);
  border-radius: 8px;
  padding: 5px;
}
.ms-modebar label { color: silver; font-size: 1.1em; }
.ms-bar-button {
  min-width: 42px;
  min-height: 42px;
  padding: 0;
  margin: 3px;
  border-radius: 6px;
  color: white;
  background-image: none;
  box-shadow: none;
}
.ms-bar-blue { background-color: rgb(25,110,225); }
.ms-bar-blue:hover { background-color: rgb(70,145,235); }
.ms-bar-blue:disabled { background-color: rgb(25,110,225); opacity: 0.4; }
.ms-bar-gray { background-color: rgb(70,72,80); }
.ms-bar-gray:hover { background-color: rgb(107,109,116); }
entry.ms-size-entry {
  background-color: rgb(58,60,66);
  color: white;
  min-width: 58px;
  margin: 8px 3px;
  font-size: 1.05em;
}

/* Recording bar, scrolling-capture status */
.ms-floatbar { background-color: rgb(32,32,36); color: white; padding: 6px; }
.ms-float-button {
  background-color: rgb(240,240,242);
  color: rgb(30,30,30);
  background-image: none;
  margin: 4px;
}
.ms-float-button label { color: rgb(30,30,30); }
.ms-float-button:hover { background-color: white; }
.ms-rec-time { font-weight: bold; font-size: 1.25em; color: white; margin: 0 10px 0 8px; }
.ms-rec-live { color: rgb(255,90,90); }
.ms-rec-paused { color: gold; }
.ms-scroll-status { color: white; font-weight: bold; margin: 0 10px 0 8px; }

/* OCR / update text areas */
.ms-ocr-text { font-size: 1.1em; }
.ms-update-title { font-size: 1.35em; font-weight: bold; }
.ms-command { font-family: monospace; }
"""

LIGHT_CSS = """
.ms-thumb-caption { color: rgb(60,60,66); }
"""

DARK_CSS = """
.ms-thumb-caption { color: rgb(220,220,224); }
"""

_installed = False
_scheme_provider = None


def _load(provider, text):
    if hasattr(provider, "load_from_string"):   # GTK 4.12+
        provider.load_from_string(text)
    else:
        provider.load_from_data(text, -1)


def is_dark():
    try:
        return Adw.StyleManager.get_default().get_dark()
    except Exception:  # noqa: BLE001 - before Adw.init()
        return False


def install():
    """Adds the stylesheets to the default display (once) and the bundled icon to the icon theme."""
    global _installed, _scheme_provider
    if _installed:
        return
    display = Gdk.Display.get_default()
    if display is None:
        return
    _installed = True
    base = Gtk.CssProvider()
    _load(base, BASE_CSS)
    Gtk.StyleContext.add_provider_for_display(display, base, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _scheme_provider = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(display, _scheme_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    sm = Adw.StyleManager.get_default()
    sm.connect("notify::dark", lambda *_: _apply_scheme())
    _apply_scheme()

    # Running from the source tree: the app icon is not installed in the icon theme yet.
    icons = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "icons")
    if os.path.isdir(icons):
        Gtk.IconTheme.get_for_display(display).add_search_path(icons)


def _apply_scheme():
    if _scheme_provider is not None:
        _load(_scheme_provider, DARK_CSS if is_dark() else LIGHT_CSS)


def canvas_rgb():
    """Editor background around the image (Windows Theme.Canvas)."""
    return (24 / 255, 24 / 255, 24 / 255) if is_dark() else (229 / 255, 229 / 255, 229 / 255)


def surface_rgb():
    """Card / placeholder colour (Windows Theme.Surface or the light thumbnail grey)."""
    return (43 / 255, 43 / 255, 43 / 255) if is_dark() else (232 / 255, 232 / 255, 236 / 255)


def ink_rgb():
    """Default glyph colour (Windows Icons.Ink)."""
    return (232, 232, 232) if is_dark() else (50, 50, 56)


def new_provider(display=None):
    """A separate provider (used for per-widget rules such as the editor's text box font)."""
    display = display or Gdk.Display.get_default()
    p = Gtk.CssProvider()
    Gtk.StyleContext.add_provider_for_display(display, p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 2)
    return p


def set_provider_css(provider, text):
    _load(provider, text)


def remove_provider(provider, display=None):
    display = display or Gdk.Display.get_default()
    try:
        Gtk.StyleContext.remove_provider_for_display(display, provider)
    except Exception:  # noqa: BLE001
        pass
