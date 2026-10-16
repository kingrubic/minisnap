"""xdg-desktop-portal helpers over Gio.DBus: Screenshot, ScreenCast and the pieces shared with
RemoteDesktop (scrolling capture) and GlobalShortcuts.

Portal methods return a Request object path at once and deliver their result later through the
org.freedesktop.portal.Request::Response signal. We subscribe to the predicted request path
(built from our unique bus name and a handle_token) *before* calling, so the answer can't be
missed, and re-subscribe if an old portal returns a different path.
Response codes: 0 = success, 1 = cancelled by the user, 2 = other error.

Outside Flatpak the portal cannot tell which app is calling. Where it offers the host Registry
(xdg-desktop-portal 1.19+, and Ubuntu 24.04's 1.18 backport) MiniSnap registers its app id first, on
a private connection of its own: the registration must be the connection's first portal call, and
GTK has already used the shared connection. The portal then asks the user about "MiniSnap" instead
of refusing an app with no id (GNOME 46 answers a silent screenshot from one with response 2).
"""

import itertools
import os

from . import _gi  # noqa: F401
from gi.repository import Gio, GLib

from . import APP_ID, paths

BUS_NAME = "org.freedesktop.portal.Desktop"
OBJECT_PATH = "/org/freedesktop/portal/desktop"
REGISTRY_IFACE = "org.freedesktop.host.portal.Registry"
PERMISSION_STORE_NAME = "org.freedesktop.impl.portal.PermissionStore"
PERMISSION_STORE_PATH = "/org/freedesktop/impl/portal/PermissionStore"
PERMISSION_STORE_IFACE = "org.freedesktop.impl.portal.PermissionStore"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SCREENSHOT_IFACE = "org.freedesktop.portal.Screenshot"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
SESSION_IFACE = "org.freedesktop.portal.Session"
REMOTE_DESKTOP_IFACE = "org.freedesktop.portal.RemoteDesktop"
GLOBAL_SHORTCUTS_IFACE = "org.freedesktop.portal.GlobalShortcuts"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"

SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
CURSOR_HIDDEN = 1
CURSOR_EMBEDDED = 2
CURSOR_METADATA = 4
DEVICE_KEYBOARD = 1
DEVICE_POINTER = 2
PERSIST_UNTIL_REVOKED = 2

_counter = itertools.count(1)
_conn = None
registered = False      # the portal knows us as APP_ID (host Registry)


class PortalError(Exception):
    pass


def _bus():
    global _conn
    if _conn is not None and not _conn.is_closed():
        return _conn
    try:
        shared = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error as e:
        raise PortalError(e.message)
    _conn = _registered_connection() or shared
    return _conn


