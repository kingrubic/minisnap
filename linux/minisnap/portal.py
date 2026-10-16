"""xdg-desktop-portal helpers over Gio.DBus: Screenshot and ScreenCast.

Portal methods return a Request object path at once and deliver their result later through the
org.freedesktop.portal.Request::Response signal. We subscribe to the predicted request path
(built from our unique bus name and a handle_token) *before* calling, so the answer can't be
missed, and re-subscribe if an old portal returns a different path.
Response codes: 0 = success, 1 = cancelled by the user, 2 = other error.
"""

import itertools
import os

from . import _gi  # noqa: F401
from gi.repository import Gio, GLib

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
SESSION_IFACE = "org.freedesktop.portal.Session"

SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
CURSOR_HIDDEN = 1
CURSOR_EMBEDDED = 2
CURSOR_METADATA = 4

_counter = itertools.count(1)


class PortalError(Exception):
    pass


def _bus():
    try:
        return Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as e:
        raise PortalError(e.message)


def new_token(prefix="minisnap"):
    return "%s_%d_%d" % (prefix, os.getpid(), next(_counter))


def _request_path(conn, token):
    sender = conn.get_unique_name().lstrip(":").replace(".", "_")
    return "%s/request/%s/%s" % (OBJECT_PATH, sender, token)


class _Request:
    """One portal call that answers through a Request::Response signal."""

    def __init__(self, conn, iface, method, params, token, callback):
        self.conn = conn
        self.callback = callback
        self.done = False
        self.sub_id = 0
        self._subscribe(_request_path(conn, token))
        conn.call(BUS_NAME, OBJECT_PATH, iface, method, params, GLib.VariantType.new("(o)"),
                  Gio.DBusCallFlags.NONE, -1, None, self._on_reply)

    def _subscribe(self, path):
        if self.sub_id:
            self.conn.signal_unsubscribe(self.sub_id)
        self.path = path
        # sender=None: the signal comes from the portal's unique name, not the well-known one.
        self.sub_id = self.conn.signal_subscribe(None, REQUEST_IFACE, "Response", path, None,
                                                 Gio.DBusSignalFlags.NONE, self._on_response)

    def _unsubscribe(self):
        if self.sub_id:
            self.conn.signal_unsubscribe(self.sub_id)
            self.sub_id = 0

    def _on_reply(self, conn, res, *_):
        try:
            ret = conn.call_finish(res)
        except GLib.Error as e:
            self._finish(2, {"error": e.message})
            return
        handle = ret.unpack()[0]
        if handle != self.path and not self.done:
            self._subscribe(handle)

    def _on_response(self, conn, sender, path, iface, signal, params, *_):
        code, results = params.unpack()
        self._finish(code, results)

    def _finish(self, code, results):
        if self.done:
            return
        self.done = True
        self._unsubscribe()
        self.callback(int(code), results or {})


# ---------- Screenshot ----------

def screenshot(interactive, callback):
    """Asks the portal for a screenshot. callback(uri, error): uri None + error None = cancelled."""
    try:
        conn = _bus()
    except PortalError as e:
        GLib.idle_add(lambda: (callback(None, str(e)), False)[1])
        return
    token = new_token()
    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", bool(interactive)),
        "modal": GLib.Variant("b", True),
    }

    def done(code, results):
        if code == 0 and results.get("uri"):
            callback(results["uri"], None)
        elif code == 1:
            callback(None, None)
        else:
            callback(None, results.get("error") or "xdg-desktop-portal Screenshot: response %d" % code)

    _Request(conn, SCREENSHOT_IFACE, "Screenshot", GLib.Variant("(sa{sv})", ("", options)), token, done)


# ---------- ScreenCast ----------

class ScreenCastSession:
    """CreateSession -> SelectSources -> Start -> OpenPipeWireRemote.

    on_ready(fd, node_id, stream_props) or on_error(message) (message None = cancelled).
    Keep the object alive while recording and call close() afterwards."""

    def __init__(self):
        self.conn = None
        self.session = None
        self.closed = False

    def start(self, on_ready, on_error, cursor=True):
        self.on_ready = on_ready
        self.on_error = on_error
        try:
            self.conn = _bus()
        except PortalError as e:
            GLib.idle_add(lambda: (on_error(str(e)), False)[1])
            return
        self.cursor_modes = self._available_cursor_modes() if cursor else 0
        token = new_token()
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", new_token("minisnap_session")),
        }
        _Request(self.conn, SCREENCAST_IFACE, "CreateSession", GLib.Variant("(a{sv})", (options,)), token,
                 self._on_created)

    def _available_cursor_modes(self):
        try:
            ret = self.conn.call_sync(BUS_NAME, OBJECT_PATH, "org.freedesktop.DBus.Properties", "Get",
                                      GLib.Variant("(ss)", (SCREENCAST_IFACE, "AvailableCursorModes")),
                                      GLib.VariantType.new("(v)"), Gio.DBusCallFlags.NONE, 3000, None)
            return int(ret.unpack()[0])
        except (GLib.Error, TypeError, ValueError):
            return 0

    def _fail(self, code, results):
        self.close()
        self.on_error(None if code == 1 else (results.get("error") or "xdg-desktop-portal ScreenCast: response %d" % code))

    def _on_created(self, code, results):
        if code != 0:
            self._fail(code, results)
            return
        self.session = results.get("session_handle")
        if not self.session:
            self._fail(2, {"error": "xdg-desktop-portal: no session handle"})
            return
        token = new_token()
        options = {
            "handle_token": GLib.Variant("s", token),
            "types": GLib.Variant("u", SOURCE_MONITOR),
            "multiple": GLib.Variant("b", False),
        }
        if self.cursor_modes & CURSOR_EMBEDDED:
            options["cursor_mode"] = GLib.Variant("u", CURSOR_EMBEDDED)
        _Request(self.conn, SCREENCAST_IFACE, "SelectSources",
                 GLib.Variant("(oa{sv})", (self.session, options)), token, self._on_selected)

    def _on_selected(self, code, results):
        if code != 0:
            self._fail(code, results)
            return
        token = new_token()
        options = {"handle_token": GLib.Variant("s", token)}
        _Request(self.conn, SCREENCAST_IFACE, "Start",
                 GLib.Variant("(osa{sv})", (self.session, "", options)), token, self._on_started)

    def _on_started(self, code, results):
        if code != 0:
            self._fail(code, results)
            return
        streams = results.get("streams") or []
        if not streams:
            self._fail(2, {"error": "xdg-desktop-portal: no stream was shared"})
            return
        node_id, props = streams[0]
        try:
            ret, fds = self.conn.call_with_unix_fd_list_sync(
                BUS_NAME, OBJECT_PATH, SCREENCAST_IFACE, "OpenPipeWireRemote",
                GLib.Variant("(oa{sv})", (self.session, {})), GLib.VariantType.new("(h)"),
                Gio.DBusCallFlags.NONE, -1, None, None)
            index = ret.get_child_value(0).get_handle()
            fd = fds.get(index)
        except GLib.Error as e:
            self._fail(2, {"error": e.message})
            return
        self.on_ready(fd, int(node_id), dict(props or {}))

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.conn is not None and self.session:
            try:
                self.conn.call(BUS_NAME, self.session, SESSION_IFACE, "Close", None, None,
                               Gio.DBusCallFlags.NONE, -1, None, None)
            except GLib.Error:
                pass
