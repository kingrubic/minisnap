"""Headless self-test: `python3 -m minisnap --selftest OUTDIR`.

Runs under `xvfb-run -a -s "-screen 0 1600x1000x24"` without any portal (none is called here).
Writes OUTDIR/log.txt plus PNGs: render.png, stitch.png, and screenshots of every window in both
languages and both colour schemes (e.g. editor-vi-dark.png). Each step logs "ok" or
"FAILED: reason"; a failing step never stops the others; the exit code is non-zero if any failed.
(SelfTest in windows/src/Program.cs.)
"""

import ast
import os
import random
import shutil
import sys
import tempfile
import time
import traceback

WINDOW_KINDS = ("launcher", "editor", "overlay", "library", "about", "shortcuts")


def run(outdir):
    """Prepares an isolated environment, then runs the GTK part inside a non-unique application."""
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "log.txt"), "w", encoding="utf-8"):
        pass
    tmp = tempfile.mkdtemp(prefix="minisnap-selftest-")
    # Never touch the user's real captures or settings.
    os.environ["MINISNAP_LIBRARY"] = os.path.join(tmp, "library")
    os.environ["XDG_CONFIG_HOME"] = os.path.join(tmp, "config")
    os.environ.pop("MINISNAP_LANG", None)
    os.environ.setdefault("GTK_A11Y", "none")
    os.environ.setdefault("NO_AT_BRIDGE", "1")
    # Deterministic software rendering under Xvfb (override by setting GSK_RENDERER yourself).
    os.environ.setdefault("GSK_RENDERER", "cairo")
    try:
        from .app import MiniSnapApp
        app = MiniSnapApp(selftest_dir=outdir)
        app.run([sys.argv[0] if sys.argv else "minisnap"])
        code = app.selftest_result
    except Exception:  # noqa: BLE001
        _append(outdir, "selftest: FAILED to start: " + traceback.format_exc())
        code = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return code


