"""Global keyboard shortcuts through the xdg-desktop-portal GlobalShortcuts interface
(Hotkeys in windows/src/Hotkeys.cs). GNOME 48+ and KDE Plasma 6 ship the portal; older desktops
(Ubuntu 24.04 / GNOME 46) keep using custom shortcuts that run `minisnap --capture region` etc.

CreateSession -> BindShortcuts (the desktop shows its own dialog to confirm or change the keys) ->
ListShortcuts (the triggers the system really assigned). The Activated signal runs the same app
actions as the command-line options. The session lives as long as the app, so while shortcuts are
enabled the app holds itself and keeps running in the background.
"""

from . import _gi  # noqa: F401
from gi.repository import Gio, GLib

from . import portal, settings
from .i18n import L

IFACE = portal.GLOBAL_SHORTCUTS_IFACE
SETTING = "global_shortcuts_enabled"
NOTIFIED = "global_shortcuts_notified"

# shortcut id -> app action (the same actions the command-line options use).
ACTIONS = {
    "capture-region": "capture-region",
    "capture-full": "capture-full",
    "capture-scroll": "capture-scroll",
    "record": "record",
    "ocr": "ocr",
    "library": "library",
}


def shortcut_list():
    """(id, description, preferred trigger in the portal's syntax)."""
    return [
        ("capture-region", L.t("Chụp vùng / cửa sổ"), "CTRL+ALT+c"),
        ("capture-full", L.t("Chụp toàn màn hình"), "CTRL+ALT+f"),
        ("capture-scroll", L.t("Chụp cuộn trang dài"), "CTRL+ALT+s"),
        ("record", L.t("Quay video (bắt đầu / dừng)"), "CTRL+ALT+r"),
        ("ocr", L.t("Chụp và trích chữ (OCR)"), "CTRL+ALT+o"),
        ("library", L.t("Thư viện ảnh & video"), "CTRL+ALT+l"),
    ]


def bind_items():
    """Python value of BindShortcuts' a(sa{sv}) argument."""
    return [(sid, {"description": GLib.Variant("s", desc), "preferred_trigger": GLib.Variant("s", trig)})
            for sid, desc, trig in shortcut_list()]


def bind_variant():
    return GLib.Variant("a(sa{sv})", bind_items())


def bind_params(session, handle_token):
    """BindShortcuts(o session_handle, a(sa{sv}) shortcuts, s parent_window, a{sv} options)."""
    return GLib.Variant("(oa(sa{sv})sa{sv})",
                        (session, bind_items(), "", {"handle_token": GLib.Variant("s", handle_token)}))


def parse_shortcuts(items):
    """{id: trigger description} from the a(sa{sv}) the portal returns (unpacked)."""
    out = {}
    for item in items or []:
        try:
            sid, props = item
        except (TypeError, ValueError):
            continue
        props = dict(props or {})
        out[str(sid)] = str(props.get("trigger_description") or "")
    return out


def pretty_trigger(trigger):
    """'CTRL+ALT+c' -> 'Ctrl+Alt+C' (for suggestions shown before the system assigned anything)."""
    names = {"CTRL": "Ctrl", "ALT": "Alt", "SHIFT": "Shift", "LOGO": "Super", "NUM": "Num"}
    parts = [p for p in (trigger or "").split("+") if p]
    return "+".join(names.get(p.upper(), p.upper() if len(p) == 1 else p) for p in parts)


def dispatch(app, shortcut_id):
    """Runs the app action bound to a shortcut id; returns the action name (None if unknown)."""
    action = ACTIONS.get(shortcut_id)
    if action is not None:
        app.activate_action(action, None)
    return action


