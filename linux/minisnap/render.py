"""Image helpers and the flattener (Renderer in windows/src/Shapes.cs).

Every image in the app is a cairo.ImageSurface in FORMAT_ARGB32 (premultiplied, native endian).
"""

import io
import os
import sys

import cairo

from . import _gi  # noqa: F401
from gi.repository import Gdk, GdkPixbuf, GLib

from .shapes import BlurShape


def new_surface(w, h):
    return cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(w)), max(1, int(h)))


def size(surface):
    return surface.get_width(), surface.get_height()


def copy_surface(src):
    out = new_surface(src.get_width(), src.get_height())
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(src, 0, 0)
    cr.paint()
    out.flush()
    return out


def crop(src, rect):
    """Copy of the pixels in rect (x, y, w, h), clipped to the image."""
    x, y, w, h = (int(round(v)) for v in rect)
    x2, y2 = min(src.get_width(), x + w), min(src.get_height(), y + h)
    x, y = max(0, x), max(0, y)
    w, h = max(1, x2 - x), max(1, y2 - y)
    out = new_surface(w, h)
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.set_source_surface(src, -x, -y)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.paint()
    out.flush()
    return out


def render(base, shapes):
    """Flattens the annotations onto a copy of the base image."""
    out = copy_surface(base)
    for s in shapes:
        if isinstance(s, BlurShape):
            # Blur reads the pixels drawn so far, like the Windows version.
            s.apply(out)
            continue
        cr = cairo.Context(out)
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        s.draw(cr)
        del cr
        out.flush()
    return out


# ---------- Loading and saving ----------

def surface_from_pixbuf(pixbuf):
    w, h = pixbuf.get_width(), pixbuf.get_height()
    out = new_surface(w, h)
    cr = cairo.Context(out)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    out.flush()
    return out


def load_surface(path):
    """Reads any image GdkPixbuf understands. Raises GLib.Error / OSError."""
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    rotated = pixbuf.apply_embedded_orientation()
    return surface_from_pixbuf(rotated or pixbuf)


def png_bytes(surface):
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def to_pixbuf(surface):
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(png_bytes(surface))
    loader.close()
    return loader.get_pixbuf()


def save_image(surface, path):
    """PNG, or JPEG (quality 92, on white) for .jpg/.jpeg. Raises on failure."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        flat = new_surface(surface.get_width(), surface.get_height())
        cr = cairo.Context(flat)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.set_source_surface(surface, 0, 0)
        cr.paint()
        flat.flush()
        # The image is opaque now; gdk-pixbuf's JPEG writer skips the alpha channel.
        to_pixbuf(flat).savev(path, "jpeg", ["quality"], ["92"])
    else:
        surface.write_to_png(path)


def to_texture(surface):
    """Gdk.Texture for the clipboard and for display."""
    surface.flush()
    w, h, stride = surface.get_width(), surface.get_height(), surface.get_stride()
    data = GLib.Bytes.new(bytes(surface.get_data()))
    fmt = (Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED if sys.byteorder == "little"
           else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED)
    return Gdk.MemoryTexture.new(w, h, fmt, data, stride)


def pixel_rgb(surface, x, y):
    """(r, g, b) of one pixel (alpha ignored), or (0, 0, 0) outside the image."""
    if x < 0 or y < 0 or x >= surface.get_width() or y >= surface.get_height():
        return (0, 0, 0)
    data = surface.get_data()
    o = y * surface.get_stride() + x * 4
    if sys.byteorder == "little":
        b, g, r = data[o], data[o + 1], data[o + 2]
    else:
        r, g, b = data[o + 1], data[o + 2], data[o + 3]
    return (r, g, b)


def copy_to_clipboard(surface, display=None):
    """Copies the image; returns True on success."""
    display = display or Gdk.Display.get_default()
    if display is None:
        return False
    try:
        display.get_clipboard().set_texture(to_texture(surface))
        return True
    except Exception:  # noqa: BLE001
        return False
