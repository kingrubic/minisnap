"""Scrolling capture on Wayland and X11 (ScrollCaptureSession in windows/src/ScrollCapture.cs).

Windows moves the real cursor and sends wheel input; Linux desktops only allow that through the
xdg-desktop-portal RemoteDesktop interface. One portal session carries both the pointer device and
a ScreenCast stream of the monitor:

  RemoteDesktop.CreateSession -> RemoteDesktop.SelectDevices(POINTER, persist) ->
  ScreenCast.SelectSources(MONITOR) -> RemoteDesktop.Start -> ScreenCast.OpenPipeWireRemote

Frames come from `pipewiresrc ! videoconvert ! BGRx ! appsink` (only the newest buffer is kept and
pulled when a frame is needed); the selected region is cropped from the monitor frame and fed to
the row-matching stitcher (stitcher.py). The pointer is moved to the centre of the region with
NotifyPointerMotionAbsolute and scrolled with NotifyPointerAxisDiscrete (NotifyPointerAxis as a
fallback). The portal's restore token is saved so the permission dialog is not shown every time.

ScrollStateMachine is the pure part (timing, retries, adaptive step) shared by the real session and
the self-test, which drives it with a synthetic page.
"""

import os
import sys

import cairo

from . import _gi
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import icons, portal, render, settings
from .i18n import L
from .stitcher import NO_MATCH, NO_MOVEMENT, ScrollStitcher

if _gi.HAVE_GST:
    from gi.repository import Gst
else:  # pragma: no cover - reported to the user when scrolling capture starts
    Gst = None

MAX_HEIGHT, MAX_FRAMES = 30000, 120
START_MS, SETTLE_MS, RETRY_MS = 250, 450, 200
MAX_EMPTY_GRABS = 25            # about 5 s without any frame from PipeWire
PULL_TIMEOUT_NS = 100 * 1000 * 1000
TOKEN_KEY = "remote_desktop_restore_token"
AXIS_VERTICAL = 0
SMOOTH_STEP = 15.0              # NotifyPointerAxis pixels per notch (fallback path)
# videoconvert output with the same memory layout as cairo FORMAT_RGB24 on this machine.
FRAME_FORMAT = "BGRx" if sys.byteorder == "little" else "xRGB"


# ---------- Pure state machine ----------

