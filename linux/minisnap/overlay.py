"""Full-screen frozen screenshot on which the user drags a region (port of windows/src/CaptureOverlay.cs).

One undecorated full-screen window per monitor shows that monitor's slice of the portal
screenshot, dimmed. With ask mode the selection stays editable and a small bar asks:
screenshot, video or scrolling capture?

Coordinates: the selection is kept in screenshot pixels (like the Windows virtual-screen bitmap).
Monitors report logical geometry; scale = screenshot width / total logical width (per axis).
Window picking on hover is impossible on Wayland, so hovering highlights the whole monitor.
"""

import math

import cairo

from . import _gi  # noqa: F401
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

from . import icons, render, theme
from .i18n import L
from .shapes import font_desc

ACCENT = (255, 120, 30)
MAG_PIXELS = 15
MAG_ZOOM = 8
GAP = 22
HANDLE = 7
EDGE_L, EDGE_T, EDGE_R, EDGE_B = 1, 2, 4, 8
IMAGE, VIDEO, SCROLL = "image", "video", "scroll"


def _rgb(cr, c, a=255):
    cr.set_source_rgba(c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, a / 255.0)


def map_monitors(geoms, shot_w, shot_h):
    """Maps logical monitor rectangles to screenshot pixels.

    Returns (mapping, info): mapping is a list of (logical_rect, pixel_rect) and info is
    (origin_x, origin_y, scale_x, scale_y) with scale = screenshot pixels per logical unit."""
    if not geoms:
        geoms = [(0, 0, shot_w, shot_h)]
    ox = min(g[0] for g in geoms)
    oy = min(g[1] for g in geoms)
    tw = max(g[0] + g[2] for g in geoms) - ox
    th = max(g[1] + g[3] for g in geoms) - oy
    sx = shot_w / float(tw) if tw > 0 else 1.0
    sy = shot_h / float(th) if th > 0 else 1.0
    out = []
    for (x, y, w, h) in geoms:
        px = int(round((x - ox) * sx))
        py = int(round((y - oy) * sy))
        pw = min(shot_w - px, int(round(w * sx)))
        ph = min(shot_h - py, int(round(h * sy)))
        out.append(((x, y, w, h), (px, py, max(1, pw), max(1, ph))))
    return out, (ox, oy, sx, sy)


def display_monitors():
    """[(Gdk.Monitor, (x, y, w, h) logical)] of the default display."""
    mons = []
    display = Gdk.Display.get_default()
    model = display.get_monitors() if display is not None else None
    n = model.get_n_items() if model is not None else 0
    for i in range(n):
        m = model.get_item(i)
        g = m.get_geometry()
        mons.append((m, (g.x, g.y, g.width, g.height)))
    return mons


def monitors_matching(geoms, shot_w, shot_h):
    """Which monitors an image from the desktop's own screenshot UI shows, judged by its shape: the
    indices of all monitors (the whole desktop), of one monitor ("Screen" on a multi-monitor desktop),
    or None (a window or an area, which is a finished capture rather than a backdrop for the overlay)."""
    def fits(w, h):
        if w <= 0 or h <= 0:
            return False
        sx, sy = shot_w / float(w), shot_h / float(h)
        return sx >= 0.99 and abs(sx - sy) <= 0.01 * sx
    if not geoms:
        return None
    ox = min(g[0] for g in geoms)
    oy = min(g[1] for g in geoms)
    if fits(max(g[0] + g[2] for g in geoms) - ox, max(g[1] + g[3] for g in geoms) - oy):
        return list(range(len(geoms)))
    for i, g in enumerate(geoms):
        if fits(g[2], g[3]):
            return [i]
    return None