def _registered_connection():
    """A private session-bus connection registered as APP_ID, or None (Flatpak, which identifies the app
    itself, or a portal without the host Registry)."""
    global registered
    registered = False
    if paths.in_flatpak():
        return None
    try:
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        conn = Gio.DBusConnection.new_for_address_sync(
            address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
    except GLib.Error:
        return None
    try:
        conn.call_sync(BUS_NAME, OBJECT_PATH, REGISTRY_IFACE, "Register",
                       GLib.Variant("(sa{sv})", (APP_ID, {})), None, Gio.DBusCallFlags.NONE, 5000, None)
    except GLib.Error:
        try:
            conn.close_sync(None)
        except GLib.Error:
            pass
        return None
    registered = True
    return conn


def reset():
    """Forgets the portal connection; the next call connects (and registers) again. Used by the self-test."""
    global _conn, registered
    # Only the private connection is ours to close; closing the shared one would end the app.
    if _conn is not None and registered:
        try:
            _conn.close_sync(None)
        except GLib.Error:
            pass
    _conn = None
    registered = False


def bus():
    """The portal connection (registered as APP_ID when possible); raises PortalError without a session bus."""
    return _bus()


def get_property(conn, iface, name, timeout=3000):
    """A portal property (e.g. an interface's `version`), or None when the interface or the property
    does not exist (an old portal or a backend without that interface)."""
    try:
        ret = conn.call_sync(BUS_NAME, OBJECT_PATH, PROPERTIES_IFACE, "Get",
                             GLib.Variant("(ss)", (iface, name)), GLib.VariantType.new("(v)"),
                             Gio.DBusCallFlags.NONE, timeout, None)
    except GLib.Error:
        return None
    try:
        return ret.unpack()[0]
    except (TypeError, IndexError):
        return None


def interface_version(iface, conn=None):
    """The portal interface's version, 0 when it is missing (or there is no session bus)."""
    try:
        conn = conn or _bus()
    except PortalError:
        return 0
    v = get_property(conn, iface, "version")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def open_pipewire_remote(conn, session):
    """ScreenCast.OpenPipeWireRemote: a new file descriptor for the session's PipeWire remote.
    Raises GLib.Error. The caller owns (and should close) the descriptor."""
    ret, fds = conn.call_with_unix_fd_list_sync(
        BUS_NAME, OBJECT_PATH, SCREENCAST_IFACE, "OpenPipeWireRemote",
        GLib.Variant("(oa{sv})", (session, {})), GLib.VariantType.new("(h)"),
        Gio.DBusCallFlags.NONE, -1, None, None)
    index = ret.get_child_value(0).get_handle()
    return fds.get(index)


def close_session(conn, session):
    """org.freedesktop.portal.Session.Close, fire and forget."""
    if conn is None or not session:
        return
    try:
        conn.call(BUS_NAME, session, SESSION_IFACE, "Close", None, None,
                  Gio.DBusCallFlags.NONE, -1, None, None)
    except GLib.Error:
        pass


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


# Public name for the other portal clients (scrollcapture.py, globalshortcuts.py).
Request = _Request


# ---------- Screenshot ----------

def screenshot(interactive, callback):
    """Asks the portal for a screenshot. callback(uri, error, denied): uri None + error None = cancelled;
    denied = the portal answered "no" (response 2), as opposed to a failed call."""
    try:
        conn = _bus()
    except PortalError as e:
        GLib.idle_add(lambda: (callback(None, str(e), False), False)[1])
        return
    token = new_token()
    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", bool(interactive)),
        "modal": GLib.Variant("b", True),
    }

    def done(code, results):
        if code == 0 and results.get("uri"):
            callback(results["uri"], None, False)
        elif code == 1:
            callback(None, None, False)
        else:
            # _Request puts "error" in the results only when the call itself failed.
            callback(None, results.get("error") or "xdg-desktop-portal Screenshot: response %d" % code,
                     code == 2 and "error" not in results)

    _Request(conn, SCREENSHOT_IFACE, "Screenshot", GLib.Variant("(sa{sv})", ("", options)), token, done)


def reset_screenshot_permission():
    """Deletes the stored answer to the portal's "Allow … to take screenshots?" question for this app
    (APP_ID once registered, else the empty id of unidentified host apps), so the portal asks again.
    True when an entry was removed. Not possible from inside Flatpak (no access to the permission store)."""
    try:
        conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except GLib.Error:
        return False
    try:
        conn.call_sync(PERMISSION_STORE_NAME, PERMISSION_STORE_PATH, PERMISSION_STORE_IFACE, "DeletePermission",
                       GLib.Variant("(sss)", ("screenshot", "screenshot", APP_ID if registered else "")),
                       None, Gio.DBusCallFlags.NONE, 3000, None)
    except GLib.Error:
        return False
    return True


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
        return available_cursor_modes(self.conn)

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
            fd = open_pipewire_remote(self.conn, self.session)
        except GLib.Error as e:
            self._fail(2, {"error": e.message})
            return
        self.on_ready(fd, int(node_id), dict(props or {}))

    def close(self):
        if self.closed:
            return
        self.closed = True
        close_session(self.conn, self.session)


def available_cursor_modes(conn):
    """ScreenCast AvailableCursorModes bitmask (0 when unknown)."""
    v = get_property(conn, SCREENCAST_IFACE, "AvailableCursorModes")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0
