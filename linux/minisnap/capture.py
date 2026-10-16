"""Full-desktop screenshot through the xdg-desktop-portal Screenshot interface.

Works on Wayland and X11 and inside Flatpak. The result is a cairo ImageSurface of the whole
desktop (all monitors), in pixels.
"""

import os
import time

from . import _gi  # noqa: F401
from gi.repository import Adw, Gio, GLib, GdkPixbuf

from . import paths, portal, render
from .i18n import L


class Denied(str):
    """Error text for a screenshot the portal refused (response 2), as opposed to a portal that failed."""


# The desktop refused a silent grab in this run: go straight to its screenshot UI from now on.
_silent_denied = False


def take_screenshot(interactive, callback, on_fallback=None):
    """callback(surface, error_text, used_ui). surface None and error None means the user cancelled.

    interactive=False: silent full-desktop grab (used before the selection overlay).
    interactive=True: the desktop's own screenshot UI, where the user can pick a window.
    When the desktop refuses the silent grab (GNOME does for an app it has no permission for, or after
    the user answered "Deny"), the request is repeated with the screenshot UI, which needs no stored
    permission; on_fallback() is called then. used_ui tells the caller which of the two answered."""
    started = time.time()

    def attempt(ui):
        def got(uri, error, denied):
            global _silent_denied
            if uri is None:
                if denied and not ui:
                    _silent_denied = True
                    if on_fallback is not None:
                        on_fallback()
                    attempt(True)
                    return
                callback(None, Denied(error) if denied else error, ui)
                return
            f = Gio.File.new_for_uri(uri)
            path = f.get_path()
            try:
                if path:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
                else:
                    ok, data, _etag = f.load_contents(None)
                    loader = GdkPixbuf.PixbufLoader()
                    loader.write(data)
                    loader.close()
                    pixbuf = loader.get_pixbuf()
                surface = render.surface_from_pixbuf(pixbuf)
            except (GLib.Error, OSError) as e:
                callback(None, getattr(e, "message", str(e)), ui)
                return
            if path:
                _cleanup_portal_file(path, started)
            callback(surface, None, ui)

        portal.screenshot(ui, got)

    attempt(bool(interactive or _silent_denied))


def forget_denial():
    global _silent_denied
    _silent_denied = False


def _cleanup_portal_file(path, started):
    """Some portal backends (GNOME) save every screenshot as ~/Pictures/Screenshot*.png. The file was
    created only for us, so remove it; we keep our own copy in the MiniSnap library.
    Only files created during this request and outside the library are touched."""
    try:
        name = os.path.basename(path)
        lib = os.path.realpath(paths.images_folder())
        if os.path.realpath(path).startswith(lib + os.sep):
            return
        if not name.lower().startswith("screenshot"):
            return
        if os.path.getmtime(path) < started - 2:
            return
        os.unlink(path)
    except OSError:
        pass


def show_message(app, heading, body):
    dlg = Adw.MessageDialog(heading=heading, body=body)
    parent = app.get_active_window() if app is not None else None
    if parent is not None:
        dlg.set_transient_for(parent)
    if app is not None:
        dlg.set_application(app)
    dlg.add_response("close", L.t("Đóng"))
    dlg.set_close_response("close")
    dlg.present()
    return dlg


def show_error(app, detail, retry=None):
    """Friendly explanation when the portal is missing or refused the screenshot.

    A refusal (Denied) usually means a stored "Deny" answer: outside Flatpak the dialog offers to
    delete it, so the system asks again, and then calls retry()."""
    parent = app.get_active_window() if app is not None else None
    denied = isinstance(detail, Denied)
    can_reset = denied and not paths.in_flatpak()
    if denied:
        body = L.t("Hệ thống đã từ chối cho MiniSnap chụp màn hình. Thường là do trước đây đã chọn “Từ chối” ở hộp thoại hỏi quyền chụp màn hình.")
        if can_reset:
            body += "\n\n" + L.t("Bấm “Hỏi lại quyền” để xoá lựa chọn cũ, rồi chọn “Cho phép” khi hệ thống hỏi.")
        else:
            body += "\n\n" + L.t("Hãy cấp lại quyền chụp màn hình cho MiniSnap bằng lệnh:") + \
                "\nflatpak permission-remove screenshot screenshot " + portal.APP_ID
    else:
        body = L.t("MiniSnap chụp màn hình qua xdg-desktop-portal. Hãy kiểm tra gói xdg-desktop-portal và xdg-desktop-portal-gnome (hoặc -kde, -wlr) đã được cài, rồi thử lại.")
    if detail:
        body += "\n\n" + str(detail)
    dlg = Adw.MessageDialog(heading=L.t("Không chụp được màn hình"), body=body)
    dlg.set_body_use_markup(False)
    if parent is not None:
        dlg.set_transient_for(parent)
    if app is not None:
        dlg.set_application(app)
    dlg.add_response("close", L.t("Đóng"))
    if can_reset:
        dlg.add_response("reset", L.t("Hỏi lại quyền"))
        dlg.set_response_appearance("reset", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("reset")
    else:
        dlg.set_default_response("close")
    dlg.set_close_response("close")

    def on_response(_dlg, response):
        if response != "reset":
            return
        portal.reset_screenshot_permission()
        forget_denial()
        if retry is not None:
            GLib.timeout_add(300, lambda: (retry(), False)[1])
    dlg.connect("response", on_response)
    dlg.present()
    return dlg
