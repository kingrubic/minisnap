"""The application: single instance, command line, launcher window and the capture flow
(TrayApp in windows/src/Program.cs). There is no tray icon: the launcher window plays that role,
and desktop shortcuts run `minisnap --capture region` etc. on the running instance. Where the
GlobalShortcuts portal exists, MiniSnap can bind real global shortcuts and keep running in the
background (globalshortcuts.py).
"""

import os
import sys

from . import _gi  # noqa: F401
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID, VERSION, capture, icons, paths, render, settings, theme
from .i18n import L

USAGE = """Usage: minisnap [OPTION] [IMAGE...]

  --capture region|full|delayed|window   take a screenshot
  --capture scroll                       scrolling capture of a long page
  --record                              record the screen (again: stop recording)
  --ocr                                  capture an area and extract its text
  --library                              open the image & video library
  --about                                show the About window
  --shortcuts                            explain how to set keyboard shortcuts
  --selftest DIR                         headless self-test (writes PNGs and log.txt to DIR)
  --version                              print the version
  IMAGE                                  open an image in the editor
"""


def parse_args(args):
    """Returns (action, value, files) or raises ValueError. Pure, so the self-test can check it."""
    action, value, files = None, None, []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--capture"):
            if "=" in a:
                value = a.split("=", 1)[1]
            else:
                i += 1
                value = args[i] if i < len(args) else "region"
            if value not in ("region", "full", "delayed", "window", "scroll"):
                raise ValueError("--capture expects region, full, delayed, window or scroll")
            action = "capture"
        elif a in ("--record", "--ocr", "--library", "--about", "--shortcuts"):
            action = a[2:]
        elif a.startswith("-"):
            raise ValueError("unknown option: " + a)
        else:
            files.append(a)
        i += 1
    return action, value, files