class ScrollStateMachine:
    """Same steps as ScrollCaptureSession.Step on Windows.

    grab_frame() -> cairo surface or None (no frame yet); scroll(notches), positive = down;
    schedule(ms, fn) runs fn later; done(surface or None) is called exactly once;
    progress(frame_count, total_height) after every accepted frame."""

    def __init__(self, view_height, grab_frame, scroll, schedule, done, progress=None):
        self.grab_frame = grab_frame
        self.scroll = scroll
        self.schedule = schedule
        self.done = done
        self.progress = progress
        self.stitcher = ScrollStitcher()
        self.notches = 1 if view_height < 350 else 3
        self.pending = 0
        self.failures = 0
        self.empty_grabs = 0
        self.finished = False

    def start(self):
        # Let the selection overlay disappear first.
        self.schedule(START_MS, self._step)

    def stop(self):
        """Stop button / Esc: keep what has been captured so far."""
        self.finish()

    def abort(self):
        """Error path: drop everything without calling done()."""
        self.finished = True
        self.stitcher.dispose_frames()

    def _wait(self, ms):
        self.schedule(ms, self._step)

    def _step(self):
        if self.finished:
            return
        if self.pending:
            self.scroll(self.pending)
            self.pending = 0
            self._wait(SETTLE_MS)
            return

        frame = self.grab_frame()
        if self.finished:
            return
        if frame is None:
            self.empty_grabs += 1
            if self.empty_grabs > MAX_EMPTY_GRABS:
                self.finish()
                return
            self._wait(RETRY_MS)
            return

        st = self.stitcher
        if st.frame_count == 0:
            st.add_first(frame)
        else:
            outcome = st.add(frame)
            if outcome == NO_MOVEMENT:
                self.finish()
                return
            if outcome == NO_MATCH:
                # Probably scrolled further than one screen: go back and retry with a smaller step.
                if self.failures < 2 and self.notches > 1:
                    self.failures += 1
                    self.scroll(-self.notches)
                    self.notches = max(1, self.notches // 2)
                    self.pending = self.notches
                    self._wait(SETTLE_MS)
                    return
                self.finish()
                return
            self.failures = 0
            per_notch = st.last_shift / float(self.notches)
            if per_notch > 0:
                self.notches = max(1, min(10, int(st.last_usable_height * 0.6 / per_notch)))
        if self.progress is not None:
            self.progress(st.frame_count, st.total_height)
        if st.total_height >= MAX_HEIGHT or st.frame_count >= MAX_FRAMES:
            self.finish()
            return
        self.scroll(self.notches)
        self._wait(SETTLE_MS)

    def finish(self):
        if self.finished:
            return
        self.finished = True
        result = self.stitcher.compose() if self.stitcher.frame_count > 0 else None
        self.stitcher.dispose_frames()
        self.done(result)


# ---------- Pure portal helpers (tested by --selftest without D-Bus) ----------

def select_devices_options(version, restore_token, handle_token):
    """RemoteDesktop.SelectDevices options: pointer only; persistence needs interface version 2."""
    options = {
        "handle_token": GLib.Variant("s", handle_token),
        "types": GLib.Variant("u", portal.DEVICE_POINTER),
    }
    if version >= 2:
        options["persist_mode"] = GLib.Variant("u", portal.PERSIST_UNTIL_REVOKED)
        if restore_token:
            options["restore_token"] = GLib.Variant("s", restore_token)
    return options


def parse_start_response(results):
    """(devices or None, streams, restore_token or None) from RemoteDesktop.Start's results.

    Each stream is a dict: node (PipeWire node id), position (x, y) and size (w, h) in logical
    units or None when the portal does not say, source_type."""
    streams = []
    for item in results.get("streams") or []:
        try:
            node, props = item
            node = int(node)
        except (TypeError, ValueError):
            continue
        props = dict(props or {})
        pos = props.get("position")
        size = props.get("size")
        try:
            pos = (int(pos[0]), int(pos[1])) if pos is not None else None
        except (TypeError, IndexError, ValueError):
            pos = None
        try:
            size = (int(size[0]), int(size[1])) if size is not None else None
        except (TypeError, IndexError, ValueError):
            size = None
        if size is not None and (size[0] <= 0 or size[1] <= 0):
            size = None
        streams.append({"node": node, "position": pos, "size": size,
                        "source_type": int(props.get("source_type") or 0)})
    devices = results.get("devices")
    try:
        devices = int(devices) if devices is not None else None
    except (TypeError, ValueError):
        devices = None
    token = results.get("restore_token") or None
    return devices, streams, token


def pixels_to_logical(rect, info):
    """Screenshot pixels -> global logical units (info = CaptureOverlay.info)."""
    ox, oy, sx, sy = info
    return (ox + rect[0] / sx, oy + rect[1] / sy, rect[2] / sx, rect[3] / sy)


def stream_rect(stream, total_logical):
    """The stream's monitor in global logical units (the whole desktop when the portal gives no size)."""
    size = stream.get("size") if stream else None
    if size:
        pos = stream.get("position") or (0, 0)
        return (pos[0], pos[1], size[0], size[1])
    return tuple(total_logical)


def selection_to_stream(logical, stream, frame_w, frame_h, total_logical):
    """(x, y, w, h) in stream pixels for a logical selection, clipped to the frame; None when the
    selection is (almost) not on the shared monitor."""
    sx0, sy0, sw, sh = stream_rect(stream, total_logical)
    if sw <= 0 or sh <= 0:
        return None
    kx, ky = frame_w / float(sw), frame_h / float(sh)
    x1 = int(round((logical[0] - sx0) * kx))
    y1 = int(round((logical[1] - sy0) * ky))
    x2 = int(round((logical[0] + logical[2] - sx0) * kx))
    y2 = int(round((logical[1] + logical[3] - sy0) * ky))
    x1, x2 = max(0, min(frame_w, x1)), max(0, min(frame_w, x2))
    y1, y2 = max(0, min(frame_h, y1)), max(0, min(frame_h, y2))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return (x1, y1, x2 - x1, y2 - y1)


def pointer_position(logical, stream, total_logical):
    """Centre of the selection in the stream's logical coordinates (NotifyPointerMotionAbsolute)."""
    sx0, sy0, sw, sh = stream_rect(stream, total_logical)
    x = logical[0] + logical[2] / 2.0 - sx0
    y = logical[1] + logical[3] / 2.0 - sy0
    return (max(0.0, min(sw - 1.0, x)), max(0.0, min(sh - 1.0, y)))


def surface_from_bgrx(data, w, h, stride, rect):
    """Cairo ARGB32 copy of `rect` from a BGRx (little endian; xRGB on big endian) frame."""
    if w <= 0 or h <= 0:
        return None
    if not stride:
        stride = len(data) // h
    if stride < w * 4 or stride % 4 or len(data) < stride * (h - 1) + w * 4:
        return None
    buf = bytearray(data)
    if len(buf) < stride * h:
        buf.extend(bytes(stride * h - len(buf)))
    full = cairo.ImageSurface.create_for_data(buf, cairo.FORMAT_RGB24, w, h, stride)
    # render.crop paints with OPERATOR_SOURCE onto ARGB32: an RGB24 source becomes opaque.
    out = render.crop(full, rect)
    full.finish()
    return out


def buffer_bytes(buf):
    """The bytes of a Gst.Buffer, with or without the gst-python overrides installed."""
    try:
        data = buf.extract_dup(0, buf.get_size())
        if data:
            return bytes(data)
    except Exception:  # noqa: BLE001 - fall back to mapping
        pass
    res = buf.map(Gst.MapFlags.READ)
    if isinstance(res, tuple):
        ok, info = res
        if not ok:
            return None
    else:
        info = res
    try:
        return bytes(info.data)
    finally:
        buf.unmap(info)


def missing_portal_text():
    return L.t("Chụp cuộn cần cổng RemoteDesktop của xdg-desktop-portal để tự cuộn trang thay bạn. Hãy cài xdg-desktop-portal-gnome hoặc xdg-desktop-portal-kde bản có RemoteDesktop (GNOME 40, KDE Plasma 5.27 trở lên đều có; xdg-desktop-portal-wlr thì chưa), rồi đăng xuất và đăng nhập lại. Phiên X11 cũng dùng cùng cổng này.")


def show_error(app, body):
    parent = app.get_active_window() if app is not None else None
    dlg = Adw.MessageDialog(heading=L.t("Không chụp cuộn được"), body=body)
    if parent is not None:
        dlg.set_transient_for(parent)
    if app is not None:
        dlg.set_application(app)
    dlg.add_response("close", L.t("Đóng"))
    dlg.set_default_response("close")
    dlg.set_close_response("close")
    dlg.present()
    return dlg


def _glib_schedule(ms, fn):
    GLib.timeout_add(int(ms), lambda: (fn(), False)[1])


def _later(fn, *args):
    GLib.idle_add(lambda: (fn(*args), False)[1])


# ---------- The real session ----------

class ScrollCaptureSession:
    """One scrolling capture. on_done(surface, error_text): surface None and error None means the
    user cancelled (or stopped before the first frame)."""

    def __init__(self, app, logical, pixel_rect, total_logical, on_done):
        self.app = app
        self.logical = tuple(float(v) for v in logical)
        self.view_height = int(pixel_rect[3]) if pixel_rect else int(logical[3])
        self.total_logical = tuple(total_logical) if total_logical else (0, 0, 1, 1)
        self.on_done = on_done
        self.conn = None
        self.session = None
        self.version = 0
        self.cursor_modes = 0
        self.token = None
        self.retried = False
        self.stream = None
        self.fd = None
        self.pipeline = None
        self.sink = None
        self.frame_size = None
        self.crop = None
        self.last_frame = None
        self.machine = None
        self.window = None
        self.smooth_scroll = False
        self.user_stopped = False
        self.finished = False

    # ---------- Portal ----------

    def start(self):
        from . import recorder
        try:
            recorder.ensure_gst()
            for name in ("pipewiresrc", "videoconvert", "appsink"):
                if not recorder.has_element(name):
                    raise RuntimeError(L.t("Chụp cuộn cần GStreamer với các gói gstreamer1.0-pipewire và gstreamer1.0-plugins-base. Thiếu: ") + name)
        except RuntimeError as e:
            _later(self._finish, None, str(e))
            return
        try:
            self.conn = portal.bus()
        except portal.PortalError as e:
            _later(self._finish, None, missing_portal_text() + "\n\n" + str(e))
            return
        self.version = portal.interface_version(portal.REMOTE_DESKTOP_IFACE, self.conn)
        if self.version <= 0:
            _later(self._finish, None, missing_portal_text())
            return
        self.cursor_modes = portal.available_cursor_modes(self.conn)
        saved = settings.get(TOKEN_KEY)
        self.token = saved if (self.version >= 2 and isinstance(saved, str) and saved) else None
        self._create_session()

    def _create_session(self):
        token = portal.new_token()
        options = {
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", portal.new_token("minisnap_session")),
        }
        portal.Request(self.conn, portal.REMOTE_DESKTOP_IFACE, "CreateSession",
                       GLib.Variant("(a{sv})", (options,)), token, self._on_created)

    def _on_created(self, code, results):
        if code == 0 and self.finished:
            portal.close_session(self.conn, results.get("session_handle"))
            return
        if self.finished:
            return
        if code != 0:
            self._portal_failed(code, results)
            return
        self.session = results.get("session_handle")
        if not self.session:
            self._portal_failed(2, {"error": "xdg-desktop-portal: no session handle"})
            return
        token = portal.new_token()
        options = select_devices_options(self.version, self.token, token)
        portal.Request(self.conn, portal.REMOTE_DESKTOP_IFACE, "SelectDevices",
                       GLib.Variant("(oa{sv})", (self.session, options)), token, self._on_devices)

    def _on_devices(self, code, results):
        if self.finished:
            return
        if code != 0:
            self._portal_failed(code, results)
            return
        token = portal.new_token()
        options = {
            "handle_token": GLib.Variant("s", token),
            "types": GLib.Variant("u", portal.SOURCE_MONITOR),
            "multiple": GLib.Variant("b", False),
        }
        # The stitcher compares rows of consecutive frames: a cursor drawn into them (it stays at the
        # centre while the page moves) would spoil the match, so it is hidden when the portal allows.
        if self.cursor_modes & portal.CURSOR_HIDDEN:
            options["cursor_mode"] = GLib.Variant("u", portal.CURSOR_HIDDEN)
        portal.Request(self.conn, portal.SCREENCAST_IFACE, "SelectSources",
                       GLib.Variant("(oa{sv})", (self.session, options)), token, self._on_sources)

    def _on_sources(self, code, results):
        if self.finished:
            return
        if code != 0:
            self._portal_failed(code, results)
            return
        token = portal.new_token()
        options = {"handle_token": GLib.Variant("s", token)}
        portal.Request(self.conn, portal.REMOTE_DESKTOP_IFACE, "Start",
                       GLib.Variant("(osa{sv})", (self.session, "", options)), token, self._on_started)

    def _portal_failed(self, code, results):
        if code == 1:                      # the user cancelled the permission dialog
            self._finish(None, None)
            return
        if self.token and not self.retried:
            # A saved permission that no longer works: forget it and ask again, once.
            self.retried = True
            self.token = None
            self._forget_token()
            portal.close_session(self.conn, self.session)
            self.session = None
            self._create_session()
            return
        detail = results.get("error") or "xdg-desktop-portal RemoteDesktop: response %d" % code
        self._finish(None, L.t("Chụp cuộn bị lỗi:\n") + str(detail))

    @staticmethod
    def _forget_token():
        try:
            settings.set(TOKEN_KEY, None)
        except OSError:
            pass

    def _on_started(self, code, results):
        if self.finished:
            return
        if code != 0:
            self._portal_failed(code, results)
            return
        devices, streams, new_token = parse_start_response(results)
        if self.version >= 2 and new_token:
            try:
                settings.set(TOKEN_KEY, new_token)
            except OSError:
                pass
        if not streams:
            self._finish(None, L.t("Không nhận được hình ảnh nào từ màn hình. Hãy thử lại."))
            return
        if devices is not None and not devices & portal.DEVICE_POINTER:
            self._finish(None, L.t("Hệ thống không cho MiniSnap điều khiển chuột nên không tự cuộn trang được."))
            return
        self.stream = streams[0]
        try:
            self.fd = portal.open_pipewire_remote(self.conn, self.session)
            self._start_pipeline()
        except (GLib.Error, RuntimeError) as e:
            self._finish(None, L.t("Chụp cuộn bị lỗi:\n") + str(getattr(e, "message", e)))
            return
        self.window = ScrollStatusWindow(self.app, self.stop)
        self.window.present()
        self.machine = ScrollStateMachine(self.view_height, self._grab_frame, self._scroll, _glib_schedule,
                                          self._on_machine_done, progress=self.window.update)
        self.machine.start()

    # ---------- Frames ----------

    def _start_pipeline(self):
        desc = ("pipewiresrc fd=%d path=%d do-timestamp=true keepalive-time=1000 ! videoconvert ! "
                "video/x-raw,format=%s ! appsink name=sink max-buffers=1 drop=true emit-signals=false sync=false"
                % (self.fd, self.stream["node"], FRAME_FORMAT))
        self.pipeline = Gst.parse_launch(desc)
        self.sink = self.pipeline.get_by_name("sink")
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus)
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError(L.t("Không đọc được hình ảnh màn hình (GStreamer)."))

    def _on_bus(self, bus, msg):
        if self.finished:
            return
        if msg.type == Gst.MessageType.ERROR:
            err, _debug = msg.parse_error()
            self._stream_ended(err.message)
        elif msg.type == Gst.MessageType.EOS:
            self._stream_ended(None)

    def _stream_ended(self, error):
        """The stream stopped (error, or sharing ended from the desktop's indicator)."""
        if self.machine is not None and self.machine.stitcher.frame_count > 0:
            self.machine.finish()
        else:
            self._finish(None, L.t("Chụp cuộn bị lỗi:\n") + error if error
                         else L.t("Không nhận được hình ảnh nào từ màn hình. Hãy thử lại."))

    def _grab_frame(self):
        """Newest frame, cropped to the selection. When PipeWire sent nothing new the screen did not
        change, so the previous frame is returned again (the stitcher then reports NoMovement)."""
        if self.sink is None:
            return None
        try:
            sample = self.sink.emit("try-pull-sample", PULL_TIMEOUT_NS)
        except (TypeError, GLib.Error):
            sample = None
        if sample is not None:
            frame = self._frame_from_sample(sample)
            if frame is not None:
                self.last_frame = frame
        return self.last_frame

    def _frame_from_sample(self, sample):
        caps = sample.get_caps()
        if caps is None or caps.get_size() == 0:
            return None
        s = caps.get_structure(0)
        okw, w = s.get_int("width")
        okh, h = s.get_int("height")
        if not (okw and okh) or w <= 0 or h <= 0:
            return None
        if self.frame_size is None:
            self.frame_size = (w, h)
            self.crop = selection_to_stream(self.logical, self.stream, w, h, self.total_logical)
            if self.crop is None:
                # The shared monitor is not the one with the selection (e.g. a remembered choice).
                self._forget_token()
                _later(self._finish, None, L.t("Vùng đã chọn không nằm trên màn hình được chia sẻ. Hãy thử lại và chọn đúng màn hình."))
                return None
        elif (w, h) != self.frame_size or self.crop is None:
            return None
        buf = sample.get_buffer()
        if buf is None:
            return None
        data = buffer_bytes(buf)
        if not data:
            return None
        return surface_from_bgrx(data, w, h, None, self.crop)

    # ---------- Scrolling ----------

    def _rd_call(self, method, params, on_error=None):
        def done(conn, res, *_):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                if on_error is not None and not self.finished:
                    on_error(e)
        try:
            self.conn.call(portal.BUS_NAME, portal.OBJECT_PATH, portal.REMOTE_DESKTOP_IFACE, method, params,
                           None, Gio.DBusCallFlags.NONE, -1, None, done)
        except GLib.Error as e:
            if on_error is not None:
                on_error(e)

    def _scroll(self, notches):
        if self.finished or not notches or not self.session or self.stream is None:
            return
        x, y = pointer_position(self.logical, self.stream, self.total_logical)
        self._rd_call("NotifyPointerMotionAbsolute",
                      GLib.Variant("(oa{sv}udd)", (self.session, {}, self.stream["node"], float(x), float(y))))
        self._axis(int(notches))

    def _axis(self, notches):
        if self.smooth_scroll:
            self._rd_call("NotifyPointerAxis",
                          GLib.Variant("(oa{sv}dd)", (self.session, {"finish": GLib.Variant("b", True)},
                                                      0.0, notches * SMOOTH_STEP)))
            return

        def failed(_error):
            if not self.smooth_scroll:
                self.smooth_scroll = True
                self._axis(notches)
        # Positive steps scroll down, like a wheel turned towards the user.
        self._rd_call("NotifyPointerAxisDiscrete",
                      GLib.Variant("(oa{sv}ui)", (self.session, {}, AXIS_VERTICAL, notches)), failed)

    # ---------- Ending ----------

    def stop(self):
        """Stop button, Esc or closing the status window."""
        self.user_stopped = True
        if self.machine is not None and not self.machine.finished:
            self.machine.stop()
        else:
            self._finish(None, None)

    def cancel(self):
        """App shutdown: drop everything, no editor."""
        self._finish(None, None)

    def _on_machine_done(self, image):
        if image is None and not self.user_stopped:
            self._finish(None, L.t("Không nhận được hình ảnh nào từ màn hình. Hãy thử lại."))
        else:
            self._finish(image, None)

    def _cleanup(self):
        if self.pipeline is not None:
            try:
                self.pipeline.get_bus().remove_signal_watch()
            except Exception:  # noqa: BLE001
                pass
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            self.sink = None
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        portal.close_session(self.conn, self.session)
        self.session = None
        if self.window is not None:
            self.window.finish()
            self.window = None
        self.last_frame = None

    def _finish(self, surface, error):
        if self.finished:
            return
        self.finished = True
        if self.machine is not None and not self.machine.finished:
            self.machine.abort()
        self._cleanup()
        if self.on_done is not None:
            self.on_done(surface, error)


