"""Pins the GObject-introspection versions. Every module that uses gi.repository imports this first."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("Graphene", "1.0")

# DrawingArea callbacks hand us a real pycairo Context only when the gi <-> cairo bridge
# (python3-gi-cairo) is installed.
gi.require_foreign("cairo")

# GStreamer is only needed for screen recording; the rest of the app works without it.
try:
    gi.require_version("Gst", "1.0")
    HAVE_GST = True
except ValueError:
    HAVE_GST = False