class LauncherWindow(Adw.ApplicationWindow):
    """Compact main window with the big capture buttons (the tray menu of the Windows version)."""

    def __init__(self, app):
        super().__init__(application=app)
        self.app = app
        self.set_title("MiniSnap")
        self.set_default_size(470, -1)
        self.set_resizable(False)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_menu_model(app.build_menu())
        menu_btn.set_tooltip_text(L.t("Menu chính"))
        header.pack_end(menu_btn)
        view.add_top_bar(header)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(6)
        box.set_margin_bottom(18)

        title_row = Gtk.Box(spacing=14)
        title_row.append(icons.AppLogo(52))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        name = Gtk.Label(label="MiniSnap", xalign=0)
        name.add_css_class("title-2")
        tagline = Gtk.Label(label=L.t("Chụp ảnh, quay video màn hình và trích chữ"), xalign=0)
        tagline.set_wrap(True)
        tagline.add_css_class("dim-label")
        texts.append(name)
        texts.append(tagline)
        title_row.append(texts)
        box.append(title_row)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_column_homogeneous(True)
        buttons = [
            ("capture", L.t("Chụp vùng / cửa sổ"), "ms-blue", lambda: app.begin_capture("region")),
            ("window", L.t("Chọn cửa sổ"), "ms-teal", app.pick_window),
            ("fullscreen", L.t("Chụp toàn màn hình"), "ms-blue", lambda: app.begin_capture("full")),
            ("timer", L.t("Chụp sau 3 giây"), "ms-gray", lambda: app.begin_capture("region", 3)),
            ("scroll", L.t("Chụp cuộn trang dài"), "ms-orange", lambda: app.begin_capture("scroll")),
            ("record", L.t("Quay video màn hình"), "ms-red", app.toggle_recording),
            ("ocr", L.t("Chụp và trích chữ (OCR)"), "ms-purple", lambda: app.begin_capture("ocr")),
            ("library", L.t("Thư viện"), "ms-green", lambda: app.show_library()),
        ]
        tips = {
            "window": L.t("Hệ thống sẽ cho bạn chọn cửa sổ cần chụp, ảnh mở thẳng trong trình chỉnh sửa"),
            "scroll": L.t("Chọn vùng có nội dung cần cuộn, MiniSnap sẽ tự cuộn xuống và ghép thành một ảnh dài"),
        }
        for i, (glyph, text, css, cb) in enumerate(buttons):
            b = Gtk.Button()
            inner = Gtk.Box(spacing=10)
            inner.append(icons.Glyph(glyph, 26, ink=(255, 255, 255), paper=(0, 0, 0), mono=True))
            label = Gtk.Label(label=text, xalign=0)
            label.set_wrap(True)
            label.set_hexpand(True)
            inner.append(label)
            b.set_child(inner)
            b.add_css_class("ms-big-button")
            b.add_css_class("ms-launch-button")
            b.add_css_class(css)
            if glyph in tips:
                b.set_tooltip_text(tips[glyph])
            b.connect("clicked", lambda _b, f=cb: f())
            last = i == len(buttons) - 1
            grid.attach(b, i % 2, i // 2, 2 if last and i % 2 == 0 else 1, 1)
        box.append(grid)

        hint = Gtk.Label(xalign=0)
        hint.set_wrap(True)
        hint.add_css_class("dim-label")
        hint.add_css_class("caption")
        hint.set_text(L.t("Mẹo: đặt phím tắt trong menu ☰ → Phím tắt bàn phím… để chụp nhanh từ bất cứ đâu."))
        box.append(hint)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(box)
        view.set_content(self.toasts)
        self.set_content(view)

    def toast(self, text):
        t = Adw.Toast.new(text)
        t.set_timeout(4)
        self.toasts.add_toast(t)


class MiniSnapApp(Adw.Application):
    def __init__(self, selftest_dir=None):
        flags = Gio.ApplicationFlags.NON_UNIQUE if selftest_dir else Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        super().__init__(application_id=APP_ID + (".SelfTest" if selftest_dir else ""), flags=flags)
        self.selftest_dir = selftest_dir
        self.selftest_result = 1
        self.launcher = None
        self.library = None
        self.recorder = None
        self.scroller = None
        self.gshortcuts = None
        self.overlay = None
        self.shortcuts_window = None
        self.about_window = None
        self.update_window = None
        self.busy = False
        self._held = False
        self._reopen_launcher = False

    # ---------- Startup ----------

    def do_startup(self):
        Adw.Application.do_startup(self)
        L.load()
        theme.install()
        Gtk.Window.set_default_icon_name(APP_ID)
        from .globalshortcuts import GlobalShortcuts
        self.gshortcuts = GlobalShortcuts(self)
        self._add_actions()
        if not self.selftest_dir:
            # Inside Flatpak, Flathub delivers the updates: no update check at all.
            if not paths.in_flatpak():
                from . import updater
                updater.schedule_auto_check(self._on_update_found)
            if settings.get("global_shortcuts_enabled"):
                GLib.idle_add(lambda: (self.gshortcuts.start(), False)[1])

    @staticmethod
    def updates_from_app():
        """False inside Flatpak (Flathub updates the app); True for .deb and source installs."""
        return not paths.in_flatpak()

    def _add_actions(self):
        def simple(name, cb, accels=None):
            a = Gio.SimpleAction.new(name, None)
            a.connect("activate", lambda *_: cb())
            self.add_action(a)
            if accels:
                self.set_accels_for_action("app." + name, accels)

        simple("capture-region", lambda: self.begin_capture("region"))
        simple("capture-full", lambda: self.begin_capture("full"))
        simple("capture-scroll", lambda: self.begin_capture("scroll"))
        simple("record", self.toggle_recording)
        simple("ocr", lambda: self.begin_capture("ocr"))
        simple("library", lambda: self.show_library())
        simple("shortcuts", self.show_shortcuts)
        simple("check-updates", lambda: self.show_update(None))
        simple("show-update", lambda: self.show_update(getattr(self, "_found_release", None)))
        simple("about", self.show_about)
        simple("quit", self.quit_app, ["<Control>q"])

        lang = Gio.SimpleAction.new_stateful("language", GLib.VariantType.new("s"),
                                             GLib.Variant("s", "en" if L.english else "vi"))
        lang.connect("change-state", self._on_language)
        self.add_action(lang)

        for name, key in (("ask-after-select", "ask_after_select"), ("auto-update", "auto_update_check")):
            a = Gio.SimpleAction.new_stateful(name, None, GLib.Variant("b", bool(settings.get(key))))
            a.connect("change-state", self._on_toggle_setting, key)
            self.add_action(a)

        gs = Gio.SimpleAction.new_stateful("global-shortcuts", None,
                                           GLib.Variant("b", bool(settings.get("global_shortcuts_enabled"))))
        gs.connect("change-state", self._on_global_shortcuts)
        self.add_action(gs)

    def build_menu(self):
        menu = Gio.Menu()
        langs = Gio.Menu()
        langs.append("Tiếng Việt", "app.language::vi")
        langs.append("English", "app.language::en")
        menu.append_submenu("Ngôn ngữ / Language", langs)   # always bilingual so it can be found
        prefs = Gio.Menu()
        prefs.append(L.t("Hỏi chụp ảnh / quay video / chụp cuộn sau khi chọn vùng"), "app.ask-after-select")
        if self.updates_from_app():
            prefs.append(L.t("Tự kiểm tra cập nhật hằng ngày"), "app.auto-update")
        if self.gshortcuts is not None and self.gshortcuts.available:
            prefs.append(L.t("Bật phím tắt toàn cục"), "app.global-shortcuts")
        prefs.append(L.t("Phím tắt bàn phím…"), "app.shortcuts")
        menu.append_section(None, prefs)
        about = Gio.Menu()
        if self.updates_from_app():
            about.append(L.t("Kiểm tra cập nhật..."), "app.check-updates")
        about.append(L.t("Giới thiệu MiniSnap"), "app.about")
        about.append(L.t("Thoát MiniSnap"), "app.quit")
        menu.append_section(None, about)
        return menu

    def _on_language(self, action, value):
        english = value.get_string() == "en"
        action.set_state(value)
        if english == L.english:
            return
        try:
            L.set(english)
        except OSError as e:
            self._message(L.t("Không lưu được cài đặt:\n") + str(e))
            return
        # Rebuild the launcher so every caption is read again through L.t (after the menu has closed).
        GLib.idle_add(self._rebuild_launcher, english)

    def _rebuild_launcher(self, english):
        if self.launcher is not None:
            old = self.launcher
            self.launcher = None
            self.show_launcher()
            old.destroy()
            self.launcher.toast("Language changed to English. Open windows switch when you reopen them." if english
                                else "Đã chuyển sang Tiếng Việt. Các cửa sổ đang mở sẽ đổi khi bạn mở lại.")
        return False

    def _on_toggle_setting(self, action, value, key):
        try:
            settings.set(key, bool(value.get_boolean()))
            action.set_state(value)
        except OSError as e:
            self._message(L.t("Không lưu được cài đặt:\n") + str(e))

    def _on_global_shortcuts(self, action, value):
        try:
            self.gshortcuts.set_enabled(bool(value.get_boolean()))
            action.set_state(value)
        except OSError as e:
            self._message(L.t("Không lưu được cài đặt:\n") + str(e))

    def sync_global_shortcuts_action(self):
        """Keeps the menu check mark in step when shortcuts are enabled from the shortcuts window."""
        a = self.lookup_action("global-shortcuts")
        if a is not None:
            a.set_state(GLib.Variant("b", bool(settings.get("global_shortcuts_enabled"))))

    # ---------- Command line ----------

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        try:
            action, value, files = parse_args(args)
        except ValueError as e:
            if not command_line.get_is_remote():
                print("minisnap: %s\n\n%s" % (e, USAGE), file=sys.stderr)
            return 2
        cwd = command_line.get_cwd() or os.getcwd()
        for f in files:
            gf = Gio.File.new_for_commandline_arg_and_cwd(f, cwd)
            if gf.get_path():
                self.open_image_file(gf.get_path())
        if action == "capture":
            if value == "full":
                self.begin_capture("full")
            elif value == "delayed":
                self.begin_capture("region", 3)
            elif value == "window":
                self.pick_window()
            elif value == "scroll":
                self.begin_capture("scroll")
            else:
                self.begin_capture("region")
        elif action == "record":
            self.toggle_recording()
        elif action == "ocr":
            self.begin_capture("ocr")
        elif action == "library":
            self.show_library()
        elif action == "about":
            self.show_about()
        elif action == "shortcuts":
            self.show_shortcuts()
        elif not files:
            self.activate()
        return 0

    def do_activate(self):
        if self.selftest_dir:
            from . import selftest
            selftest.start(self, self.selftest_dir)
            return
        self.show_launcher()

    # ---------- Windows ----------

    def show_launcher(self):
        if self.launcher is None:
            self.launcher = LauncherWindow(self)
            self.launcher.connect("destroy", self._on_launcher_destroyed)
        self.launcher.present()
        return self.launcher

    def _on_launcher_destroyed(self, win):
        if self.launcher is win:
            self.launcher = None

    def _track(self, win, attr):
        setattr(self, attr, win)

        def gone(w):
            if getattr(self, attr, None) is w:
                setattr(self, attr, None)
        win.connect("destroy", gone)
        return win

    def show_library(self, reveal=None):
        if self.library is None:
            from .library import LibraryWindow
            self._track(LibraryWindow(self, self.open_image_file, self.ocr_file), "library")
        if reveal:
            self.library.reveal(reveal)
        self.library.present()

    def show_about(self):
        if self.about_window is None:
            from .about import make_about
            self._track(make_about(self, self.get_active_window()), "about_window")
        self.about_window.present()

    def show_shortcuts(self):
        if self.shortcuts_window is None:
            from .shortcuts import ShortcutsWindow
            self._track(ShortcutsWindow(self), "shortcuts_window")
        self.shortcuts_window.present()

    def show_update(self, known):
        if self.update_window is not None:
            self.update_window.present()
            return
        from .updater import UpdateWindow
        self._track(UpdateWindow(self, known), "update_window")
        self.update_window.present()

    def _on_update_found(self, release):
        from . import updater
        self._found_release = release
        title = L.t("Có bản MiniSnap mới: ") + updater.version_text(release.version)
        if self.launcher is not None:
            self.launcher.toast(title)
        n = Gio.Notification.new(title)
        n.set_body(L.t("Bấm vào đây để xem."))
        n.set_default_action("app.show-update")
        self.send_notification("update", n)

    def _message(self, text):
        dlg = Adw.MessageDialog(heading="MiniSnap", body=text)
        parent = self.get_active_window()
        if parent is not None:
            dlg.set_transient_for(parent)
        dlg.set_application(self)
        dlg.add_response("close", L.t("Đóng"))
        dlg.present()

    def quit_app(self):
        if self.recorder is not None:
            self.recorder.stop()
        if self.scroller is not None:
            self.scroller.stop()
        if self.gshortcuts is not None:
            # Stop running in the background; the setting stays, so shortcuts are bound again next time.
            self.gshortcuts.shutdown()
        for w in list(self.get_windows()):
            w.close()

    def do_shutdown(self):
        if self.recorder is not None and self.recorder.pipeline is not None:
            self.recorder.stop()
        if self.scroller is not None:
            self.scroller.cancel()
        if self.gshortcuts is not None:
            self.gshortcuts.close()
        Adw.Application.do_shutdown(self)

    # ---------- Opening images ----------

    def open_editor(self, surface, path):
        from .editor import EditorWindow
        ed = EditorWindow(self, surface, path)
        ed.present()
        return ed

    def open_image_file(self, path):
        try:
            surface = render.load_surface(path)
        except Exception as e:  # noqa: BLE001
            self._message(L.t("Không mở được ảnh:\n") + str(getattr(e, "message", e)))
            return
        self.open_editor(surface, path)

    def save_and_edit(self, surface):
        """Every new capture is saved to the library and copied to the clipboard (like Windows)."""
        path = paths.new_image_path()
        try:
            surface.write_to_png(path)
        except Exception:  # noqa: BLE001
            path = None
        render.copy_to_clipboard(surface)
        return self.open_editor(surface, path)

    def show_ocr(self, surface):
        from .ocr import OcrWindow
        w = OcrWindow(self, surface)
        w.present()
        return w

    def ocr_file(self, path):
        try:
            self.show_ocr(render.load_surface(path))
        except Exception as e:  # noqa: BLE001
            self._message(L.t("Không mở được ảnh:\n") + str(getattr(e, "message", e)))

    # ---------- Capture flow ----------

    def _hold(self):
        if not self._held:
            self._held = True
            self.hold()

    def _release(self):
        if self._held:
            self._held = False
            self.release()

    def _hide_launcher(self):
        """The launcher must not appear in the screenshot: close it, reopen it if the capture is cancelled."""
        if self.launcher is not None and self.launcher.get_visible():
            w = self.launcher
            self.launcher = None
            w.destroy()
            return True
        return False

    @staticmethod
    def _prompt(mode):
        if mode == "video":
            return L.t("Quay video: chọn cửa sổ hoặc kéo chọn vùng cần quay (Enter = toàn màn hình)")
        if mode == "ocr":
            return L.t("Trích chữ: chọn vùng có chữ cần lấy")
        if mode == "scroll":
            return L.t("Chụp cuộn: kéo chọn vùng có nội dung cần cuộn — MiniSnap sẽ tự cuộn xuống")
        return None

    def begin_capture(self, mode, delay=0):
        """mode: region, full, ocr, video or scroll."""
        if self.busy or self.scroller is not None or (self.recorder is not None and mode != "video"):
            return
        self.busy = True
        self._hold()
        self._reopen_launcher = self._hide_launcher()
        if delay > 0:
            n = Gio.Notification.new("MiniSnap")
            n.set_body(L.t("Sẽ chụp sau ") + str(delay) + L.t(" giây..."))
            self.send_notification("delay", n)
        # A short delay also lets the launcher disappear before the screen is grabbed.
        GLib.timeout_add(max(350, delay * 1000), self._grab, mode, delay)

    def _grab(self, mode, delay):
        if delay > 0:
            self.withdraw_notification("delay")
        capture.take_screenshot(False, lambda surface, error: self._on_shot(mode, surface, error))
        return False

    def _end_capture(self, cancelled):
        self.busy = False
        self.overlay = None
        if cancelled and self._reopen_launcher:
            self.show_launcher()
        self._reopen_launcher = False
        self._release()

    def _on_shot(self, mode, surface, error):
        if surface is None:
            if error:
                capture.show_error(self, error)
            self._end_capture(cancelled=True)
            return
        if mode == "full":
            self.save_and_edit(surface)
            self._end_capture(cancelled=False)
            return
        from .overlay import CaptureOverlay
        ask = mode == "region" and bool(settings.get("ask_after_select"))
        self.overlay = CaptureOverlay(self, surface, lambda result: self._on_overlay(mode, surface, result),
                                      prompt=self._prompt(mode), ask_mode=ask)
        ox, oy, sx, sy = self.overlay.info
        self._total_logical = (ox, oy, surface.get_width() / sx, surface.get_height() / sy)
        self.overlay.show()

    def _on_overlay(self, mode, shot, result):
        if result is None:
            self._end_capture(cancelled=True)
            return
        choice, rect, logical = result
        if mode == "ocr":
            self.show_ocr(render.crop(shot, rect))
        elif mode == "video" or choice == "video":
            if rect[2] >= 16 and rect[3] >= 16:
                self.start_recording(logical, (rect[2], rect[3]), self._total_logical)
            else:
                self._end_capture(cancelled=True)
                return
        elif mode == "scroll" or choice == "scroll":
            if rect[2] >= 32 and rect[3] >= 32:
                self.start_scroll(logical, rect, self._total_logical)
            else:
                self._end_capture(cancelled=True)
                return
        else:
            self.save_and_edit(render.crop(shot, rect))
        self._end_capture(cancelled=False)

    def pick_window(self):
        """Wayland can't tell apps where windows are, so the desktop's own screenshot UI picks one."""
        if self.busy or self.recorder is not None or self.scroller is not None:
            return
        self.busy = True
        self._hold()
        self._reopen_launcher = self._hide_launcher()

        def got(surface, error):
            if surface is None:
                if error:
                    capture.show_error(self, error)
                self._end_capture(cancelled=True)
                return
            self.save_and_edit(surface)
            self._end_capture(cancelled=False)
        GLib.timeout_add(350, lambda: (capture.take_screenshot(True, got), False)[1])

    # ---------- Scrolling capture ----------

    def start_scroll(self, logical, rect, total_logical):
        from .scrollcapture import ScrollCaptureSession
        self.scroller = ScrollCaptureSession(self, logical, rect, total_logical, self._on_scroll_done)
        # Keep running while the portal's permission dialog is open (no window of ours is shown then).
        self.hold()
        self.scroller.start()

    def _on_scroll_done(self, surface, error):
        self.scroller = None
        GLib.idle_add(lambda: (self.release(), False)[1])
        if surface is not None:
            self.save_and_edit(surface)
        elif error:
            from .scrollcapture import show_error
            show_error(self, error)

    # ---------- Recording ----------

    def toggle_recording(self):
        if self.recorder is not None:
            self.recorder.stop()
        else:
            self.begin_capture("video")

    def start_recording(self, region, out_size, total_logical):
        from .recorder import RecordingSession
        self.recorder = RecordingSession(self, region=region, out_size=out_size, total_logical=total_logical,
                                         on_done=self._on_recording_done)
        # Keep running while the portal's screen picker is open (no window of ours is shown then).
        self.hold()
        self.recorder.start()

    def _on_recording_done(self, path, error):
        self.recorder = None
        GLib.idle_add(lambda: (self.release(), False)[1])
        if error:
            self._message(L.t("Không quay được video:\n") + error)
        elif path and os.path.exists(path):
            self.show_library(reveal=path)
            n = Gio.Notification.new(L.t("Đã lưu video"))
            n.set_body(os.path.basename(path))
            self.send_notification("video", n)


def main(argv):
    args = argv[1:]
    if "--selftest" in args:
        i = args.index("--selftest")
        outdir = args[i + 1] if i + 1 < len(args) else "selftest-out"
        from . import selftest
        return selftest.run(outdir)
    if "--help" in args or "-h" in args:
        print(USAGE)
        return 0
    if "--version" in args:
        print("MiniSnap " + VERSION)
        return 0
    app = MiniSnapApp()
    return app.run(argv)