def rect_intersect(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    if x2 <= x1 or y2 <= y1:
        return (0, 0, 0, 0)
    return (x1, y1, x2 - x1, y2 - y1)


def rect_contains(r, p):
    return r[0] <= p[0] < r[0] + r[2] and r[1] <= p[1] < r[1] + r[3]


def rect_empty(r):
    return r is None or r[2] <= 0 or r[3] <= 0


class CaptureOverlay:
    """Controller shared by the per-monitor windows. on_done(result) gets None (cancelled) or
    (choice, pixel_rect, logical_rect)."""

    def __init__(self, app, shot, on_done, prompt=None, ask_mode=False, monitors=None):
        self.app = app
        self.shot = shot
        self.on_done = on_done
        self.prompt = prompt
        self.ask_mode = ask_mode
        self.w, self.h = render.size(shot)

        # Dimmed copy painted everywhere outside the highlight.
        self.dim = render.copy_surface(shot)
        cr = cairo.Context(self.dim)
        cr.set_source_rgba(0, 0, 0, 125 / 255.0)
        cr.paint()
        self.dim.flush()

        mons = monitors if monitors is not None else display_monitors()
        mapping, self.info = map_monitors([g for (_m, g) in mons], self.w, self.h)
        self.views = []
        for i, (logical, pixel) in enumerate(mapping):
            mon = mons[i][0] if i < len(mons) else None
            self.views.append(MonitorView(self, mon, logical, pixel))

        self.cursor = None          # global pixel position of the pointer
        self.active = self.views[0] if self.views else None
        self.mouse_down = False
        self.dragging = False
        self.selected = False
        self.selection = (0, 0, 0, 0)
        self.hover = (0, 0, 0, 0)
        self.drag_kind = None       # None, "move" or "resize"
        self.drag_edges = 0
        self.drag_start = (0, 0)
        self.drag_orig = (0, 0, 0, 0)
        self.finished = False

    # ---------- Lifecycle ----------

    def show(self):
        for v in self.views:
            v.present()
        if self.active is not None:
            self.hover = self.active.pixel

    def _close_windows(self):
        for v in self.views:
            v.destroy()
        self.views = []

    def cancel(self):
        if self.finished:
            return
        self.finished = True
        self._close_windows()
        if self.on_done:
            self.on_done(None)

    def finish(self, choice):
        if self.finished:
            return
        x, y, w, h = self.selection
        if w < 3 or h < 3:
            return
        self.finished = True
        ox, oy, sx, sy = self.info
        logical = (ox + x / sx, oy + y / sy, w / sx, h / sy)
        self._close_windows()
        if self.on_done:
            # Let the compositor remove the overlay before anything else (recording) starts.
            GLib.timeout_add(150, lambda: (self.on_done((choice, self.selection, logical)), False)[1])

    # ---------- State ----------

    @property
    def highlight(self):
        return self.selection if (self.selected or self.dragging) else self.hover

    def redraw(self):
        for v in self.views:
            v.area.queue_draw()

    def update_state(self, view, p):
        self.cursor = p
        self.active = view
        if self.mouse_down:
            sx = self.info[2]
            if not self.dragging and (abs(p[0] - self.drag_start[0]) > 3 * sx or abs(p[1] - self.drag_start[1]) > 3 * sx):
                self.dragging = True
            if self.dragging:
                self.selection = rect_intersect(self.from_points(self.drag_start, p), view.pixel)
        if not self.dragging:
            self.hover = view.pixel
        self.redraw()

    @staticmethod
    def from_points(a, b):
        x1, y1 = min(a[0], b[0]), min(a[1], b[1])
        return (x1, y1, max(a[0], b[0]) + 1 - x1, max(a[1], b[1]) + 1 - y1)

    def enter_selected(self, view, r):
        r = rect_intersect(r, view.pixel)
        if rect_empty(r):
            return
        self.selection = r
        self.selected = True
        self.mouse_down = self.dragging = False
        self.drag_kind = None
        self.active = view
        for v in self.views:
            v.area.set_cursor_from_name("default")
            if v is not view:
                v.hide_bar()
        view.show_bar()
        self.redraw()

    def reselect(self):
        self.selected = False
        self.drag_kind = None
        for v in self.views:
            v.hide_bar()
            v.area.set_cursor_from_name("crosshair")
            v.area.grab_focus()
        self.redraw()

    def simulate_select(self, rect):
        """Used by --selftest to show the selected state without real mouse input."""
        for v in self.views:
            if not rect_empty(rect_intersect(rect, v.pixel)):
                self.enter_selected(v, rect)
                return

    def hit_edges(self, p):
        x, y, w, h = self.selection
        t = HANDLE * self.info[2]
        if not (x - t <= p[0] <= x + w + t and y - t <= p[1] <= y + h + t):
            return 0
        e = 0
        if abs(p[0] - x) <= t:
            e |= EDGE_L
        elif abs(p[0] - (x + w)) <= t:
            e |= EDGE_R
        if abs(p[1] - y) <= t:
            e |= EDGE_T
        elif abs(p[1] - (y + h)) <= t:
            e |= EDGE_B
        return e

    @staticmethod
    def cursor_for(edges):
        if edges in (EDGE_L | EDGE_T, EDGE_R | EDGE_B):
            return "nwse-resize"
        if edges in (EDGE_R | EDGE_T, EDGE_L | EDGE_B):
            return "nesw-resize"
        if edges in (EDGE_L, EDGE_R):
            return "ew-resize"
        if edges in (EDGE_T, EDGE_B):
            return "ns-resize"
        return "default"

    def set_selection(self, r):
        view = self.active
        r = rect_intersect(r, view.pixel)
        if r[2] < 4 or r[3] < 4:
            return
        self.selection = r
        view.position_bar()
        self.redraw()

    def drag_selection(self, p):
        dx, dy = p[0] - self.drag_start[0], p[1] - self.drag_start[1]
        o = self.drag_orig
        mx, my, mw, mh = self.active.pixel
        if self.drag_kind == "move":
            x = int(max(mx, min(o[0] + dx, mx + mw - o[2])))
            y = int(max(my, min(o[1] + dy, my + mh - o[3])))
            self.set_selection((x, y, o[2], o[3]))
            return
        left, top, right, bottom = o[0], o[1], o[0] + o[2], o[1] + o[3]
        if self.drag_edges & EDGE_L:
            left += dx
        if self.drag_edges & EDGE_R:
            right += dx
        if self.drag_edges & EDGE_T:
            top += dy
        if self.drag_edges & EDGE_B:
            bottom += dy
        x1, x2 = int(min(left, right)), int(max(left, right))
        y1, y2 = int(min(top, bottom)), int(max(top, bottom))
        self.set_selection((x1, y1, x2 - x1, y2 - y1))

    # ---------- Input (called by the views) ----------

    def press(self, view, p):
        if self.selected:
            edges = self.hit_edges(p) if view is self.active else 0
            if view is self.active and (edges or rect_contains(self.selection, p)):
                self.drag_kind = "resize" if edges else "move"
                self.drag_edges = edges
                self.drag_start = p
                self.drag_orig = self.selection
                return
            # Clicking outside starts a brand-new selection.
            self.selected = False
            for v in self.views:
                v.hide_bar()
                v.area.set_cursor_from_name("crosshair")
        self.mouse_down = True
        self.dragging = False
        self.drag_start = p
        self.update_state(view, p)

    def motion(self, view, p, dragging_now):
        if self.selected:
            if self.drag_kind is not None:
                if dragging_now:
                    self.drag_selection(p)
                return
            if view is self.active:
                edges = self.hit_edges(p)
                name = self.cursor_for(edges) if edges else ("move" if rect_contains(self.selection, p) else "default")
                view.area.set_cursor_from_name(name)
            return
        self.update_state(view, p)

    def release(self, view, p):
        if self.selected:
            self.drag_kind = None
            return
        if not self.mouse_down:
            return
        self.mouse_down = False
        r = self.selection if self.dragging else self.hover
        self.dragging = False
        if r[2] < 3 or r[3] < 3:
            self.update_state(view, p)
            return
        if self.ask_mode:
            self.enter_selected(view, r)
            return
        self.selection = r
        self.finish(IMAGE)

    def key(self, view, keyval, state):
        step = 10 if state & Gdk.ModifierType.SHIFT_MASK else 1
        k = Gdk.keyval_to_lower(keyval)
        if self.selected:
            if k == Gdk.KEY_Escape:
                self.cancel()
            elif k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space, Gdk.KEY_c):
                self.finish(IMAGE)
            elif k == Gdk.KEY_v:
                self.finish(VIDEO)
            elif k == Gdk.KEY_s:
                self.finish(SCROLL)
            elif k in (Gdk.KEY_r, Gdk.KEY_BackSpace):
                self.reselect()
            elif k in (Gdk.KEY_Left, Gdk.KEY_Right, Gdk.KEY_Up, Gdk.KEY_Down):
                x, y, w, h = self.selection
                dx = -step if k == Gdk.KEY_Left else step if k == Gdk.KEY_Right else 0
                dy = -step if k == Gdk.KEY_Up else step if k == Gdk.KEY_Down else 0
                self.set_selection((x + dx, y + dy, w, h))
            else:
                return False
            return True
        if k == Gdk.KEY_Escape:
            self.cancel()
            return True
        if k in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            target = self.active or view
            if self.ask_mode:
                self.enter_selected(target, target.pixel)
            else:
                self.selection = target.pixel
                self.finish(IMAGE)
            return True
        return False


