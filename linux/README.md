# MiniSnap for Linux

MiniSnap is free, open-source (MIT) screenshot and screen recording software. This folder is the
Linux version: Python 3 + GTK 4 + libadwaita, with screen access through **xdg-desktop-portal**, so it
works on Wayland (the Ubuntu default), on X11 and inside Flatpak. It follows the Windows and macOS
versions: the same tools, strings, colours and Vietnamese / English interface.

> **Honest note:** this version was written without a Linux desktop at hand. It is exercised in CI on
> `ubuntu-24.04` under Xvfb by a headless self-test (`--selftest`, see below) that renders every window
> to PNG in both languages and both colour schemes, but the portal-driven parts (screenshot, window
> picking, screen recording) can only be verified on a real desktop. Bug reports are very welcome.

## Requirements

Ubuntu 24.04 or newer (GTK 4.14, libadwaita 1.5, Python 3.12, PyGObject 3.48, GStreamer 1.24,
PipeWire 1.0). Install the dependencies:

```sh
sudo apt install python3 python3-gi python3-gi-cairo python3-cairo \
    gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gstreamer-1.0 \
    xdg-desktop-portal xdg-desktop-portal-gnome \
    gstreamer1.0-pipewire gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly \
    tesseract-ocr tesseract-ocr-vie tesseract-ocr-eng
```

* `xdg-desktop-portal-gnome` is for GNOME; on KDE use `xdg-desktop-portal-kde`, on wlroots
  compositors (Sway, …) `xdg-desktop-portal-wlr`.
* `gstreamer1.0-plugins-ugly` provides the H.264 encoder (`x264enc`). Without it MiniSnap falls back to
  `openh264enc` (`gstreamer1.0-plugins-bad`) or to VP8 / WebM.
* Tesseract is only needed for text extraction (OCR); everything else works without it.

No `pip` packages are needed.

## Run from source

```sh
cd linux
python3 -m minisnap                      # the launcher window
python3 -m minisnap --capture region     # or use the wrapper script:
./bin/minisnap --capture region
```

Command-line options (a second invocation is passed to the running instance):

| Option | Action |
|---|---|
| *(none)* | show the launcher window |
| `--capture region` | drag a region (or click a screen) on a frozen screenshot |
| `--capture full` | capture the whole desktop |
| `--capture delayed` | region capture after 3 seconds |
| `--capture window` | let the desktop's screenshot UI pick a window |
| `--record` | record the screen; run it again to stop |
| `--ocr` | select an area and extract its text |
| `--library` | the image & video library |
| `--about` | About MiniSnap |
| `--selftest DIR` | headless self-test, writes `DIR/log.txt` and PNGs |
| `IMAGE…` | open images in the editor |

Captures go to `~/Pictures/MiniSnap`, recordings to `~/Videos/MiniSnap` (your XDG user folders).
Settings are stored in `~/.config/minisnap/settings.json`.

## Keyboard shortcuts

Global hotkeys are set in the desktop's own settings in this version. On GNOME:

1. *Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts*
2. Click **+**, give it a name and enter a command, for example:
   * `minisnap --capture region`
   * `minisnap --capture full`
   * `minisnap --record`
   * `minisnap --ocr`
   * `minisnap --library`
3. Click *Set Shortcut…* and press the keys (e.g. Ctrl+Alt+C).

When running from source, use the full path of `linux/bin/minisnap` instead of `minisnap`. The menu
item **Keyboard shortcuts…** in the launcher shows the exact commands with copy buttons. GNOME keeps the
Print Screen key for its own screenshot tool; remove it under *Screenshots* first if you want it for
MiniSnap.

## Wayland notes

* Wayland does not let applications read the screen directly. MiniSnap asks the **screenshot portal**
  for a full-desktop image and shows it frozen for you to select from. The first time, your desktop may
  ask for permission.
* Applications can't see where other windows are, so hovering doesn't highlight windows. Use
  **Pick a window** in the launcher (or `--capture window`): the desktop's own screenshot UI lets you
  choose a window, and the result opens in the editor.
* Screen recording uses the **ScreenCast portal**: your desktop asks which screen to share each time.
  The selected region is cropped from that screen's stream.
* Apps can't keep a window on top or hide it from recordings on Wayland, so the small recording window
  (timer, Pause, Stop) is a normal window. Run `minisnap --record` again (e.g. from your shortcut) to stop.

## Phase 1 and phase 2

Phase 1 (this version):

* region / full-screen / delayed capture with a magnifier, pixel size and colour readout, multi-monitor
* the post-selection bar (Screenshot / Record video, width × height, reselect, resize and move handles)
* window capture through the system picker
* the annotation editor: arrow, box, ellipse, line, pen, highlight, text, blur, step numbers, crop,
  undo/redo, zoom, copy / save / save as; every capture auto-saved and copied to the clipboard
* screen recording to MP4 (portal + PipeWire + GStreamer), with countdown, pause and stop
* OCR with Tesseract (Vietnamese + English), the library, update check, About, Vietnamese / English UI

Phase 2 (next):

* scrolling capture (the stitcher is already included and tested; the button is shown disabled)
* real global hotkeys through the GlobalShortcuts portal, and a tray / background mode

## Self-test

```sh
cd linux
xvfb-run -a -s "-screen 0 1600x1000x24" python3 -m minisnap --selftest /tmp/minisnap-selftest
```

It never calls a portal. It renders all annotation types (`render.png`), runs the scrolling-capture
stitcher on a synthetic page with a sticky header and footer (`stitch.png`, height must match), runs
Tesseract, encodes a short test video with GStreamer, checks that every UI string has an English
translation, and saves PNGs of the launcher, editor, capture overlay with the mode bar, library, About
and shortcuts windows, e.g. `editor-vi-dark.png`, `launcher-en-light.png`. The exit code is non-zero if
any step failed; details are in `log.txt`.

## License

MIT — see [LICENSE](../LICENSE). Privacy: see [PRIVACY.md](../PRIVACY.md); MiniSnap collects no data.