# ---------- Status window ----------

class ScrollStatusWindow(Gtk.Window):
    """Progress text (N shots, height H px) and a Stop button (the FloatingBar of the Windows
    version). Wayland gives apps no global Esc key; Esc works while this window has the focus."""

    def __init__(self, app, on_stop):
        super().__init__()
        self.on_stop = on_stop
        self._closing = False
        if app is not None:
            self.set_application(app)
        self.set_title(L.t("Chụp cuộn trang dài"))
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.add_css_class("ms-floatbar")
        self.label = Gtk.Label(label=L.t("Đang chuẩn bị chụp cuộn..."), xalign=0)
        self.label.add_css_class("ms-scroll-status")
        self.label.set_width_chars(30)
        stop = Gtk.Button()
        inner = Gtk.Box(spacing=6)
        inner.append(icons.Glyph("stop", 16, ink=(30, 30, 30), paper=(240, 240, 242)))
        inner.append(Gtk.Label(label=L.t("Dừng (Esc)")))
        stop.set_child(inner)
        stop.add_css_class("ms-float-button")
        stop.connect("clicked", lambda *_: self._stop())
        box.append(self.label)
        box.append(stop)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)

    def update(self, frames, height):
        self.label.set_text(L.t("Đang chụp cuộn... ") + str(frames) + L.t(" lần, cao ") + str(height) + " px")

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self._stop()
            return True
        return False

    def _stop(self):
        if self.on_stop is not None:
            self.on_stop()

    def _on_close_request(self, *_):
        if not self._closing:
            self._closing = True
            self._stop()
        return False

    def finish(self):
        if self._closing:
            return
        self._closing = True
        self.close()