def _append(outdir, line):
    print(line, flush=True)
    with open(os.path.join(outdir, "log.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def start(app, outdir):
    """Called from MiniSnapApp.do_activate in self-test mode."""
    Runner(app, outdir).start()


# ---------- Synthetic images ----------

def sample_image(w, h, lines, seed):
    """Light page with numbered text lines and a few coloured boxes (SelfTest.SampleImage)."""
    import cairo
    from . import _gi  # noqa: F401
    from gi.repository import PangoCairo
    from .shapes import font_desc

    rnd = random.Random(seed)
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(s)
    cr.set_source_rgb(246 / 255.0, 248 / 255.0, 252 / 255.0)
    cr.paint()
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(font_desc(22, bold=False))
    for i in range(lines):
        layout.set_text("Line %d — the quick brown fox %d jumps" % (i + 1, rnd.randint(1000, 9999)), -1)
        cr.move_to(40, 30 + i * 58)
        cr.set_source_rgb(105 / 255.0, 105 / 255.0, 105 / 255.0)
        PangoCairo.show_layout(cr, layout)
        if i % 7 == 3:
            cr.set_source_rgb(rnd.randint(80, 199) / 255.0, rnd.randint(80, 199) / 255.0, rnd.randint(80, 199) / 255.0)
            cr.rectangle(w - 260, 20 + i * 58, 200, 40)
            cr.fill()
    s.flush()
    return s


def text_image(text, w=900, h=160):
    import cairo
    from . import _gi  # noqa: F401
    from gi.repository import PangoCairo
    from .shapes import font_desc

    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(s)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(font_desc(36, bold=False))
    layout.set_text(text, -1)
    cr.move_to(30, 40)
    cr.set_source_rgb(0, 0, 0)
    PangoCairo.show_layout(cr, layout)
    s.flush()
    return s


def sample_shapes():
    from .shapes import (ArrowShape, BlurShape, EllipseShape, HighlightShape, LineShape, PenShape, RectShape,
                         StepShape, TextShape)
    red, blue, yellow, green, purple = (232, 38, 38), (30, 120, 230), (255, 214, 0), (40, 170, 70), (150, 70, 200)
    pen = [(620 + i * 6, 430 + 25 * ((i % 8) - 4) * ((-1) ** (i // 8)) / 4.0) for i in range(40)]
    return [
        ArrowShape(a=(560, 420), b=(380, 150), color=red, width=5),
        RectShape(a=(30, 80), b=(560, 140), color=red, width=4),
        EllipseShape(a=(600, 60), b=(860, 180), color=blue, width=4),
        LineShape(a=(600, 230), b=(860, 230), color=green, width=5),
        PenShape(points=pen, color=purple, width=5),
        HighlightShape(a=(36, 200), b=(560, 240), color=yellow, width=5),
        BlurShape(a=(330, 260), b=(720, 330), width=5),
        StepShape(center=(60, 470), number=1, color=red, width=5),
        StepShape(center=(60, 530), number=2, color=blue, width=5),
        TextShape(pos=(100, 450), text="Chú thích tiếng Việt", color=red, width=5),
    ]


def snapshot_window(win, path):
    """Renders a presented window to PNG through Gtk.WidgetPaintable and the window's own renderer."""
    from . import _gi  # noqa: F401
    from gi.repository import Gtk

    last_error = "window has no size"
    for target in (win, win.get_child()):
        if target is None:
            continue
        w, h = target.get_width(), target.get_height()
        if w <= 0 or h <= 0:
            continue
        paintable = Gtk.WidgetPaintable(widget=target)
        snap = Gtk.Snapshot()
        paintable.snapshot(snap, w, h)
        node = snap.to_node()
        if node is None:
            last_error = "empty render node"
            continue
        renderer = win.get_renderer()
        if renderer is None:
            last_error = "window has no renderer"
            continue
        tex = renderer.render_texture(node, None)
        if tex.save_to_png(path) and os.path.getsize(path) > 0:
            return "%dx%d" % (tex.get_width(), tex.get_height())
        last_error = "save_to_png failed"
    raise RuntimeError(last_error)


class Runner:
    def __init__(self, app, outdir):
        self.app = app
        self.outdir = outdir
        self.failures = 0
        self.finished = False

    def log(self, line):
        _append(self.outdir, line)

    def check(self, name, fn):
        try:
            detail = fn()
            self.log("%s: ok%s" % (name, (" — " + str(detail)) if detail else ""))
        except Exception as e:  # noqa: BLE001
            self.failures += 1
            self.log("%s: FAILED: %s" % (name, e))
            for line in traceback.format_exc().rstrip().splitlines():
                self.log("    " + line)

    def start(self):
        from gi.repository import GLib
        from . import VERSION
        self.app.hold()
        self.log("MiniSnap %s self-test, Python %s" % (VERSION, sys.version.split()[0]))
        self._log_versions()
        GLib.timeout_add_seconds(300, self._watchdog)
        for name, fn in (
            ("settings", self.test_settings),
            ("args", self.test_args),
            ("i18n", self.test_i18n),
            ("render", self.test_render),
            ("stitch", self.test_stitch),
            ("monitor mapping", self.test_mapping),
            ("record crop", self.test_crop),
            ("updater compare", self.test_updater),
            ("ocr", self.test_ocr),
            ("video encode", self.test_video),
            ("library files", self.fill_library),
            ("editor operations", self.test_editor_ops),
        ):
            self.check(name, fn)
        self._pump(self._ui_steps())

    def _log_versions(self):
        try:
            from gi.repository import Adw, Gtk
            self.log("GTK %d.%d.%d, libadwaita %d.%d.%d, renderer env GSK_RENDERER=%s" % (
                Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version(),
                Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version(),
                os.environ.get("GSK_RENDERER", "")))
        except Exception as e:  # noqa: BLE001
            self.log("versions: %s" % e)

    def _watchdog(self):
        if not self.finished:
            self.failures += 1
            self.log("watchdog: FAILED: self-test did not finish in 300 s")
            self._finish()
        return False

    def _finish(self):
        if self.finished:
            return
        self.finished = True
        self.log("selftest: %s (%d failed step%s)" % ("ok" if self.failures == 0 else "FAILED", self.failures,
                                                      "" if self.failures == 1 else "s"))
        self.app.selftest_result = 0 if self.failures == 0 else 1
        for w in list(self.app.get_windows()):
            try:
                w.destroy()
            except Exception:  # noqa: BLE001
                pass
        self.app.release()
        self.app.quit()

    # ---------- Non-UI steps ----------

    def test_settings(self):
        from . import settings
        settings.set("ask_after_select", False)
        settings.reset_cache()
        if settings.get("ask_after_select") is not False:
            raise RuntimeError("value not read back from " + settings.config_path())
        settings.set("ask_after_select", True)
        settings.reset_cache()
        return settings.config_path()

    def test_args(self):
        from .app import parse_args
        cases = {
            ("--capture", "region"): ("capture", "region"),
            ("--capture=full",): ("capture", "full"),
            ("--capture", "delayed"): ("capture", "delayed"),
            ("--record",): ("record", None),
            ("--ocr",): ("ocr", None),
            ("--library",): ("library", None),
            ("--about",): ("about", None),
        }
        for args, want in cases.items():
            got = parse_args(list(args))[:2]
            if got != want:
                raise RuntimeError("%s -> %s, expected %s" % (args, got, want))
        try:
            parse_args(["--capture", "nonsense"])
            raise RuntimeError("bad --capture value accepted")
        except ValueError:
            pass
        return "%d cases" % len(cases)

    def test_i18n(self):
        """Every L.t("…") literal in the package must have an English entry."""
        from .i18n import L
        pkg = os.path.dirname(os.path.abspath(__file__))
        used, missing, dynamic = set(), [], 0
        for name in sorted(os.listdir(pkg)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(pkg, name), "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "t"
                        and isinstance(node.func.value, ast.Name) and node.func.value.id == "L"):
                    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                        text = node.args[0].value
                        used.add(text)
                        if not L.has(text):
                            missing.append("%s:%d %r" % (name, node.lineno, text))
                    else:
                        dynamic += 1
        if missing:
            raise RuntimeError("%d missing translation(s): %s" % (len(missing), "; ".join(missing)))
        return "%d strings checked, %d non-literal calls" % (len(used), dynamic)

    def test_render(self):
        from . import render
        sample = sample_image(900, 560, 9, 1)
        flat = render.render(sample, sample_shapes())
        path = os.path.join(self.outdir, "render.png")
        flat.write_to_png(path)
        r, g, b = render.pixel_rgb(flat, 30, 110)    # left edge of the red box
        if not (r > 180 and g < 110 and b < 110):
            raise RuntimeError("box edge pixel is %s, expected red" % ((r, g, b),))
        self._render_sample = flat
        return "%dx%d" % render.size(flat)

    def test_stitch(self):
        """Synthetic scrolling page with a sticky header and footer, viewed through a 600px viewport."""
        import cairo
        from gi.repository import PangoCairo
        from .shapes import font_desc
        from .stitcher import ADDED, NO_MOVEMENT, ScrollStitcher

        page_h, view_h, header, footer, width = 2600, 600, 70, 50, 800
        page = sample_image(width, page_h, 44, 2)
        stitcher = ScrollStitcher()
        last = page_h - (view_h - header - footer) - header
        offsets = [0, 230, 460, 700, 950, 1200, 1450, 1700, 1950, last, last]
        outcomes = []
        for off in offsets:
            frame = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, view_h)
            cr = cairo.Context(frame)
            cr.save()
            cr.rectangle(0, header, width, view_h - header - footer)
            cr.clip()
            cr.set_source_surface(page, 0, header - (off + header))
            cr.paint()
            cr.restore()
            layout = PangoCairo.create_layout(cr)
            layout.set_font_description(font_desc(12))
            cr.set_source_rgb(70 / 255.0, 130 / 255.0, 180 / 255.0)
            cr.rectangle(0, 0, width, header)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(10, 25)
            layout.set_text("STICKY HEADER", -1)
            PangoCairo.show_layout(cr, layout)
            cr.set_source_rgb(47 / 255.0, 79 / 255.0, 79 / 255.0)
            cr.rectangle(0, view_h - footer, width, footer)
            cr.fill()
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(10, view_h - footer + 15)
            layout.set_text("STICKY FOOTER", -1)
            PangoCairo.show_layout(cr, layout)
            frame.flush()
            if stitcher.frame_count == 0:
                stitcher.add_first(frame)
                outcomes.append("first")
                continue
            o = stitcher.add(frame)
            outcomes.append(o)
            if o == NO_MOVEMENT:
                break
        result = stitcher.compose()
        result.write_to_png(os.path.join(self.outdir, "stitch.png"))
        expected = page_h + footer
        line = "%s | height=%d expected=%d" % (" ".join(outcomes), stitcher.total_height, expected)
        self.log("stitch: " + line)
        stitcher.dispose_frames()
        self._stitch_result = result
        if stitcher.total_height != expected or result.get_height() != expected:
            raise RuntimeError("height %d != expected %d" % (stitcher.total_height, expected))
        return "height %d, %d frames added" % (stitcher.total_height, outcomes.count(ADDED))

    def test_mapping(self):
        from .overlay import map_monitors
        mapping, info = map_monitors([(0, 0, 1920, 1080), (1920, 0, 1280, 1024)], 6400, 2160)
        if info[2] != 2.0 or info[3] != 2.0:
            raise RuntimeError("scale %s" % (info,))
        if mapping[1][1] != (3840, 0, 2560, 2048):
            raise RuntimeError("second monitor -> %s" % (mapping[1][1],))
        mapping, info = map_monitors([(-1280, 0, 1280, 1024), (0, 0, 1920, 1080)], 3200, 1080)
        if mapping[1][1] != (1280, 0, 1920, 1080) or info[0] != -1280:
            raise RuntimeError("negative origin -> %s %s" % (mapping, info))
        return "2 layouts"

    def test_crop(self):
        from .recorder import compute_crop, even_size
        l, t, r, b = compute_crop(3840, 2160, (100, 100, 641, 401), {"position": (0, 0), "size": (1920, 1080)}, None)
        w, h = 3840 - l - r, 2160 - t - b
        if (l, t) != (200, 200) or w % 2 or h % 2 or abs(w - 1282) > 2 or abs(h - 802) > 2:
            raise RuntimeError("crop %s -> %dx%d" % ((l, t, r, b), w, h))
        full = compute_crop(1921, 1081, None, {}, (0, 0, 1921, 1081))
        if full != (0, 0, 1, 1):
            raise RuntimeError("full-frame crop %s" % (full,))
        if even_size(641, 401) != (640, 400) or even_size(7680, 4320) != (3840, 2160):
            raise RuntimeError("even_size")
        return "crop %s" % ((l, t, r, b),)

    def test_updater(self):
        from . import updater
        cur = updater.CURRENT
        newer = updater.Release(tag="v%d.%d.0" % (cur[0], cur[1] + 1))
        same = updater.Release(tag="v" + updater.version_text(cur))
        older = updater.Release(tag="1.0.0")
        result = (updater.is_newer(newer), updater.is_newer(same), updater.is_newer(older))
        if result != (True, False, False):
            raise RuntimeError("is_newer(+1 minor, same, older) = %s" % (result,))
        if updater.parse_version("v2.0-beta") != (2, 0, 0) or updater.parse_version("garbage") is not None:
            raise RuntimeError("parse_version")
        detail = "current=%s" % updater.version_text(cur)
        if os.environ.get("MINISNAP_SELFTEST_NETWORK") == "1":
            try:
                r = updater.fetch()
                detail += ", latest on GitHub: %s" % ("no releases (404)" if r is None else r.tag)
            except Exception as e:  # noqa: BLE001 - network is informational only
                detail += ", fetch skipped: %s" % e
        return detail

    def test_ocr(self):
        from . import ocr
        if ocr.tesseract_path() is None:
            return "skipped (tesseract not installed)"
        langs = ocr.available_languages()
        text, used = ocr.recognize(sample_image(900, 200, 3, 3))
        self.log("ocr [%s] (installed: %s): %s" % ("+".join(used), ",".join(langs), text.replace("\n", " / ")))
        if "vie" in langs:
            vi, _ = ocr.recognize(text_image("Chú thích tiếng Việt có dấu"))
            self.log("ocr vie sample: " + vi.replace("\n", " / "))
        if "line" not in text.lower():
            self.log("ocr: warning — expected the word 'Line' in the recognized text")
        return "%d characters" % len(text)

    def test_video(self):
        from . import _gi as gi_pins
        if not gi_pins.HAVE_GST:
            return "skipped (GStreamer introspection not installed)"
        from gi.repository import Gst
        from . import recorder
        recorder.ensure_gst()
        enc = recorder.choose_encoder()
        path = os.path.join(self.outdir, "test" + enc[2])
        if os.path.exists(path):
            os.unlink(path)
        tail, _ext = recorder.encode_tail(recorder.even_size(641, 401), path, enc)   # odd on purpose
        pipeline = Gst.parse_launch("videotestsrc num-buffers=45 is-live=false ! "
                                    "video/x-raw,width=641,height=401,framerate=30/1 ! " + tail)
        pipeline.set_state(Gst.State.PLAYING)
        bus = pipeline.get_bus()
        msg = bus.timed_pop_filtered(60 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        pipeline.set_state(Gst.State.NULL)
        if msg is None:
            raise RuntimeError("timeout waiting for EOS")
        if msg.type == Gst.MessageType.ERROR:
            err, debug = msg.parse_error()
            raise RuntimeError("%s (%s)" % (err.message, debug))
        size = os.path.getsize(path) if os.path.exists(path) else 0
        if size <= 0:
            raise RuntimeError("empty output file")
        pw = "pipewiresrc " + ("present" if recorder.has_element("pipewiresrc") else "MISSING")
        return "%s, %d bytes, encoder %s, %s" % (os.path.basename(path), size, enc[0].split()[0], pw)

    def fill_library(self):
        """A couple of generated images (and a placeholder video) in the temporary library."""
        from . import paths
        folder = paths.images_folder()
        img = getattr(self, "_render_sample", None) or sample_image(900, 560, 9, 1)
        p1 = os.path.join(folder, "MiniSnap_2026-01-02_10-00-00.png")
        img.write_to_png(p1)
        p2 = os.path.join(folder, "MiniSnap_sample_page.png")
        sample_image(800, 1200, 18, 5).write_to_png(p2)
        now = time.time()
        os.utime(p1, (now - 3600, now - 3600))
        os.utime(p2, (now - 86400 * 3, now - 86400 * 3))
        p3 = os.path.join(paths.videos_folder(), "MiniSnap_recording.mp4")
        with open(p3, "wb") as f:
            f.write(b"\0" * 64)
        os.utime(p3, (now - 86400 * 40, now - 86400 * 40))
        n = len(paths.all_files())
        if n != 3:
            raise RuntimeError("library lists %d files, expected 3" % n)
        return "%d files in %s" % (n, os.environ.get("MINISNAP_LIBRARY"))

    def test_editor_ops(self):
        from . import render
        from .editor import EditorWindow
        ed = EditorWindow(self.app, sample_image(400, 300, 4, 6), None)
        ed.skip_save_prompt = True
        try:
            ed.load_shapes(sample_shapes()[:3])
            ed._apply_crop((50, 40, 200, 150))
            if render.size(ed.base) != (200, 150):
                raise RuntimeError("crop -> %s" % (render.size(ed.base),))
            ed.undo()
            if render.size(ed.base) != (400, 300):
                raise RuntimeError("undo -> %s" % (render.size(ed.base),))
            ed.redo()
            ed.set_tool("select")
            ed.set_color((30, 120, 230))
            ed.set_width(8)
            n = ed._next_step()
            flat = ed.flattened()
            return "crop/undo/redo ok, next step %d, flattened %dx%d" % ((n,) + render.size(flat))
        finally:
            ed.close()

    # ---------- Window screenshots ----------

    def _pump(self, gen):
        from gi.repository import GLib
        try:
            delay = next(gen)
        except StopIteration:
            self._finish()
            return False
        except Exception:  # noqa: BLE001
            self.failures += 1
            self.log("ui: FAILED: " + traceback.format_exc())
            self._finish()
            return False
        GLib.timeout_add(int(delay), self._pump, gen)
        return False

    def _ui_steps(self):
        from gi.repository import Adw
        from .i18n import L
        sm = Adw.StyleManager.get_default()
        for lang in ("vi", "en"):
            for scheme in ("light", "dark"):
                L.set(lang == "en", persist=False)
                sm.set_color_scheme(Adw.ColorScheme.FORCE_DARK if scheme == "dark" else Adw.ColorScheme.FORCE_LIGHT)
                yield 200
                for kind in WINDOW_KINDS:
                    name = "%s-%s-%s" % (kind, lang, scheme)
                    holder = {}
                    try:
                        delay = self._open(kind, holder)
                    except Exception as e:  # noqa: BLE001
                        self.failures += 1
                        self.log("window %s: FAILED: %s" % (name, e))
                        for line in traceback.format_exc().rstrip().splitlines():
                            self.log("    " + line)
                        self._close(holder)
                        continue
                    yield delay
                    if kind == "overlay":
                        try:
                            holder["overlay"].simulate_select((220, 160, 640, 360))
                        except Exception as e:  # noqa: BLE001
                            self.log("window %s: simulate_select raised %s" % (name, e))
                        yield 700
                    self.check("window " + name, lambda: snapshot_window(holder["window"],
                                                                         os.path.join(self.outdir, name + ".png")))
                    self._close(holder)
                    yield 150
        sm.set_color_scheme(Adw.ColorScheme.DEFAULT)

    def _open(self, kind, holder):
        """Creates and presents one window; returns how long to wait before capturing it (ms)."""
        from gi.repository import Gdk
        app = self.app
        if kind == "launcher":
            from .app import LauncherWindow
            win = LauncherWindow(app)
            delay = 700
        elif kind == "editor":
            from .editor import EditorWindow
            win = EditorWindow(app, sample_image(900, 560, 9, 4), None)
            win.skip_save_prompt = True
            shapes = sample_shapes()
            win.load_shapes([shapes[0], shapes[1], shapes[7], shapes[9]])
            delay = 1200
        elif kind == "overlay":
            from .overlay import CaptureOverlay
            display = Gdk.Display.get_default()
            model = display.get_monitors()
            geoms = []
            for i in range(model.get_n_items()):
                g = model.get_item(i).get_geometry()
                geoms.append((g.x, g.y, g.width, g.height))
            if not geoms:
                geoms = [(0, 0, 1600, 1000)]
            tw = max(g[0] + g[2] for g in geoms) - min(g[0] for g in geoms)
            th = max(g[1] + g[3] for g in geoms) - min(g[1] for g in geoms)
            fake = sample_image(tw, th, max(8, th // 60), 7)   # synthetic background, never a real screen
            ov = CaptureOverlay(app, fake, lambda result: None, ask_mode=True)
            ov.show()
            holder["overlay"] = ov
            win = ov.views[0]
            delay = 400
        elif kind == "library":
            from .library import LibraryWindow
            win = LibraryWindow(app, lambda p: None, lambda p: None)
            delay = 1800
        elif kind == "about":
            from .about import make_about
            win = make_about(app, None)
            delay = 900
        elif kind == "shortcuts":
            from .shortcuts import ShortcutsWindow
            win = ShortcutsWindow(app)
            delay = 700
        else:
            raise ValueError(kind)
        holder["window"] = win
        if kind != "overlay":
            win.present()
        return delay

    def _close(self, holder):
        try:
            if "overlay" in holder:
                holder["overlay"].cancel()
            elif "window" in holder:
                holder["window"].close()
        except Exception as e:  # noqa: BLE001
            self.log("close: %s" % e)
