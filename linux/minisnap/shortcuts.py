"""Explains how to bind MiniSnap commands to GNOME custom keyboard shortcuts.

Real global hotkeys (the GlobalShortcuts portal) arrive in phase 2; until then the desktop's own
custom shortcuts run `minisnap --capture region` and friends, which reach the running instance.
"""

import os
import shlex
import shutil
import subprocess

from . import _gi  # noqa: F401
from gi.repository import Adw, GLib, Gtk

from .i18n import L


def launcher_command():
    """`minisnap` when installed on PATH, else the absolute path of linux/bin/minisnap.

    Inside Flatpak the shortcut runs on the host, so it must go through `flatpak run`."""
    if os.environ.get("FLATPAK_ID") or os.path.exists("/.flatpak-info"):
        return "flatpak run " + os.environ.get("FLATPAK_ID", "io.github.kingrubic.MiniSnap")
    if shutil.which("minisnap"):
        return "minisnap"
    here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "minisnap")
    return here if os.path.exists(here) else "minisnap"


def commands():
    """(name, arguments, suggested keys)."""
    return [
        (L.t("Chụp vùng / cửa sổ"), "--capture region", "Ctrl+Alt+C"),
        (L.t("Chụp toàn màn hình"), "--capture full", "Ctrl+Alt+F"),
        (L.t("Quay video (bắt đầu / dừng)"), "--record", "Ctrl+Alt+R"),
        (L.t("Chụp và trích chữ (OCR)"), "--ocr", "Ctrl+Alt+O"),
        (L.t("Thư viện ảnh & video"), "--library", "Ctrl+Alt+L"),
    ]


class ShortcutsWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title(L.t("Phím tắt bàn phím — MiniSnap"))
        self.set_default_size(640, 620)
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())

        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        page.set_margin_start(20)
        page.set_margin_end(20)
        page.set_margin_top(14)
        page.set_margin_bottom(20)

        intro = Gtk.Label(xalign=0)
        intro.set_wrap(True)
        intro.set_text(L.t("Trên Linux, phím tắt toàn cục được đặt trong Cài đặt của hệ thống. Mỗi phím tắt chạy một lệnh MiniSnap; nếu MiniSnap đang chạy, lệnh được chuyển cho cửa sổ đang mở."))
        page.append(intro)

        steps = Gtk.Label(xalign=0)
        steps.set_wrap(True)
        steps.set_text(L.t("1. Mở Cài đặt → Bàn phím → Xem và tuỳ chỉnh phím tắt → Phím tắt tự tạo.") + "\n"
                       + L.t("2. Bấm + (Thêm phím tắt), đặt tên, dán lệnh bên dưới vào ô Lệnh.") + "\n"
                       + L.t("3. Bấm Đặt phím tắt… rồi nhấn tổ hợp phím, ví dụ Ctrl+Alt+C."))
        page.append(steps)

        group = Adw.PreferencesGroup()
        group.set_title(L.t("Lệnh"))
        exe = launcher_command()
        for name, args, keys in commands():
            cmd = shlex.quote(exe) + " " + args
            row = Adw.ActionRow()
            row.set_use_markup(False)   # titles contain "&"
            row.set_title(name)
            row.set_subtitle(cmd)
            row.set_subtitle_selectable(True)
            row.add_css_class("ms-command-row")
            hint = Gtk.Label(label=L.t("Gợi ý: ") + keys)
            hint.add_css_class("dim-label")
            hint.set_valign(Gtk.Align.CENTER)
            row.add_suffix(hint)
            copy = Gtk.Button(label=L.t("Sao chép"))
            copy.set_valign(Gtk.Align.CENTER)
            copy.connect("clicked", self._copy, cmd)
            row.add_suffix(copy)
            group.add(row)
        page.append(group)

        note = Gtk.Label(xalign=0)
        note.set_wrap(True)
        note.add_css_class("dim-label")
        note.set_text(L.t("Phím Print Screen đang được GNOME dùng cho công cụ chụp màn hình của nó. Muốn dùng Print Screen cho MiniSnap, hãy bỏ phím đó ở mục Chụp màn hình trong Cài đặt → Bàn phím trước."))
        page.append(note)

        if shutil.which("gnome-control-center"):
            open_btn = Gtk.Button(label=L.t("Mở Cài đặt bàn phím"))
            open_btn.add_css_class("suggested-action")
            open_btn.set_halign(Gtk.Align.START)
            open_btn.connect("clicked", self._open_settings)
            page.append(open_btn)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(720)
        clamp.set_child(page)
        scroll.set_child(clamp)
        view.set_content(scroll)
        self.set_content(view)

    def _copy(self, button, cmd):
        self.get_display().get_clipboard().set_text(cmd)
        button.set_label(L.t("✓ Đã chép"))
        GLib.timeout_add(1500, lambda: (button.set_label(L.t("Sao chép")), False)[1])

    def _open_settings(self, *_):
        try:
            subprocess.Popen(["gnome-control-center", "keyboard"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass
