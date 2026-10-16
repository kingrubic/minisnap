"""Screen recording: xdg-desktop-portal ScreenCast -> PipeWire -> GStreamer -> MP4.

Flow: the portal asks the user which screen to share, we get a PipeWire fd + node id, a small
control window counts down 3-2-1, then
  pipewiresrc ! videoconvert ! videocrop (selected region) ! videoscale ! I420 even size ! x264enc ! mp4mux ! filesink
runs until Stop (EOS, wait for it on the bus, then close). Pause = pipeline PAUSED.
The crop is computed when the stream's caps (its real pixel size) are known.
Fallbacks when x264enc (gst-plugins-ugly) is missing: openh264enc, then vp8enc + webmmux (.webm).
"""

import time

from . import _gi
from gi.repository import GLib, Gtk

from . import icons, paths, portal
from .i18n import L

if _gi.HAVE_GST:
    from gi.repository import Gst
else:  # pragma: no cover - reported to the user when recording starts
    Gst = None

MAX_W, MAX_H = 3840, 2160
_gst_ready = False


def ensure_gst():
    """Initialises GStreamer; raises RuntimeError with a friendly message when it is missing."""
    global _gst_ready
    if Gst is None:
        raise RuntimeError(L.t("Thiếu GStreamer. Hãy cài: sudo apt install gir1.2-gstreamer-1.0 gstreamer1.0-pipewire gstreamer1.0-plugins-ugly"))
    if not _gst_ready:
        Gst.init(None)
        _gst_ready = True


def has_element(name):
    ensure_gst()
    return Gst.ElementFactory.find(name) is not None


def choose_encoder():
    """(encoder description, muxer description, file extension)."""
    ensure_gst()
    if has_element("x264enc"):
        return ("x264enc tune=zerolatency speed-preset=veryfast", "mp4mux", ".mp4")
    if has_element("openh264enc"):
        parse = " ! h264parse" if has_element("h264parse") else ""
        return ("openh264enc" + parse, "mp4mux", ".mp4")
    if has_element("vp8enc") and has_element("webmmux"):
        return ("vp8enc deadline=1 cpu-used=8 end-usage=cbr target-bitrate=6000000", "webmmux", ".webm")
    raise RuntimeError(L.t("Không tìm thấy bộ mã hoá video. Hãy cài: sudo apt install gstreamer1.0-plugins-ugly"))


def even_size(w, h):
    """H.264 needs even dimensions; very large areas are scaled down to 4K (Windows ScreenRecorder)."""
    w, h = max(2, int(w)), max(2, int(h))
    scale = min(1.0, MAX_W / float(w), MAX_H / float(h))
    return max(2, int(w * scale) & ~1), max(2, int(h * scale) & ~1)


def encode_tail(out_size, location, encoder=None):
    """Everything after the source: convert, crop, scale, encode, mux, write. Returns (description, ext)."""
    enc, mux, ext = encoder or choose_encoder()
    caps = "video/x-raw,format=I420,pixel-aspect-ratio=1/1"
    if out_size:
        caps += ",width=%d,height=%d" % out_size
    loc = location.replace("\\", "\\\\").replace('"', '\\"')
    desc = ('videoconvert ! videocrop name=crop ! videoscale ! videoconvert ! %s ! queue ! %s ! %s name=mux ! filesink location="%s"'
            % (caps, enc, mux, loc))
    return desc, ext


def compute_crop(frame_w, frame_h, region, stream_props, total_logical):
    """Crop (left, top, right, bottom) in stream pixels for a logical region on the shared monitor.

    region: (x, y, w, h) in global logical coordinates, or None for the whole stream.
    stream_props: portal stream properties ("position", "size" in logical units, when known).
    total_logical: (x, y, w, h) of the whole desktop, used when the portal gives no geometry."""
    if region is None:
        return (0, 0, frame_w & 1, frame_h & 1)
    pos = stream_props.get("position") if stream_props else None
    size = stream_props.get("size") if stream_props else None
    if size and size[0] > 0 and size[1] > 0:
        ox, oy = pos if pos else (0, 0)
        lw, lh = size
    else:
        ox, oy, lw, lh = total_logical
    sx, sy = frame_w / float(lw), frame_h / float(lh)
    x1 = int(round((region[0] - ox) * sx))
    y1 = int(round((region[1] - oy) * sy))
    x2 = int(round((region[0] + region[2] - ox) * sx))
    y2 = int(round((region[1] + region[3] - oy) * sy))
    x1, y1 = max(0, min(frame_w - 2, x1)), max(0, min(frame_h - 2, y1))
    x2, y2 = max(x1 + 2, min(frame_w, x2)), max(y1 + 2, min(frame_h, y2))
    w, h = (x2 - x1) & ~1, (y2 - y1) & ~1
    return (x1, y1, frame_w - x1 - w, frame_h - y1 - h)


class RecordingSession:
    """One recording. on_done(path, error_text); both None = cancelled before starting."""

    def __init__(self, app, region=None, out_size=None, total_logical=None, on_done=None):
        self.app = app
        self.region = region
        self.out_size = even_size(*out_size) if out_size else None
        self.total_logical = total_logical or (0, 0, 1, 1)
        self.on_done = on_done
        self.cast = None
        self.pipeline = None
        self.bar = None
        self.path = None
        self.stopping = False
        self.finished = False
        self.paused = False
        self.started_at = None
        self.paused_total = 0.0
        self.paused_at = None
        self._eos_timeout = 0

    @property
    def is_active(self):
        return not self.finished

    def start(self):
        try:
            ensure_gst()
            if not has_element("pipewiresrc"):
                raise RuntimeError(L.t("Thiếu gói gstreamer1.0-pipewire để quay màn hình."))
            self.encoder = choose_encoder()
        except RuntimeError as e:
            GLib.idle_add(lambda: (self._done(None, str(e)), False)[1])
            return
        self.cast = portal.ScreenCastSession()
        self.cast.start(self._on_stream, self._on_portal_error)

    def _on_portal_error(self, message):
        self._done(None, message)   # message None: the user cancelled the screen picker

    def _on_stream(self, fd, node_id, props):
        self.fd, self.node_id, self.props = fd, node_id, props
        self.bar = RecorderBar(self)
        self.bar.present()
        self.bar.start_countdown()

    # ---------- Pipeline ----------

    def begin_pipeline(self):
        self.path = paths.new_video_path(self.encoder[2])
        tail, _ext = encode_tail(self.out_size, self.path, self.encoder)
        desc = "pipewiresrc name=src fd=%d path=%d do-timestamp=true keepalive-time=1000 ! %s" % (self.fd, self.node_id, tail)
        try:
            self.pipeline = Gst.parse_launch(desc)
        except GLib.Error as e:
            self._done(None, e.message)
            return
        crop = self.pipeline.get_by_name("crop")
        src_pad = self.pipeline.get_by_name("src").get_static_pad("src")

        def on_event(pad, info):
            ev = info.get_event()
            if ev is not None and ev.type == Gst.EventType.CAPS:
                s = ev.parse_caps().get_structure(0)
                okw, fw = s.get_int("width")
                okh, fh = s.get_int("height")
                if okw and okh:
                    l, t, r, b = compute_crop(fw, fh, self.region, self.props, self.total_logical)
                    crop.set_property("left", l)
                    crop.set_property("top", t)
                    crop.set_property("right", r)
                    crop.set_property("bottom", b)
            return Gst.PadProbeReturn.OK
        src_pad.add_probe(Gst.PadProbeType.EVENT_DOWNSTREAM, on_event)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus)
        if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            self._done(None, L.t("Không bắt đầu quay được (GStreamer)."))
            return
        self.started_at = time.monotonic()

    def _on_bus(self, bus, msg):
        if msg.type == Gst.MessageType.EOS:
            self._finish_pipeline(None)
        elif msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            self._finish_pipeline(err.message)

    def elapsed(self):
        if self.started_at is None:
            return 0.0
        now = self.paused_at if self.paused_at is not None else time.monotonic()
        return max(0.0, now - self.started_at - self.paused_total)

    def toggle_pause(self):
        if self.pipeline is None or self.stopping:
            return
        if self.paused:
            self.pipeline.set_state(Gst.State.PLAYING)
            self.paused_total += time.monotonic() - self.paused_at
            self.paused_at = None
            self.paused = False
        else:
            self.pipeline.set_state(Gst.State.PAUSED)
            self.paused_at = time.monotonic()
            self.paused = True

    def stop(self):
        if self.stopping or self.finished:
            return
        self.stopping = True
        if self.pipeline is None:
            self._done(None, None)
            return
        if self.paused:
            self.toggle_pause_force_play()
        if self.bar is not None:
            self.bar.show_saving()
        # A live source only pushes the EOS when it is PLAYING.
        self.pipeline.send_event(Gst.Event.new_eos())
        self._eos_timeout = GLib.timeout_add_seconds(10, self._eos_timed_out)

    def toggle_pause_force_play(self):
        self.pipeline.set_state(Gst.State.PLAYING)
        if self.paused_at is not None:
            self.paused_total += time.monotonic() - self.paused_at
        self.paused_at = None
        self.paused = False

    def _eos_timed_out(self):
        self._eos_timeout = 0
        self._finish_pipeline(None)
        return False

    def _finish_pipeline(self, error):
        if self._eos_timeout:
            GLib.source_remove(self._eos_timeout)
            self._eos_timeout = 0
        if self.pipeline is not None:
            bus = self.pipeline.get_bus()
            bus.remove_signal_watch()
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
        self._done(self.path if error is None else None, error)

    def _done(self, path, error):
        if self.finished:
            return
        self.finished = True
        if self.cast is not None:
            self.cast.close()
        if self.bar is not None:
            self.bar.finish()
            self.bar = None
        if self.on_done:
            self.on_done(path, error)


class RecorderBar(Gtk.Window):
    """Countdown, timer, pause and stop controls (RecorderBar in windows/src/Recorder.cs).
    Wayland does not let apps keep windows on top or out of the recording, so this is a small
    normal window; it is also reachable with `minisnap --record` (toggles stop)."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.countdown = 3
        self.tick_id = 0
        self._closing = False
        if session.app is not None:
            self.set_application(session.app)
        self.set_title(L.t("Quay video màn hình"))
        self.set_resizable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        box.add_css_class("ms-floatbar")
        self.time_label = Gtk.Label(label=L.t("Bắt đầu sau 3..."))
        self.time_label.add_css_class("ms-rec-time")
        self.time_label.set_width_chars(14)
        self.pause_glyph = icons.Glyph("pause", 16, ink=(30, 30, 30), paper=(240, 240, 242))
        self.pause_text = Gtk.Label(label=L.t("Tạm dừng"))
        self.pause_btn = self._button(self.pause_glyph, self.pause_text, session.toggle_pause)
        self.pause_btn.set_sensitive(False)
        self.stop_btn = self._button(icons.Glyph("stop", 16, ink=(30, 30, 30), paper=(240, 240, 242)),
                                     Gtk.Label(label=L.t("Dừng")), session.stop)
        box.append(self.time_label)
        box.append(self.pause_btn)
        box.append(self.stop_btn)
        self.set_child(box)
        self.connect("close-request", self._on_close_request)

    def _button(self, glyph, label, cb):
        b = Gtk.Button()
        inner = Gtk.Box(spacing=6)
        inner.append(glyph)
        inner.append(label)
        b.set_child(inner)
        b.add_css_class("ms-float-button")
        b.connect("clicked", lambda *_: (cb(), self._refresh()))
        return b

    def start_countdown(self):
        self.tick_id = GLib.timeout_add(1000, self._tick)

    def _tick(self):
        s = self.session
        if s.pipeline is None and not s.stopping and not s.finished:
            self.countdown -= 1
            if self.countdown > 0:
                self.time_label.set_text(L.t("Bắt đầu sau ") + "%d..." % self.countdown)
                return True
            self.tick_id = 0
            s.begin_pipeline()
            if s.finished:
                return False
            self.pause_btn.set_sensitive(True)
            self.tick_id = GLib.timeout_add(250, self._tick)
            self._refresh()
            return False
        self._refresh()
        if s.finished or s.stopping:
            self.tick_id = 0
            return False
        return True

    def _refresh(self):
        s = self.session
        if s.pipeline is None or s.stopping:
            return
        t = int(s.elapsed())
        self.time_label.set_text(("⏸ " if s.paused else "● ") + "%02d:%02d" % (t // 60, t % 60))
        for c in ("ms-rec-live", "ms-rec-paused"):
            self.time_label.remove_css_class(c)
        self.time_label.add_css_class("ms-rec-paused" if s.paused else "ms-rec-live")
        self.pause_glyph.set_kind("record" if s.paused else "pause")
        self.pause_text.set_text(L.t("Tiếp tục") if s.paused else L.t("Tạm dừng"))

    def show_saving(self):
        self.time_label.set_text(L.t("Đang lưu video..."))
        self.pause_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(False)

    def _on_close_request(self, *_):
        if self._closing:
            return False
        self.session.stop()
        return True

    def finish(self):
        if self.tick_id:
            GLib.source_remove(self.tick_id)
            self.tick_id = 0
        self._closing = True
        self.close()