class GlobalShortcuts:
    """The app's GlobalShortcuts portal session. Listeners are called (without arguments) whenever
    the triggers or the state change, so the shortcuts window can refresh itself."""

    def __init__(self, app):
        self.app = app
        self.fake_version = None      # set by --selftest; never touches D-Bus then
        self._version = None
        self.conn = None
        self.session = None
        self.creating = False
        self.triggers = {}
        self.error = None
        self._held = False
        self._subs = []
        self._listeners = []

    # ---------- Availability ----------

    def version(self):
        if self.fake_version is not None:
            return self.fake_version
        if getattr(self.app, "selftest_dir", None):
            return 0
        if self._version is None:
            self._version = portal.interface_version(IFACE)
        return self._version

    @property
    def available(self):
        return self.version() > 0

    @staticmethod
    def enabled():
        return bool(settings.get(SETTING))

    # ---------- Listeners ----------

    def add_listener(self, fn):
        self._listeners.append(fn)

    def remove_listener(self, fn):
        if fn in self._listeners:
            self._listeners.remove(fn)

    def _changed(self):
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:  # noqa: BLE001 - a closed window must not break the others
                pass

    # ---------- Enable / disable ----------

    def set_enabled(self, enabled):
        """Raises OSError when the setting cannot be saved."""
        settings.set(SETTING, bool(enabled))
        if enabled:
            self.start()
            if not settings.get(NOTIFIED):
                n = Gio.Notification.new(L.t("MiniSnap chạy nền"))
                n.set_body(L.t("MiniSnap sẽ tiếp tục chạy nền để nhận phím tắt toàn cục, kể cả khi bạn đóng cửa sổ. Tắt trong menu ☰ → Bật phím tắt toàn cục."))
                self.app.send_notification("background", n)
                try:
                    settings.set(NOTIFIED, True)
                except OSError:
                    pass
        else:
            self.shutdown()
        self._changed()

    def _hold(self):
        if not self._held:
            self._held = True
            self.app.hold()

    def _release(self):
        if self._held:
            self._held = False
            self.app.release()

    # ---------- Portal session ----------

    def start(self):
        """Creates the session and binds the shortcuts (called at startup when enabled)."""
        if not self.available:
            return
        self._hold()
        if self.session or self.creating:
            return
        try:
            self.conn = portal.bus()
        except portal.PortalError as e:
            self._failed(str(e))
            return
        self.creating = True
        self.error = None
        if not self._subs:
            for name, cb in (("Activated", self._on_activated), ("ShortcutsChanged", self._on_shortcuts_changed)):
                # sender=None: signals come from the portal's unique name (see portal.py).
                self._subs.append(self.conn.signal_subscribe(None, IFACE, name, portal.OBJECT_PATH, None,
                                                             Gio.DBusSignalFlags.NONE, cb))
        token = portal.new_token()
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", portal.new_token("minisnap_shortcuts")),
        }
        portal.Request(self.conn, IFACE, "CreateSession", GLib.Variant("(a{sv})", (options,)), token,
                       self._on_created)

    def _failed(self, message):
        self.creating = False
        self.error = message
        self._release()
        self._changed()

    def _on_created(self, code, results):
        self.creating = False
        if code != 0:
            self._failed(None if code == 1 else (results.get("error") or "GlobalShortcuts: response %d" % code))
            return
        self.session = results.get("session_handle")
        if not self.session:
            self._failed("GlobalShortcuts: no session handle")
            return
        if not self.enabled():          # switched off while the portal was answering
            self.close()
            return
        self.bind()

    def bind(self):
        if not self.session:
            return
        token = portal.new_token()
        portal.Request(self.conn, IFACE, "BindShortcuts", bind_params(self.session, token), token, self._on_bound)

    def _on_bound(self, code, results):
        if code == 0:
            self.triggers.update(parse_shortcuts(results.get("shortcuts")))
            self.error = None
        elif code != 1:
            self.error = results.get("error") or "GlobalShortcuts: response %d" % code
        self._changed()
        self.list_shortcuts()

    def list_shortcuts(self):
        if not self.session:
            return
        token = portal.new_token()
        portal.Request(self.conn, IFACE, "ListShortcuts",
                       GLib.Variant("(oa{sv})", (self.session, {"handle_token": GLib.Variant("s", token)})),
                       token, self._on_listed)

    def _on_listed(self, code, results):
        if code == 0:
            self.triggers = parse_shortcuts(results.get("shortcuts"))
            self._changed()

    def configure(self):
        """'Register / change keys…': the desktop shows its own dialog."""
        if not self.enabled():
            self.set_enabled(True)        # starts the session, BindShortcuts shows the dialog
            return
        if not self.session:
            self.start()
            return
        if self.version() >= 2:
            def done(conn, res, *_):
                try:
                    conn.call_finish(res)
                except GLib.Error:
                    self._rebind()
            self.conn.call(portal.BUS_NAME, portal.OBJECT_PATH, IFACE, "ConfigureShortcuts",
                           GLib.Variant("(osa{sv})", (self.session, "", {})), None,
                           Gio.DBusCallFlags.NONE, -1, None, done)
        else:
            self._rebind()

    def _rebind(self):
        """Version 1 has no ConfigureShortcuts: a new session binds (and asks) again."""
        portal.close_session(self.conn, self.session)
        self.session = None
        self.start()

    # ---------- Signals ----------

    def _on_activated(self, conn, sender, path, iface, signal, params, *_):
        try:
            session, shortcut_id, _timestamp, _options = params.unpack()
        except (TypeError, ValueError):
            return
        if not self.session or session != self.session:
            return
        dispatch(self.app, shortcut_id)

    def _on_shortcuts_changed(self, conn, sender, path, iface, signal, params, *_):
        try:
            session, items = params.unpack()
        except (TypeError, ValueError):
            return
        if self.session and session == self.session:
            self.triggers = parse_shortcuts(items)
            self._changed()

    # ---------- Shutdown ----------

    def close(self):
        if self.conn is not None:
            for sub in self._subs:
                self.conn.signal_unsubscribe(sub)
        self._subs = []
        portal.close_session(self.conn, self.session)
        self.session = None
        self.creating = False

    def shutdown(self):
        """Disable (or quit): close the session and stop keeping the app alive."""
        self.close()
        self.triggers = {}
        self._release()
