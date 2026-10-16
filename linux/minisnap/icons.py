"""Toolbar glyphs drawn in code on a 24x24 grid (port of windows/src/Icons.cs), so the app looks
the same whatever icon theme is installed. Glyph widgets are DrawingAreas, so they stay sharp
at any display scale."""

import math

import cairo

from . import _gi  # noqa: F401
from gi.repository import Gtk, Pango, PangoCairo

from . import theme

RED = (232, 38, 38)
BLUE = (30, 120, 230)
GREEN = (40, 170, 70)
PURPLE = (150, 70, 200)
YELLOW = (255, 214, 0)


def _c(cr, rgb, alpha=255):
    cr.set_source_rgba(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, alpha / 255.0)


def rounded_rect(cr, x, y, w, h, r):
    """Adds a rounded rectangle path (Icons.RoundedRect)."""
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def ellipse(cr, x, y, w, h):
    cr.save()
    cr.translate(x + w / 2.0, y + h / 2.0)
    cr.scale(max(w, 0.01) / 2.0, max(h, 0.01) / 2.0)
    cr.new_sub_path()
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.restore()


def _round_pen(cr, width):
    cr.set_line_width(width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)


def _lines(cr, pts):
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)


def draw_play_badge(cr, x, y, w, h):
    """Round "play" badge drawn over video thumbnails."""
    d = min(w, h) * 0.34
    rx, ry = x + (w - d) / 2.0, y + (h - d) / 2.0
    ellipse(cr, rx, ry, d, d)
    cr.set_source_rgba(0, 0, 0, 170 / 255.0)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 230 / 255.0)
    cr.set_line_width(max(1.5, d / 18.0))
    cr.stroke()
    t, cx, cy = d * 0.22, rx + d * 0.54, ry + d / 2.0
    cr.move_to(cx - t * 0.8, cy - t)
    cr.line_to(cx - t * 0.8, cy + t)
    cr.line_to(cx + t, cy)
    cr.close_path()
    cr.set_source_rgb(1, 1, 1)
    cr.fill()


def draw_app_icon(cr, size):
    """The MiniSnap logo (Icons.cs AppIcon): orange to pink rounded square, white crop corners and dot."""
    cr.save()
    cr.scale(size / 32.0, size / 32.0)
    rounded_rect(cr, 1, 1, 30, 30, 7)
    grad = cairo.LinearGradient(0, 0, 32, 32)
    grad.add_color_stop_rgb(0, 255 / 255.0, 110 / 255.0, 50 / 255.0)
    grad.add_color_stop_rgb(1, 225 / 255.0, 40 / 255.0, 85 / 255.0)
    cr.set_source(grad)
    cr.fill()
    cr.set_source_rgb(1, 1, 1)
    _round_pen(cr, 3)
    _lines(cr, [(8, 15), (8, 8), (15, 8)])
    cr.stroke()
    _lines(cr, [(17, 24), (24, 24), (24, 17)])
    cr.stroke()
    ellipse(cr, 13, 13, 6, 6)
    cr.fill()
    cr.restore()


