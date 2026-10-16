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


def take_screenshot(interactive, callback):
    """callback(surface, error_text). surface None and error None means the user cancelled.

    interactive=False: silent full-desktop grab (used before the selection overlay).
    interactive=True: the desktop's own screenshot UI, where the user can pick a window."""
    started = time.time()

    def got(uri, error):
        if uri is None:
            callback(None, error)
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
            callback(None, getattr(e, "message", str(e)))
            return
        if path:
            _cleanup_portal_file(path, started)
        callback(surface, None)

    portal.screenshot(interactive, got)


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


def show_error(app, detail):
    """Friendly explanation when the portal is missing or refused the screenshot."""
    parent = app.get_active_window() if app is not None else None
    body = L.t("MiniSnap chụp màn hình qua xdg-desktop-portal. Hãy kiểm tra gói xdg-desktop-portal và xdg-desktop-portal-gnome (hoặc -kde, -wlr) đã được cài, rồi thử lại.")
    if detail:
        body += "\n\n" + str(detail)
    dlg = Adw.MessageDialog(heading=L.t("Không chụp được màn hình"), body=body)
    if parent is not None:
        dlg.set_transient_for(parent)
    if app is not None:
        dlg.set_application(app)
    dlg.add_response("close", L.t("Đóng"))
    dlg.set_default_response("close")
    dlg.set_close_response("close")
    dlg.present()
    return dlg
