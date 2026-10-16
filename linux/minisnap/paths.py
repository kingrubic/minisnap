"""Library folders: ~/Pictures/MiniSnap and ~/Videos/MiniSnap (XDG user dirs)."""

import datetime
import os

from . import _gi  # noqa: F401
from gi.repository import Gio, GLib

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
VIDEO_EXTS = (".mp4", ".webm", ".mkv")


def in_flatpak():
    """True inside the Flatpak sandbox (Flathub delivers the updates there)."""
    return bool(os.environ.get("FLATPAK_ID")) or os.path.exists("/.flatpak-info")


def _ensure(kind):
    # MINISNAP_LIBRARY redirects the library (used by --selftest so it never touches real captures).
    over = os.environ.get("MINISNAP_LIBRARY")
    if over:
        folder = os.path.join(over, "Pictures" if kind == "pictures" else "Videos")
    else:
        special = GLib.UserDirectory.DIRECTORY_PICTURES if kind == "pictures" else GLib.UserDirectory.DIRECTORY_VIDEOS
        root = GLib.get_user_special_dir(special)
        if not root:
            root = os.path.join(os.path.expanduser("~"), "Pictures" if kind == "pictures" else "Videos")
        folder = os.path.join(root, "MiniSnap")
    os.makedirs(folder, exist_ok=True)
    return folder


def images_folder():
    return _ensure("pictures")


def videos_folder():
    return _ensure("videos")


def _unique(folder, ext):
    name = "MiniSnap_" + datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    p = os.path.join(folder, name + ext)
    i = 2
    while os.path.exists(p):
        p = os.path.join(folder, "%s_%d%s" % (name, i, ext))
        i += 1
    return p


def new_image_path():
    return _unique(images_folder(), ".png")


def new_video_path(ext=".mp4"):
    return _unique(videos_folder(), ext)


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def is_video(path):
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def all_files():
    """(path, mtime, size) of every capture, newest first."""
    out = []
    for folder, test in ((images_folder(), is_image), (videos_folder(), is_video)):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for n in names:
            p = os.path.join(folder, n)
            if not test(n):
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            if os.path.isfile(p):
                out.append((p, st.st_mtime, st.st_size))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


def file_uri(path):
    return Gio.File.new_for_path(path).get_uri()


def open_uri(uri, parent=None):
    """Opens a file, folder or web link with the default app. Returns an error message or None."""
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
        return None
    except GLib.Error as e:
        return e.message


def open_folder(folder):
    return open_uri(file_uri(folder))


def show_in_folder(path):
    """Selects the file in the file manager (org.freedesktop.FileManager1), else opens its folder."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        bus = None
    if bus is None:
        open_folder(os.path.dirname(path))
        return

    def done(conn, res, *_):
        try:
            conn.call_finish(res)
        except GLib.Error:
            open_folder(os.path.dirname(path))

    bus.call("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1", "org.freedesktop.FileManager1",
             "ShowItems", GLib.Variant("(ass)", ([file_uri(path)], "")), None,
             Gio.DBusCallFlags.NONE, 5000, None, done)
