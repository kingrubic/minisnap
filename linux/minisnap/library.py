"""Image & video library (port of windows/src/LibraryForm.cs).

Thumbnails grouped by Today / Yesterday / Last 7 days / This month / Older, filter All / Images /
Videos, search, double-click to open, right-click menu, live refresh through Gio.FileMonitor.
"""

import datetime
import os
import threading

from . import _gi  # noqa: F401
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Graphene, Gtk, Pango

from . import icons, paths, render, theme
from .i18n import L

THUMB_W, THUMB_H = 200, 130


def group_name(mtime, now=None):
    now = now or datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    t = datetime.datetime.fromtimestamp(mtime)
    if t >= today:
        return L.t("Hôm nay")
    if t >= today - datetime.timedelta(days=1):
        return L.t("Hôm qua")
    if t >= today - datetime.timedelta(days=7):
        return L.t("7 ngày qua")
    if t >= datetime.datetime(today.year, today.month, 1):
        return L.t("Tháng này")
    return L.t("Cũ hơn")


def human_size(n):
    if n >= 1 << 20:
        return "%.1f MB" % (n / 1048576.0)
    return "%d KB" % max(1, n // 1024)


def _load_thumb(path, video):
    """GdkPixbuf at 2x the cell size (sharp on HiDPI), or None. Runs in a worker thread."""
    w, h = (THUMB_W - 4) * 2, (THUMB_H - 4) * 2
    if video:
        try:
            info = Gio.File.new_for_path(path).query_info("thumbnail::path", Gio.FileQueryInfoFlags.NONE, None)
            tp = info.get_attribute_byte_string("thumbnail::path")
        except GLib.Error:
            tp = None
        if not tp or not os.path.exists(tp):
            return None
        path = tp
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
        return pb.apply_embedded_orientation() or pb
    except GLib.Error:
        return None


class Thumb(Gtk.Box):
    def __init__(self, window, path, mtime, size):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.owner = window
        self.path = path
        self.video = paths.is_video(path)
        self.pixbuf = None
        self.set_margin_top(4)
        self.set_margin_bottom(4)
        self.area = Gtk.DrawingArea()
        self.area.set_content_width(THUMB_W)
        self.area.set_content_height(THUMB_H)
        self.area.set_draw_func(self._draw)
        self.append(self.area)
        name = os.path.splitext(os.path.basename(path))[0]
        label = Gtk.Label(label=name)
        label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        label.set_max_width_chars(24)
        label.add_css_class("ms-thumb-caption")
        self.append(label)
        when = datetime.datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
        self.set_tooltip_text("%s\n%s • %s" % (os.path.basename(path), when, human_size(size)))

        click = Gtk.GestureClick()
        click.set_button(3)
        click.connect("pressed", self._on_right_click)
        self.add_controller(click)

    def set_pixbuf(self, pb):
        self.pixbuf = pb
        self.area.queue_draw()

    def _on_right_click(self, gesture, n, x, y):
        child = self.get_parent()
        flow = child.get_parent() if child is not None else None
        if isinstance(flow, Gtk.FlowBox) and isinstance(child, Gtk.FlowBoxChild):
            flow.select_child(child)
        self.owner.popup_menu(self, x, y)

    def _draw(self, area, cr, w, h):
        if self.pixbuf is None:
            icons.rounded_rect(cr, 0, 0, w, h, 6)
            cr.set_source_rgb(*theme.surface_rgb())
            cr.fill()
            if self.video:
                icons.draw_play_badge(cr, 0, 0, w, h)
            return
        pw, ph = self.pixbuf.get_width(), self.pixbuf.get_height()
        s = min((w - 4) / float(pw), (h - 4) / float(ph))
        dw, dh = pw * s, ph * s
        x, y = (w - dw) / 2.0, (h - dh) / 2.0
        cr.set_source_rgba(0, 0, 0, 40 / 255.0)
        cr.rectangle(x + 1, y + 2, dw, dh)
        cr.fill()
        cr.save()
        cr.translate(x, y)
        cr.scale(s, s)
        Gdk.cairo_set_source_pixbuf(cr, self.pixbuf, 0, 0)
        cr.paint()
        cr.restore()
        cr.set_source_rgba(0, 0, 0, 50 / 255.0)
        cr.set_line_width(1)
        cr.rectangle(x + 0.5, y + 0.5, dw - 1, dh - 1)
        cr.stroke()
        if self.video:
            icons.draw_play_badge(cr, x, y, dw, dh)


class LibraryWindow(Adw.ApplicationWindow):
    _thumb_cache = {}

    def __init__(self, app, on_open_image, on_ocr):
        super().__init__(application=app)
        self.app = app
        self.on_open_image = on_open_image
        self.on_ocr = on_ocr
        self.filter = "all"
        self.generation = 0
        self.pending_reveal = None
        self.flowboxes = []
        self.thumbs = {}
        self._selecting = False
        self._refresh_id = 0
        self.set_title(L.t("Thư viện — MiniSnap"))
        self.set_default_size(1000, 680)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        filters.add_css_class("linked")
        self.filter_buttons = {}
        first = None
        for key, text in (("all", L.t("Tất cả")), ("images", L.t("Ảnh")), ("videos", L.t("Video"))):
            b = Gtk.ToggleButton(label=text)
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._on_filter, key)
            filters.append(b)
            self.filter_buttons[key] = b
        header.pack_start(filters)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text(L.t("Tìm:").rstrip(":"))
        self.search.set_max_width_chars(22)
        self.search.connect("search-changed", lambda *_: self.populate())
        header.pack_start(self.search)

        for glyph, tip, cb in (
            ("video", L.t("Thư mục video"), lambda: paths.open_folder(paths.videos_folder())),
            ("folder", L.t("Thư mục ảnh"), lambda: paths.open_folder(paths.images_folder())),
            ("refresh", L.t("Làm mới") + " (F5)", self.populate),
        ):
            b = Gtk.Button()
            b.set_child(icons.Glyph(glyph, 18))
            b.set_tooltip_text(tip)
            b.connect("clicked", lambda _b, f=cb: f())
            header.pack_end(b)
        view.add_top_bar(header)

        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.scroller = Gtk.ScrolledWindow()
        self.scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.stack.add_named(self.scroller, "list")
        self.empty = Adw.StatusPage()
        self.empty.set_icon_name("camera-photo-symbolic")
        self.empty.set_title(L.t("Chưa có ảnh hay video nào."))
        self.empty.set_description(L.t("Dùng cửa sổ MiniSnap hoặc phím tắt bạn đã đặt để chụp."))
        self.stack.add_named(self.empty, "empty")
        self.body.append(self.stack)
        view.set_content(self.body)

        status = Gtk.Box()
        status.add_css_class("ms-statusbar")
        self.count_label = Gtk.Label(xalign=0)
        self.count_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        self.count_label.set_hexpand(True)
        status.append(self.count_label)
        view.add_bottom_bar(status)
        self.set_content(view)

        self._build_actions()
        menu = Gio.Menu()
        main = Gio.Menu()
        main.append(L.t("Mở"), "lib.open")
        main.append(L.t("Trích chữ (OCR)"), "lib.ocr")
        main.append(L.t("Sao chép"), "lib.copy")
        main.append(L.t("Hiện trong thư mục"), "lib.show")
        menu.append_section(None, main)
        danger = Gio.Menu()
        danger.append(L.t("Chuyển vào Thùng rác"), "lib.trash")
        menu.append_section(None, danger)
        self.menu = Gtk.PopoverMenu.new_from_model(menu)
        self.menu.set_has_arrow(False)
        self.menu.set_parent(self.body)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self.monitors = []
        for folder in (paths.images_folder(), paths.videos_folder()):
            try:
                mon = Gio.File.new_for_path(folder).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
                mon.connect("changed", lambda *_: self._queue_refresh())
                self.monitors.append(mon)
            except GLib.Error:
                pass
        self.connect("close-request", self._on_close)

        self.filter_buttons["all"].set_active(True)
        self.populate()

    # ---------- Actions ----------

    def _build_actions(self):
        group = Gio.SimpleActionGroup()
        for name, cb in (("open", self.open_selected), ("ocr", self.ocr_selected), ("copy", self.copy_selected),
                         ("show", self.show_selected), ("trash", self.trash_selected)):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda _a, _p, f=cb: f())
            group.add_action(a)
        self.actions = group
        self.insert_action_group("lib", group)

    def popup_menu(self, widget, x, y):
        p = self.selected_path()
        if p is None:
            return
        self.actions.lookup_action("ocr").set_enabled(paths.is_image(p))
        px, py = x, y
        try:
            if hasattr(widget, "compute_point"):
                pt = Graphene.Point().init(x, y)
                ok, out = widget.compute_point(self.body, pt)
                if ok:
                    px, py = out.x, out.y
            else:
                ok, px, py = widget.translate_coordinates(self.body, x, y)
        except Exception:  # noqa: BLE001
            pass
        rect = Gdk.Rectangle()
        rect.x, rect.y, rect.width, rect.height = int(px), int(py), 1, 1
        self.menu.set_pointing_to(rect)
        self.menu.popup()

    def _on_key(self, ctrl, keyval, keycode, state):
        if isinstance(self.get_focus(), (Gtk.Text, Gtk.Entry, Gtk.SearchEntry)):
            return False
        ctrl_down = bool(state & Gdk.ModifierType.CONTROL_MASK)
        k = Gdk.keyval_to_lower(keyval)
        if k == Gdk.KEY_Delete:
            self.trash_selected()
        elif ctrl_down and k == Gdk.KEY_c:
            self.copy_selected()
        elif ctrl_down and k == Gdk.KEY_f:
            self.search.grab_focus()
        elif k == Gdk.KEY_F5:
            self.populate()
        else:
            return False
        return True

    # ---------- Listing ----------

    def _on_filter(self, button, key):
        if button.get_active() and key != self.filter:
            self.filter = key
            self.populate()

    def _queue_refresh(self):
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
        self._refresh_id = GLib.timeout_add(500, self._refresh_now)

    def _refresh_now(self):
        self._refresh_id = 0
        self.populate()
        return False

    def reveal(self, path):
        self.pending_reveal = path
        self.populate()

    def populate(self):
        files = paths.all_files()
        q = self.search.get_text().strip().lower()
        shown = []
        for (p, mtime, size) in files:
            if self.filter == "images" and not paths.is_image(p):
                continue
            if self.filter == "videos" and not paths.is_video(p):
                continue
            if q and q not in os.path.basename(p).lower():
                continue
            shown.append((p, mtime, size))

        selected_before = self.selected_path()
        self.generation += 1
        gen = self.generation
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(10)
        content.set_margin_bottom(16)
        self.flowboxes = []
        self.thumbs = {}
        todo = []
        reveal_child = None
        reselect = None
        current_group, flow = None, None
        for (p, mtime, size) in shown:
            g = group_name(mtime)
            if g != current_group:
                current_group = g
                header = Gtk.Label(label=g, xalign=0)
                header.add_css_class("heading")
                header.set_margin_top(8)
                content.append(header)
                flow = Gtk.FlowBox()
                flow.set_selection_mode(Gtk.SelectionMode.SINGLE)
                flow.set_activate_on_single_click(False)
                flow.set_homogeneous(True)
                flow.set_max_children_per_line(30)
                flow.set_column_spacing(8)
                flow.set_row_spacing(4)
                flow.set_valign(Gtk.Align.START)
                flow.connect("child-activated", lambda f, c: self.open_selected())
                flow.connect("selected-children-changed", self._on_selection_changed)
                content.append(flow)
                self.flowboxes.append(flow)
            thumb = Thumb(self, p, mtime, size)
            flow.append(thumb)
            self.thumbs[p] = thumb
            key = (p, mtime)
            if key in self._thumb_cache:
                thumb.set_pixbuf(self._thumb_cache[key])
            else:
                todo.append((thumb, key))
            if self.pending_reveal and os.path.realpath(self.pending_reveal) == os.path.realpath(p):
                reveal_child = thumb
            elif p == selected_before:
                reselect = thumb
        self.scroller.set_child(content)
        self.stack.set_visible_child_name("list" if shown else "empty")

        target = reveal_child or reselect
        if target is not None:
            child = target.get_parent()
            child.get_parent().select_child(child)
            if reveal_child is not None:
                GLib.idle_add(lambda: (child.grab_focus(), False)[1])
                self.pending_reveal = None

        n_img = sum(1 for f in shown if paths.is_image(f[0]))
        n_vid = sum(1 for f in shown if paths.is_video(f[0]))
        self.count_label.set_text("%d%s%d%s%s  |  %s" % (n_img, L.t(" ảnh • "), n_vid, L.t(" video   —   "),
                                                         paths.images_folder(), paths.videos_folder()))
        if todo:
            threading.Thread(target=self._load_thumbs, args=(gen, todo), daemon=True).start()

    def _load_thumbs(self, gen, todo):
        for thumb, key in todo:
            if gen != self.generation:
                return
            pb = _load_thumb(key[0], paths.is_video(key[0]))
            if pb is not None:
                GLib.idle_add(self._set_thumb, gen, thumb, key, pb)

    def _set_thumb(self, gen, thumb, key, pb):
        self._thumb_cache[key] = pb
        if gen == self.generation:
            thumb.set_pixbuf(pb)
        return False

    def _on_selection_changed(self, flow):
        if self._selecting or not flow.get_selected_children():
            return
        # One selection across all the date groups.
        self._selecting = True
        for f in self.flowboxes:
            if f is not flow:
                f.unselect_all()
        self._selecting = False

    def selected_path(self):
        for f in self.flowboxes:
            for child in f.get_selected_children():
                thumb = child.get_child()
                if isinstance(thumb, Thumb):
                    return thumb.path
        return None

    # ---------- Commands ----------

    def open_selected(self):
        p = self.selected_path()
        if p is None:
            return
        if paths.is_video(p):
            err = paths.open_uri(paths.file_uri(p))
            if err:
                self._message(err)
        else:
            self.on_open_image(p)

    def ocr_selected(self):
        p = self.selected_path()
        if p is not None and paths.is_image(p):
            self.on_ocr(p)

    def show_selected(self):
        p = self.selected_path()
        if p is not None:
            paths.show_in_folder(p)

    def copy_selected(self):
        p = self.selected_path()
        if p is None:
            return
        clipboard = self.get_display().get_clipboard()
        try:
            if paths.is_image(p):
                clipboard.set_texture(render.to_texture(render.load_surface(p)))
            else:
                uri = paths.file_uri(p)
                providers = [
                    Gdk.ContentProvider.new_for_bytes("text/uri-list", GLib.Bytes.new((uri + "\r\n").encode("utf-8"))),
                    Gdk.ContentProvider.new_for_bytes("x-special/gnome-copied-files",
                                                      GLib.Bytes.new(("copy\n" + uri).encode("utf-8"))),
                ]
                clipboard.set_content(Gdk.ContentProvider.new_union(providers))
            self.count_label.set_text(L.t("Đã sao chép ") + os.path.basename(p) + L.t(" vào clipboard"))
        except Exception as e:  # noqa: BLE001
            self.count_label.set_text(L.t("Không sao chép được: ") + str(getattr(e, "message", e)))

    def trash_selected(self):
        p = self.selected_path()
        if p is None:
            return
        dlg = Adw.MessageDialog(transient_for=self, heading="MiniSnap",
                                body=L.t("Chuyển ") + "\"" + os.path.basename(p) + "\"" + L.t(" vào Thùng rác?"))
        dlg.add_response("cancel", L.t("Huỷ"))
        dlg.add_response("trash", L.t("Chuyển vào Thùng rác"))
        dlg.set_response_appearance("trash", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")

        def answered(d, response):
            if response != "trash":
                return
            try:
                Gio.File.new_for_path(p).trash(None)
            except GLib.Error as e:
                self._message(L.t("Không xoá được ") + os.path.basename(p) + ":\n" + e.message)
            self.populate()
        dlg.connect("response", answered)
        dlg.present()

    def _message(self, text):
        dlg = Adw.MessageDialog(transient_for=self, heading="MiniSnap", body=text)
        dlg.add_response("close", L.t("Đóng"))
        dlg.present()

    def _on_close(self, *_):
        self.generation += 1
        for m in self.monitors:
            m.cancel()
        self.monitors = []
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0
        self.menu.unparent()
        return False