def draw_glyph(cr, kind, ink, paper=(255, 255, 255), mono=False):
    """Draws glyph `kind` on the 24x24 grid. ink/paper are (r,g,b) 0-255; mono paints the coloured
    accents in ink too (used on the coloured launcher buttons)."""
    def accent(c):
        return ink if mono else c

    _round_pen(cr, 2)
    _c(cr, ink)

    if kind == "select":
        pts = [(6, 3), (6, 19), (10, 15.5), (13, 21.5), (15.8, 20.2), (12.8, 14.2), (18, 14)]
        _lines(cr, pts)
        cr.close_path()
        cr.set_source_rgb(1, 1, 1)
        cr.fill_preserve()
        _c(cr, theme.ink_rgb() if not mono else ink)
        cr.set_line_width(1.6)
        cr.stroke()
    elif kind == "arrow":
        from .shapes import ArrowShape  # local import: shapes imports nothing from here
        ArrowShape(a=(4, 20), b=(21, 3), color=accent(RED), width=3).draw(cr)
    elif kind == "rect":
        _c(cr, accent(RED))
        cr.set_line_width(2.2)
        cr.rectangle(3.5, 5.5, 17, 13)
        cr.stroke()
    elif kind == "ellipse":
        _c(cr, accent(BLUE))
        cr.set_line_width(2.2)
        ellipse(cr, 2.5, 5.5, 19, 13)
        cr.stroke()
    elif kind == "line":
        _c(cr, accent(GREEN))
        _round_pen(cr, 2.6)
        _lines(cr, [(4, 19), (20, 5)])
        cr.stroke()
    elif kind == "pen":
        _c(cr, accent(PURPLE))
        _round_pen(cr, 2.4)
        cr.move_to(3, 17)
        cr.curve_to(8, 2, 13, 24, 21, 6)
        cr.stroke()
    elif kind == "highlight":
        _c(cr, accent(YELLOW), 200 if not mono else 120)
        cr.rectangle(2, 8, 20, 8)
        cr.fill()
        _c(cr, ink)
        _lines(cr, [(4, 12), (20, 12)])
        cr.stroke()
    elif kind == "text":
        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.from_string("Sans Bold")
        desc.set_absolute_size(19 * Pango.SCALE)
        layout.set_font_description(desc)
        layout.set_text("T", -1)
        ink_r, _ = layout.get_pixel_extents()
        cr.move_to(12 - ink_r.x - ink_r.width / 2.0, 12.5 - ink_r.y - ink_r.height / 2.0)
        PangoCairo.show_layout(cr, layout)
    elif kind == "blur":
        for y in range(4):
            for x in range(4):
                v = 110 + ((x * 37 + y * 53) % 4) * 35
                _c(cr, (v, v, min(255, v + 10)) if not mono else ink, 255 if not mono else 60 + v // 3)
                cr.rectangle(4 + x * 4, 4 + y * 4, 4, 4)
                cr.fill()
        _c(cr, theme.ink_rgb() if not mono else ink)
        cr.set_line_width(1.2)
        cr.rectangle(4, 4, 16, 16)
        cr.stroke()
    elif kind == "step":
        from .shapes import StepShape
        StepShape(center=(12, 12), number=1, color=accent(RED), width=0.5).draw(cr)
    elif kind == "crop":
        _lines(cr, [(7, 2), (7, 17), (22, 17)])
        cr.stroke()
        _lines(cr, [(2, 7), (17, 7), (17, 22)])
        cr.stroke()
    elif kind == "capture":
        _c(cr, accent(RED))
        cr.set_dash([2.0 * 2, 1.2 * 2])
        cr.set_line_cap(cairo.LINE_CAP_BUTT)
        cr.rectangle(3, 5, 18, 14)
        cr.stroke()
        cr.set_dash([])
        _round_pen(cr, 2)
        _c(cr, ink)
        _lines(cr, [(12, 9), (12, 15)])
        cr.stroke()
        _lines(cr, [(9, 12), (15, 12)])
        cr.stroke()
    elif kind == "fullscreen":
        rounded_rect(cr, 2.5, 4.5, 19, 13, 2)
        cr.stroke()
        _lines(cr, [(8, 20.5), (16, 20.5)])
        cr.stroke()
        _round_pen(cr, 1.6)
        _lines(cr, [(5.5, 10), (5.5, 7.5), (8, 7.5)])
        cr.stroke()
        _lines(cr, [(16, 14.5), (18.5, 14.5), (18.5, 12)])
        cr.stroke()
    elif kind == "timer":
        ellipse(cr, 4, 5, 16, 16)
        cr.stroke()
        _lines(cr, [(12, 13), (12, 8.5)])
        cr.stroke()
        _lines(cr, [(12, 13), (15, 15)])
        cr.stroke()
        _lines(cr, [(9.5, 2.5), (14.5, 2.5)])
        cr.stroke()
    elif kind == "window":
        rounded_rect(cr, 3, 4, 18, 16, 2.5)
        cr.stroke()
        _lines(cr, [(3, 8.5), (21, 8.5)])
        cr.stroke()
        _c(cr, accent(RED))
        ellipse(cr, 5, 5.3, 2, 2)
        cr.fill()
    elif kind in ("undo", "redo"):
        cr.save()
        if kind == "redo":
            cr.translate(24, 0)
            cr.scale(-1, 1)
        cr.move_to(19, 19)
        cr.curve_to(20, 9, 13, 7, 6, 9)
        cr.stroke()
        _lines(cr, [(9, 4.5), (5, 9), (10, 12.5)])
        cr.stroke()
        cr.restore()
    elif kind == "copy":
        rounded_rect(cr, 8, 3, 12, 14, 2)
        cr.stroke()
        rounded_rect(cr, 4, 7, 12, 14, 2)
        _c(cr, paper)
        cr.fill_preserve()
        _c(cr, ink)
        cr.stroke()
    elif kind in ("save", "saveas"):
        rounded_rect(cr, 3.5, 3.5, 17, 17, 2)
        cr.stroke()
        cr.rectangle(8, 3.5, 8, 5)
        cr.stroke()
        cr.rectangle(7, 13, 10, 7.5)
        cr.stroke()
        if kind == "saveas":
            _c(cr, accent(BLUE) if not mono else paper)
            ellipse(cr, 13, 12, 11, 11)
            cr.fill()
            _c(cr, (255, 255, 255) if not mono else ink)
            _round_pen(cr, 1.8)
            _lines(cr, [(18.5, 14.5), (18.5, 20.5)])
            cr.stroke()
            _lines(cr, [(15.5, 17.5), (21.5, 17.5)])
            cr.stroke()
    elif kind in ("folder", "open"):
        pts = [(2.5, 6), (9, 6), (11, 8.5), (21.5, 8.5), (21.5, 19.5), (2.5, 19.5)]
        _lines(cr, pts)
        cr.close_path()
        if mono:
            cr.set_line_width(1.8)
            cr.stroke()
        else:
            _c(cr, (255, 200, 70))
            cr.fill_preserve()
            _c(cr, (190, 140, 20))
            cr.set_line_width(1.5)
            cr.stroke()
    elif kind == "ocr":
        for pts in ([(3, 8), (3, 3), (8, 3)], [(16, 3), (21, 3), (21, 8)],
                    [(3, 16), (3, 21), (8, 21)], [(16, 21), (21, 21), (21, 16)]):
            _lines(cr, pts)
            cr.stroke()
        _c(cr, accent(BLUE))
        _round_pen(cr, 2.2)
        _lines(cr, [(8, 8.5), (16, 8.5)])
        cr.stroke()
        _lines(cr, [(12, 8.5), (12, 16.5)])
        cr.stroke()
    elif kind == "library":
        _c(cr, accent(BLUE))
        for (x, y) in ((3, 3), (13, 3), (3, 13), (13, 13)):
            rounded_rect(cr, x, y, 8, 8, 2)
            cr.fill()
    elif kind == "video":
        rounded_rect(cr, 2.5, 6, 13, 12, 2.5)
        cr.stroke()
        _lines(cr, [(15.5, 10.5), (21.5, 7), (21.5, 17), (15.5, 13.5)])
        cr.close_path()
        cr.stroke()
        _c(cr, accent(RED))
        ellipse(cr, 6, 9.5, 5, 5)
        cr.fill()
    elif kind == "update":
        _lines(cr, [(12, 3), (12, 15)])
        cr.stroke()
        _lines(cr, [(7, 10.5), (12, 15.5), (17, 10.5)])
        cr.stroke()
        _lines(cr, [(5, 20.5), (19, 20.5)])
        cr.stroke()
    elif kind == "info":
        ellipse(cr, 3, 3, 18, 18)
        cr.stroke()
        _lines(cr, [(12, 11), (12, 17)])
        cr.stroke()
        ellipse(cr, 10.8, 6.6, 2.4, 2.4)
        cr.fill()
    elif kind == "camera":
        rounded_rect(cr, 2.5, 7, 19, 13, 3)
        cr.stroke()
        _lines(cr, [(8, 7), (9.5, 4.5), (14.5, 4.5), (16, 7)])
        cr.stroke()
        ellipse(cr, 8.5, 9.5, 7, 7)
        cr.stroke()
    elif kind == "close":
        _round_pen(cr, 2.4)
        _lines(cr, [(6.5, 6.5), (17.5, 17.5)])
        cr.stroke()
        _lines(cr, [(17.5, 6.5), (6.5, 17.5)])
        cr.stroke()
    elif kind == "scroll":
        rounded_rect(cr, 5, 2.5, 14, 19, 2)
        cr.stroke()
        _c(cr, accent(BLUE))
        _round_pen(cr, 2.2)
        _lines(cr, [(12, 6.5), (12, 16)])
        cr.stroke()
        _lines(cr, [(8.5, 12.5), (12, 16), (15.5, 12.5)])
        cr.stroke()
    elif kind == "record":
        _c(cr, accent(RED))
        ellipse(cr, 5, 5, 14, 14)
        cr.fill()
    elif kind == "pause":
        cr.rectangle(6, 5, 4, 14)
        cr.rectangle(14, 5, 4, 14)
        cr.fill()
    elif kind == "stop":
        rounded_rect(cr, 5.5, 5.5, 13, 13, 2)
        cr.fill()
    elif kind == "refresh":
        cr.new_sub_path()
        cr.arc(12, 12, 7.5, math.radians(-60), math.radians(240))
        cr.stroke()
        _lines(cr, [(15, 2.5), (16.5, 6), (13, 7.5)])
        cr.stroke()
    elif kind == "globe":
        _c(cr, accent(BLUE))
        cr.set_line_width(1.8)
        ellipse(cr, 3, 3, 18, 18)
        cr.stroke()
        ellipse(cr, 8, 3, 8, 18)
        cr.stroke()
        for (a, b) in (((3, 12), (21, 12)), ((4.5, 7.5), (19.5, 7.5)), ((4.5, 16.5), (19.5, 16.5))):
            _lines(cr, [a, b])
            cr.stroke()
    elif kind == "keyboard":
        rounded_rect(cr, 2, 6, 20, 13, 2.5)
        cr.stroke()
        for i in range(4):
            cr.rectangle(5 + i * 4, 9.2, 2, 2)
            cr.rectangle(5 + i * 4, 12.2, 2, 2)
        cr.fill()
        _lines(cr, [(8, 16), (16, 16)])
        cr.stroke()
    elif kind == "delete":
        _lines(cr, [(4, 6.5), (20, 6.5)])
        cr.stroke()
        _lines(cr, [(9, 6.5), (9.5, 3.5), (14.5, 3.5), (15, 6.5)])
        cr.stroke()
        _lines(cr, [(6, 6.5), (7.5, 20.5), (16.5, 20.5), (18, 6.5)])
        cr.close_path()
        cr.stroke()
    elif kind == "zoomin" or kind == "zoomout":
        ellipse(cr, 3, 3, 14, 14)
        cr.stroke()
        _lines(cr, [(15, 15), (21, 21)])
        cr.stroke()
        _lines(cr, [(7, 10), (13, 10)])
        cr.stroke()
        if kind == "zoomin":
            _lines(cr, [(10, 7), (10, 13)])
            cr.stroke()


class Glyph(Gtk.DrawingArea):
    """A glyph as a widget. ink None = follow the widget's CSS colour (light/dark aware)."""

    def __init__(self, kind, size=24, ink=None, paper=None, mono=False):
        super().__init__()
        self.kind = kind
        self.ink = ink
        self.paper = paper
        self.mono = mono
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_can_target(False)
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_draw_func(self._draw)

    def set_kind(self, kind):
        self.kind = kind
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        ink = self.ink
        if ink is None:
            try:
                c = self.get_color()   # GTK 4.10+
                ink = (int(c.red * 255), int(c.green * 255), int(c.blue * 255))
            except Exception:  # noqa: BLE001
                ink = theme.ink_rgb()
        paper = self.paper or (tuple(int(v * 255) for v in theme.surface_rgb()) if theme.is_dark() else (255, 255, 255))
        cr.scale(w / 24.0, h / 24.0)
        draw_glyph(cr, self.kind, ink, paper, self.mono)


class AppLogo(Gtk.DrawingArea):
    def __init__(self, size=64):
        super().__init__()
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(lambda a, cr, w, h: draw_app_icon(cr, min(w, h)))


class Swatch(Gtk.DrawingArea):
    """Colour swatch for the editor palette; `ring` marks the current colour (Icons.Swatch)."""

    def __init__(self, rgb, size=20):
        super().__init__()
        self.rgb = rgb
        self.ring = False
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_can_target(False)
        self.set_draw_func(self._draw)

    def update(self, rgb=None, ring=None):
        if rgb is not None:
            self.rgb = rgb
        if ring is not None:
            self.ring = ring
        self.queue_draw()

    def _draw(self, area, cr, w, h):
        size = float(min(w, h))
        inset = size * 0.14
        rounded_rect(cr, inset, inset, size - 2 * inset, size - 2 * inset, size * 0.18)
        _c(cr, self.rgb)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 120 / 255.0)
        cr.set_line_width(1)
        cr.stroke()
        if self.ring:
            try:
                c = self.get_color()
                cr.set_source_rgba(c.red, c.green, c.blue, 1)
            except Exception:  # noqa: BLE001
                _c(cr, theme.ink_rgb())
            cr.set_line_width(max(1.5, size / 12.0))
            rounded_rect(cr, 1, 1, size - 2, size - 2, size * 0.22)
            cr.stroke()