class MonitorView(Gtk.Window):
    """One monitor's full-screen window."""

    def __init__(self, ctl, monitor, logical, pixel):
        super().__init__()
        self.ctl = ctl
        self.monitor = monitor
        self.logical = logical      # (x, y, w, h) logical units
        self.pixel = pixel          # same monitor in screenshot pixels
        self.sx = pixel[2] / float(logical[2]) if logical[2] else 1.0
        self.sy = pixel[3] / float(logical[3]) if logical[3] else 1.0
        self.bar = None
        self.width_entry = self.height_entry = None
        self._syncing = False
        self.local_cursor = None

        if ctl.app is not None:
            self.set_application(ctl.app)
        self.set_title("MiniSnap")
        self.set_decorated(False)
        self.add_css_class("ms-overlay")

        self.fixed = Gtk.Fixed()
        self.area = Gtk.DrawingArea()
        self.area.set_size_request(int(logical[2]), int(logical[3]))
        self.area.set_draw_func(self._draw)
        self.area.set_focusable(True)
        self.area.set_cursor_from_name("crosshair")
        self.fixed.put(self.area, 0, 0)
        self.set_child(self.fixed)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._on_motion)
        motion.connect("leave", self._on_leave)
        self.area.add_controller(motion)

        self.drag = Gtk.GestureDrag()
        self.drag.set_button(1)
        self.drag.connect("drag-begin", self._on_drag_begin)
        self.drag.connect("drag-update", self._on_drag_update)
        self.drag.connect("drag-end", self._on_drag_end)
        self.area.add_controller(self.drag)

        right = Gtk.GestureClick()
        right.set_button(3)
        right.connect("pressed", lambda *a: self.ctl.cancel())
        self.area.add_controller(right)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        if monitor is not None:
            self.fullscreen_on_monitor(monitor)
        else:
            self.fullscreen()

    # ---------- Coordinates ----------

    def to_px(self, x, y):
        return (int(math.floor(self.pixel[0] + x * self.sx)), int(math.floor(self.pixel[1] + y * self.sy)))

    def to_local(self, px, py):
        return ((px - self.pixel[0]) / self.sx, (py - self.pixel[1]) / self.sy)

    def local_rect(self, r):
        x, y = self.to_local(r[0], r[1])
        return (x, y, r[2] / self.sx, r[3] / self.sy)

    # ---------- Input ----------

    def _on_motion(self, ctrl, x, y):
        self.local_cursor = (x, y)
        dragging_now = self.drag.is_active() if hasattr(self.drag, "is_active") else False
        self.ctl.motion(self, self.to_px(x, y), dragging_now)

    def _on_leave(self, ctrl):
        self.local_cursor = None
        self.area.queue_draw()

    def _on_drag_begin(self, gesture, x, y):
        self.area.grab_focus()
        self.local_cursor = (x, y)
        self.ctl.press(self, self.to_px(x, y))

    def _current(self, gesture, dx, dy):
        ok, sx, sy = gesture.get_start_point()
        return sx + dx, sy + dy

    def _on_drag_update(self, gesture, dx, dy):
        x, y = self._current(gesture, dx, dy)
        self.local_cursor = (x, y)
        p = self.to_px(x, y)
        if self.ctl.selected:
            if self.ctl.drag_kind is not None:
                self.ctl.drag_selection(p)
            return
        self.ctl.update_state(self, p)

    def _on_drag_end(self, gesture, dx, dy):
        x, y = self._current(gesture, dx, dy)
        self.ctl.release(self, self.to_px(x, y))

    def _editing_size(self):
        focus = self.get_focus()
        while focus is not None:
            if focus is self.width_entry or focus is self.height_entry:
                return True
            focus = focus.get_parent()
        return False

    def _on_key(self, ctrl, keyval, keycode, state):
        if self._editing_size():
            if keyval == Gdk.KEY_Escape:
                self.update_entries(force=True)
                self.area.grab_focus()
                return True
            return False
        return self.ctl.key(self, keyval, state)

    # ---------- Mode bar ----------

    def _bar_button(self, kind, css, tip, cb, sensitive=True):
        b = Gtk.Button()
        b.set_child(icons.Glyph(kind, 24, ink=(255, 255, 255), paper=(25, 110, 225), mono=True))
        b.add_css_class("ms-bar-button")
        b.add_css_class(css)
        b.set_tooltip_text(tip)
        b.set_focusable(False)
        b.set_sensitive(sensitive)
        b.connect("clicked", lambda *_: cb())
        return b

    def _size_entry(self, tip):
        e = Gtk.Entry()
        e.add_css_class("ms-size-entry")
        e.set_max_length(5)
        e.set_width_chars(5)
        e.set_max_width_chars(5)
        e.set_alignment(0.5)
        e.set_input_purpose(Gtk.InputPurpose.DIGITS)
        e.set_tooltip_text(tip)
        e.connect("activate", lambda *_: (self.apply_entries(), self.area.grab_focus()))
        e.connect("changed", self._digits_only)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.apply_entries())
        e.add_controller(focus)
        return e

    def _digits_only(self, entry):
        text = entry.get_text()
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits != text:
            entry.set_text(digits)

    def build_bar(self):
        ctl = self.ctl
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bar.add_css_class("ms-modebar")
        bar.append(self._bar_button("camera", "ms-bar-blue", L.t("Chụp ảnh (Enter)"), lambda: ctl.finish(IMAGE)))
        bar.append(self._bar_button("video", "ms-bar-blue", L.t("Quay video (V)"), lambda: ctl.finish(VIDEO)))
        bar.append(self._bar_button("scroll", "ms-bar-blue", L.t("Chụp cuộn (S)"), lambda: ctl.finish(SCROLL)))
        self.width_entry = self._size_entry(L.t("Rộng (px) — nhập rồi nhấn Enter"))
        self.height_entry = self._size_entry(L.t("Cao (px) — nhập rồi nhấn Enter"))
        self.width_entry.set_margin_start(14)
        bar.append(self.width_entry)
        times = Gtk.Label(label="×")
        bar.append(times)
        bar.append(self.height_entry)
        reselect = self._bar_button("refresh", "ms-bar-gray", L.t("Chọn lại (R)"), ctl.reselect)
        reselect.set_margin_start(14)
        bar.append(reselect)
        bar.append(self._bar_button("close", "ms-bar-gray", L.t("Huỷ (Esc)"), ctl.cancel))
        self.bar = bar
        self.fixed.put(bar, 0, 0)

    def show_bar(self):
        if self.bar is None:
            self.build_bar()
        self.update_entries(force=True)
        self.bar.set_visible(True)
        self.position_bar()
        self.area.grab_focus()

    def hide_bar(self):
        if self.bar is not None:
            self.bar.set_visible(False)

    def update_entries(self, force=False):
        if self.width_entry is None:
            return
        self._syncing = True
        x, y, w, h = self.ctl.selection
        if force or not self._editing_size():
            self.width_entry.set_text(str(int(w)))
            self.height_entry.set_text(str(int(h)))
        self._syncing = False

    def apply_entries(self):
        if self._syncing or not self.ctl.selected or self.width_entry is None:
            return
        try:
            w = int(self.width_entry.get_text())
            h = int(self.height_entry.get_text())
        except ValueError:
            self.update_entries(force=True)
            return
        x, y, _, _ = self.ctl.selection
        px, py, pw, ph = self.pixel
        w = max(4, min(w, px + pw - x))
        h = max(4, min(h, py + ph - y))
        self.ctl.set_selection((x, y, w, h))
        self.update_entries(force=True)

    def _label_size(self, text):
        layout = self.area.create_pango_layout(text)
        layout.set_font_description(font_desc(12.5))
        _ink, logical = layout.get_pixel_extents()
        return logical.width, logical.height

    def label_rect(self, h_local):
        tw, th = self._label_size(self.size_text())
        w, ht = tw + 12, th + 6
        x = max(0, min(h_local[0], self.logical[2] - w))
        y = h_local[1] - ht - 6 - (HANDLE / 2 if self.ctl.selected else 0)
        if y < 0:
            y = h_local[1] + 6 + (HANDLE if self.ctl.selected else 0)
        return (x, y, w, ht)

    def size_text(self):
        r = self.ctl.highlight
        return "%d × %d" % (r[2], r[3])

    def position_bar(self):
        """Below the selection, else above it, else inside its bottom edge (CaptureOverlay.PositionBar)."""
        self.update_entries()
        if self.bar is None or not self.bar.get_visible():
            return
        _min, bw, _a, _b = self.bar.measure(Gtk.Orientation.HORIZONTAL, -1)
        _min, bh, _a, _b = self.bar.measure(Gtk.Orientation.VERTICAL, bw)
        sel = self.local_rect(self.ctl.selection)
        W, H = self.logical[2], self.logical[3]
        pad = 10
        x = sel[0] + (sel[2] - bw) / 2.0
        x = max(pad, min(x, W - bw - pad))
        y = sel[1] + sel[3] + pad + HANDLE
        if y + bh > H - pad:
            y = sel[1] - bh - pad - HANDLE - self.label_rect(sel)[3]
        if y < pad:
            y = sel[1] + sel[3] - bh - pad
        self.fixed.move(self.bar, int(x), int(y))

    # ---------- Painting ----------

    def _draw(self, area, cr, width, height):
        ctl = self.ctl
        scale = area.get_scale_factor()
        exact = abs(self.sx - scale) < 1e-3 and abs(self.sy - scale) < 1e-3
        filt = cairo.FILTER_NEAREST if exact else cairo.FILTER_GOOD

        # Frozen screenshot: dimmed everywhere, bright inside the highlight.
        cr.save()
        cr.scale(1.0 / self.sx, 1.0 / self.sy)
        cr.translate(-self.pixel[0], -self.pixel[1])
        cr.set_source_surface(ctl.dim, 0, 0)
        cr.get_source().set_filter(filt)
        cr.paint()
        h = ctl.highlight
        lit = rect_intersect(h, self.pixel)
        if not rect_empty(lit):
            cr.rectangle(*lit)
            cr.clip()
            cr.set_source_surface(ctl.shot, 0, 0)
            cr.get_source().set_filter(filt)
            cr.paint()
        cr.restore()

        here = ctl.active is self and self.local_cursor is not None
        if not ctl.selected and here:
            cx, cy = self.local_cursor
            cr.save()
            cr.set_source_rgba(1, 1, 1, 170 / 255.0)
            cr.set_line_width(1)
            cr.set_dash([4, 3])
            cr.move_to(0, math.floor(cy) + 0.5)
            cr.line_to(width, math.floor(cy) + 0.5)
            cr.move_to(math.floor(cx) + 0.5, 0)
            cr.line_to(math.floor(cx) + 0.5, height)
            cr.stroke()
            cr.restore()

        if not rect_empty(lit):
            hl = self.local_rect(lit)
            cr.save()
            _rgb(cr, ACCENT)
            cr.set_line_width(2)
            cr.rectangle(hl[0] - 1, hl[1] - 1, hl[2] + 2, hl[3] + 2)
            cr.stroke()
            if ctl.selected and ctl.active is self:
                s = HANDLE
                xs = (hl[0], hl[0] + hl[2] / 2.0, hl[0] + hl[2])
                ys = (hl[1], hl[1] + hl[3] / 2.0, hl[1] + hl[3])
                for yy in ys:
                    for xx in xs:
                        if xx == xs[1] and yy == ys[1]:
                            continue
                        cr.rectangle(xx - s / 2.0, yy - s / 2.0, s, s)
                        cr.set_source_rgb(1, 1, 1)
                        cr.fill_preserve()
                        _rgb(cr, ACCENT)
                        cr.set_line_width(1.5)
                        cr.stroke()
            if ctl.active is self or ctl.selected:
                lr = self.label_rect(hl)
                icons.rounded_rect(cr, lr[0], lr[1], lr[2], lr[3], 4)
                cr.set_source_rgba(25 / 255.0, 25 / 255.0, 28 / 255.0, 220 / 255.0)
                cr.fill()
                layout = PangoCairo.create_layout(cr)
                layout.set_font_description(font_desc(12.5))
                layout.set_text(self.size_text(), -1)
                _ink, logical = layout.get_pixel_extents()
                cr.move_to(lr[0] + (lr[2] - logical.width) / 2.0, lr[1] + (lr[3] - logical.height) / 2.0)
                cr.set_source_rgb(1, 1, 1)
                PangoCairo.show_layout(cr, layout)
            cr.restore()

        if ctl.prompt and not ctl.selected and (ctl.active is self):
            self._draw_prompt(cr, width)

        if not ctl.selected and here:
            self._draw_magnifier(cr, width, height)

    def _draw_prompt(self, cr, width):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(font_desc(13))
        layout.set_text(self.ctl.prompt, -1)
        _ink, logical = layout.get_pixel_extents()
        w, h = logical.width + 32, logical.height + 16
        x, y = (width - w) / 2.0, 24
        icons.rounded_rect(cr, x, y, w, h, h / 2.0)
        cr.set_source_rgba(1, 120 / 255.0, 30 / 255.0, 235 / 255.0)
        cr.fill()
        cr.move_to(x + 16, y + 8)
        cr.set_source_rgb(1, 1, 1)
        PangoCairo.show_layout(cr, layout)

    def _draw_magnifier(self, cr, width, height):
        ctl = self.ctl
        cx, cy = self.local_cursor
        gx, gy = self.to_px(cx, cy)
        zoom_size = MAG_PIXELS * MAG_ZOOM
        half = MAG_PIXELS // 2
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(font_desc(12.5))
        color = render.pixel_rgb(ctl.shot, gx, gy)
        layout.set_text("%d, %d\n#%02X%02X%02X" % (gx, gy, color[0], color[1], color[2]), -1)
        _ink, logical = layout.get_pixel_extents()
        info_h = logical.height + 10
        w, h = zoom_size, zoom_size + info_h
        x, y = cx + GAP, cy + GAP
        if x + w > width:
            x = cx - GAP - w
        if y + h > height:
            y = cy - GAP - h

        cr.save()
        cr.rectangle(x, y, w, h)
        cr.set_source_rgb(0, 0, 0)
        cr.fill()
        # Zoomed pixels, nearest-neighbour.
        cr.save()
        cr.rectangle(x, y, zoom_size, zoom_size)
        cr.clip()
        cr.translate(x, y)
        cr.scale(MAG_ZOOM, MAG_ZOOM)
        cr.translate(-(gx - half), -(gy - half))
        cr.set_source_surface(ctl.shot, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_NEAREST)
        cr.paint()
        cr.restore()
        _rgb(cr, ACCENT, 50)
        cr.rectangle(x, y + half * MAG_ZOOM, zoom_size, MAG_ZOOM)
        cr.rectangle(x + half * MAG_ZOOM, y, MAG_ZOOM, zoom_size)
        cr.fill()
        _rgb(cr, ACCENT)
        cr.set_line_width(1)
        cr.rectangle(x + half * MAG_ZOOM + 0.5, y + half * MAG_ZOOM + 0.5, MAG_ZOOM - 1, MAG_ZOOM - 1)
        cr.stroke()
        cr.set_source_rgb(1, 1, 1)
        cr.rectangle(x + 0.5, y + 0.5, w - 1, h - 1)
        cr.stroke()
        # Colour swatch and "x, y / #RRGGBB".
        sw = info_h / 2.0
        sx0, sy0 = x + 8, y + zoom_size + (info_h - sw) / 2.0
        cr.rectangle(sx0, sy0, sw, sw)
        _rgb(cr, color)
        cr.fill_preserve()
        cr.set_source_rgb(0.5, 0.5, 0.5)
        cr.stroke()
        cr.move_to(sx0 + sw + 8, y + zoom_size + (info_h - logical.height) / 2.0)
        cr.set_source_rgb(1, 1, 1)
        PangoCairo.show_layout(cr, layout)
        cr.restore()
