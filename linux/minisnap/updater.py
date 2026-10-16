"""Checks GitHub Releases of kingrubic/minisnap for a newer version (port of windows/src/Updater.cs).

On Linux there is no self-install in phase 1: a newer release is shown with its notes and a
"View on GitHub" button. The daily silent check only runs when "Check for updates daily" is on.
"""

import datetime
import json
import threading
import urllib.error
import urllib.request

from . import _gi  # noqa: F401
from gi.repository import Adw, GLib, Gtk

from . import REPO, VERSION, paths, settings
from .i18n import L

API = "https://api.github.com/repos/kingrubic/minisnap/releases/latest"


class Release:
    def __init__(self, tag=None, name=None, notes=None, page_url=None):
        self.tag = tag
        self.name = name
        self.notes = notes
        self.page_url = page_url
        self.version = parse_version(tag)


def parse_version(tag):
    """'v1.5.1' / '1.5' / '1.6.0-beta' -> (major, minor, patch); None when unparsable."""
    t = (tag or "").strip().lstrip("vV")
    for sep in "-+ ":
        t = t.split(sep, 1)[0]
    parts = t.split(".")
    try:
        nums = [int(p) for p in parts if p != ""]
    except ValueError:
        return None
    if not nums or len(nums) > 4:
        return None
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


CURRENT = parse_version(VERSION)


def version_text(v):
    return ".".join(str(x) for x in v) if v else "?"


def is_newer(release, current=None):
    current = current or CURRENT
    return release is not None and release.version is not None and release.version > current


def fetch(timeout=15):
    """The latest published release, or None when the repository has no release yet (404)."""
    req = urllib.request.Request(API, headers={
        "User-Agent": "MiniSnap/" + VERSION,
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return Release(tag=data.get("tag_name"), name=data.get("name"), notes=data.get("body"),
                   page_url=data.get("html_url") or REPO + "/releases")


# ---------- Daily background check ----------

def due_for_auto_check():
    last = settings.get("last_update_check")
    if not last:
        return True
    try:
        t = datetime.datetime.fromisoformat(last)
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return True
    return datetime.datetime.now(datetime.timezone.utc) - t >= datetime.timedelta(hours=24)


def mark_checked():
    try:
        settings.set("last_update_check", datetime.datetime.now(datetime.timezone.utc).isoformat())
    except OSError:
        pass


def schedule_auto_check(on_found):
    """Quiet check 15 s after start and then once a day while MiniSnap runs; on_found(release) in the
    main thread only when something newer exists."""
    def run_check():
        if not settings.get("auto_update_check") or not due_for_auto_check():
            return

        def work():
            try:
                r = fetch()
                mark_checked()
            except Exception:  # noqa: BLE001 - silent: no network is not an error here
                return
            if is_newer(r):
                GLib.idle_add(lambda: (on_found(r), False)[1])
        threading.Thread(target=work, daemon=True).start()

    GLib.timeout_add_seconds(15, lambda: (run_check(), False)[1])
    GLib.timeout_add_seconds(24 * 3600, lambda: (run_check(), True)[1])


class UpdateWindow(Adw.ApplicationWindow):
    def __init__(self, app, known=None):
        super().__init__(application=app)
        self.release = None
        self.set_title(L.t("Cập nhật MiniSnap"))
        self.set_default_size(520, 420)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(22)
        box.set_margin_end(22)
        box.set_margin_top(14)
        box.set_margin_bottom(18)
        self.title_label = Gtk.Label(xalign=0)
        self.title_label.set_wrap(True)
        self.title_label.add_css_class("ms-update-title")
        self.detail = Gtk.Label(xalign=0)
        self.detail.set_wrap(True)
        self.detail.set_selectable(True)
        self.detail.add_css_class("dim-label")
        self.notes = Gtk.TextView()
        self.notes.set_editable(False)
        self.notes.set_cursor_visible(False)
        self.notes.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes.set_left_margin(8)
        self.notes.set_right_margin(8)
        self.notes.set_top_margin(6)
        self.notes.set_bottom_margin(6)
        self.notes_scroll = Gtk.ScrolledWindow()
        self.notes_scroll.set_vexpand(True)
        self.notes_scroll.set_child(self.notes)
        self.notes_scroll.add_css_class("card")
        self.notes_scroll.set_visible(False)
        buttons = Gtk.Box(spacing=8)
        buttons.set_halign(Gtk.Align.END)
        buttons.set_valign(Gtk.Align.END)
        buttons.set_vexpand(True)
        self.github = Gtk.Button(label=L.t("Xem trên GitHub"))
        self.github.add_css_class("suggested-action")
        self.github.set_visible(False)
        self.github.connect("clicked", lambda *_: paths.open_uri(self.release.page_url if self.release and self.release.page_url else REPO + "/releases"))
        self.close_btn = Gtk.Button(label=L.t("Để sau"))
        self.close_btn.connect("clicked", lambda *_: self.close())
        buttons.append(self.github)
        buttons.append(self.close_btn)
        for w in (self.title_label, self.detail, self.notes_scroll, buttons):
            box.append(w)
        view.set_content(box)
        self.set_content(view)

        if known is not None:
            self.show_result(known, None)
        else:
            self.title_label.set_text(L.t("Đang kiểm tra cập nhật..."))
            self.detail.set_text(L.t("Phiên bản hiện tại: ") + VERSION)
            threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        r, error = None, None
        try:
            r = fetch()
            mark_checked()
        except Exception as e:  # noqa: BLE001
            error = str(getattr(e, "reason", None) or e)
        GLib.idle_add(lambda: (self.show_result(r, error), False)[1])

    def show_result(self, r, error):
        self.release = r
        self.close_btn.set_label(L.t("Đóng"))
        if error is not None:
            self.title_label.set_text(L.t("Không kiểm tra được cập nhật"))
            self.detail.set_text(error + L.t("\nHãy kiểm tra kết nối mạng rồi thử lại."))
            return
        if r is None:
            self.title_label.set_text(L.t("Bạn đang dùng bản mới nhất"))
            self.detail.set_text(L.t("Chưa có bản phát hành nào trên GitHub. Phiên bản hiện tại: ") + VERSION)
            return
        if not is_newer(r):
            self.title_label.set_text(L.t("Bạn đang dùng bản mới nhất"))
            self.detail.set_text(L.t("Phiên bản hiện tại: ") + VERSION + L.t(" — mới nhất trên GitHub: ")
                                 + (version_text(r.version) if r.version else (r.tag or "?")))
            self.github.set_visible(True)
            self.github.remove_css_class("suggested-action")
            return
        self.title_label.set_text(L.t("Có phiên bản mới: ") + version_text(r.version))
        self.detail.set_text(L.t("Bạn đang dùng ") + VERSION + L.t(". Ảnh, video và cài đặt của bạn được giữ nguyên khi cập nhật.")
                             + L.t("\nHãy tải bản mới cho Linux trên trang GitHub."))
        text = (r.notes or "").strip() or (r.name or r.tag or "")
        if len(text) > 4000:
            text = text[:4000] + "…"
        self.notes.get_buffer().set_text(text.replace("\r\n", "\n"), -1)
        self.notes_scroll.set_visible(True)
        self.github.set_visible(True)
        self.close_btn.set_label(L.t("Để sau"))
