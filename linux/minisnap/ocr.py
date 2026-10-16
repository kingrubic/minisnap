"""Text recognition with the tesseract command-line tool (works offline).

`tesseract <png> stdout -l vie+eng`; falls back to whatever languages are installed.
"""

import os
import shutil
import subprocess
import tempfile
import threading

import cairo

from . import _gi  # noqa: F401
from gi.repository import Adw, GLib, Gtk

from . import render
from .i18n import L

FLATPAK_TESSDATA = "/app/share/tessdata"


class TesseractMissing(Exception):
    pass


def tesseract_path():
    return shutil.which("tesseract")


def _base_cmd():
    exe = tesseract_path()
    if exe is None:
        raise TesseractMissing()
    cmd = [exe]
    # Inside the Flatpak the language data ships in /app/share/tessdata.
    if not os.environ.get("TESSDATA_PREFIX") and os.path.isdir(FLATPAK_TESSDATA):
        cmd += ["--tessdata-dir", FLATPAK_TESSDATA]
    return cmd


def _env():
    env = dict(os.environ)
    env.setdefault("OMP_THREAD_LIMIT", "1")   # tesseract is faster single-threaded on small images
    return env


def available_languages():
    """Installed traineddata names, e.g. ['eng', 'osd', 'vie']."""
    out = subprocess.run(_base_cmd() + ["--list-langs"], capture_output=True, text=True, timeout=30, env=_env())
    langs = []
    for line in (out.stdout or "").splitlines():
        line = line.strip()
        if not line or line.endswith(":") or " " in line:
            continue
        langs.append(line)
    return langs


def pick_languages(available):
    wanted = [l for l in ("vie", "eng") if l in available]
    if not wanted:
        wanted = [l for l in available if l != "osd"][:1]
    return wanted


def prepare(src):
    """Small screenshots are upscaled (OCR is far more accurate on larger glyphs) onto white."""
    w, h = render.size(src)
    longest = max(w, h)
    scale = 1.0
    if longest < 1500:
        scale = min(3.0, 1500.0 / longest)
    if longest * scale > 10000:
        scale = 10000.0 / longest
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    out = render.new_surface(nw, nh)
    cr = cairo.Context(out)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    cr.scale(nw / float(w), nh / float(h))
    cr.set_source_surface(src, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_BEST)
    cr.paint()
    out.flush()
    return out


def recognize(surface):
    """Returns (text, languages). Raises TesseractMissing or RuntimeError."""
    langs = pick_languages(available_languages())
    if not langs:
        raise RuntimeError(L.t("Tesseract chưa có dữ liệu ngôn ngữ nào."))
    fd, tmp = tempfile.mkstemp(prefix="minisnap-ocr-", suffix=".png")
    os.close(fd)
    try:
        prepare(surface).write_to_png(tmp)
        proc = subprocess.run(_base_cmd() + [tmp, "stdout", "-l", "+".join(langs)],
                              capture_output=True, text=True, timeout=180, env=_env())
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or "").strip() or "tesseract exit code %d" % proc.returncode)
        text = (proc.stdout or "").replace("\f", "").strip()
        # Tesseract separates paragraphs with blank lines; collapse runs of them.
        lines = text.splitlines()
        out, blank = [], False
        for line in lines:
            if line.strip():
                out.append(line.rstrip())
                blank = False
            elif not blank and out:
                out.append("")
                blank = True
        return "\n".join(out).strip(), langs
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class OcrWindow(Adw.ApplicationWindow):
    def __init__(self, app, image):
        super().__init__(application=app)
        self.set_title(L.t("Trích chữ (OCR) — MiniSnap"))
        self.set_default_size(640, 480)

        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.text = Gtk.TextView()
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.set_left_margin(12)
        self.text.set_right_margin(12)
        self.text.set_top_margin(12)
        self.text.set_bottom_margin(12)
        self.text.set_editable(False)
        self.text.add_css_class("ms-ocr-text")
        self.text.get_buffer().set_text(L.t("Đang nhận dạng chữ..."), -1)
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_child(self.text)
        view.set_content(scroll)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bottom.set_margin_start(12)
        bottom.set_margin_end(12)
        bottom.set_margin_top(8)
        bottom.set_margin_bottom(8)
        self.info = Gtk.Label(xalign=0)
        self.info.set_wrap(True)
        self.info.set_hexpand(True)
        self.info.add_css_class("dim-label")
        self.copy_btn = Gtk.Button(label=L.t("Sao chép chữ"))
        self.copy_btn.add_css_class("suggested-action")
        self.copy_btn.set_sensitive(False)
        self.copy_btn.connect("clicked", lambda *_: self.copy_text())
        close = Gtk.Button(label=L.t("Đóng"))
        close.connect("clicked", lambda *_: self.close())
        bottom.append(self.info)
        bottom.append(self.copy_btn)
        bottom.append(close)
        view.add_bottom_bar(bottom)
        self.set_content(view)

        copy = render.copy_surface(image)
        threading.Thread(target=self._work, args=(copy,), daemon=True).start()

    def _work(self, image):
        result, error, missing = None, None, False
        try:
            result = recognize(image)
        except TesseractMissing:
            missing = True
        except Exception as e:  # noqa: BLE001
            error = str(e)
        GLib.idle_add(self._show, result, error, missing)

    def _set_text(self, text):
        self.text.get_buffer().set_text(text, -1)

    def _show(self, result, error, missing):
        if missing:
            self._set_text(L.t("Chưa cài tesseract nên chưa trích chữ được.") + "\n\n"
                           + L.t("Cài bằng lệnh:") + "\n  sudo apt install tesseract-ocr tesseract-ocr-vie")
            return False
        if error is not None:
            self._set_text(L.t("Không nhận dạng được chữ: ") + error)
            return False
        text, langs = result
        self.text.set_editable(True)
        self._set_text(text if text else L.t("(Không tìm thấy chữ nào trong ảnh)"))
        self.copy_btn.set_sensitive(bool(text))
        info = L.t("Ngôn ngữ: ") + "+".join(langs)
        if "vie" not in langs:
            info += "\n" + L.t("Muốn đọc tiếng Việt có dấu: sudo apt install tesseract-ocr-vie")
        self.info.set_text(info)
        if text:
            self.copy_text()
            buf = self.text.get_buffer()
            buf.place_cursor(buf.get_start_iter())
        return False

    def copy_text(self):
        buf = self.text.get_buffer()
        text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        if not text:
            return
        try:
            self.get_display().get_clipboard().set_text(text)
            self.copy_btn.set_label(L.t("✓ Đã sao chép"))
        except Exception:  # noqa: BLE001
            pass
