# MiniSnap for macOS

A small, free, open-source (MIT) Snagit-style screenshot and screen-recording app that lives in the menu bar.
This is the macOS port of the Windows version in `../windows`.

> **Note:** The macOS version was written without access to a Mac and has only been compile-checked in CI; please report issues.

## Requirements

- macOS 14 Sonoma or newer (Apple silicon or Intel).
- On macOS 26 Tahoe the UI uses Liquid Glass; on macOS 14–15 it falls back to the classic translucent materials.

## Permissions

| Permission | Needed for | Where |
|---|---|---|
| **Screen Recording** (Screen & System Audio Recording) | every screenshot, recording and OCR capture | System Settings → Privacy & Security → Screen & System Audio Recording |
| **Accessibility** | scrolling capture only (MiniSnap posts scroll-wheel events to the window) | System Settings → Privacy & Security → Accessibility |

MiniSnap asks for these when they are first needed. After turning Screen Recording on, quit and reopen MiniSnap.
Because the app is ad-hoc signed, macOS may ask again after you install a new build.

## Install

1. Download `MiniSnap-macOS.zip`, unzip it and move `MiniSnap.app` to `/Applications`.
2. The app is **unsigned** (ad-hoc signature, not notarized), so the first launch is blocked by Gatekeeper.
   Either right-click `MiniSnap.app` → **Open** → **Open**, or run:

   ```bash
   xattr -dr com.apple.quarantine /Applications/MiniSnap.app
   ```

3. MiniSnap appears as a camera icon in the menu bar (it has no Dock icon).

## Build

Requires Xcode 15 or newer (Swift 5.9+; Xcode 26 / Swift 6.2 enables the Liquid Glass UI). No Xcode project is needed:

```bash
cd macos
bash build.sh
```

`build.sh` runs `swift build -c release` for arm64 + x86_64 (falling back to the native architecture),
assembles `dist/MiniSnap.app`, generates the app icon, ad-hoc signs the bundle and zips it to
`dist/MiniSnap-macOS.zip`.

## Default keyboard shortcuts

⌘⇧3/4/5 belong to macOS, so MiniSnap uses ⌥⇧ combinations. All of them can be changed in
**Keyboard shortcuts...** from the menu-bar icon.

| Action | Shortcut |
|---|---|
| Capture region / window | ⌥⇧2 |
| Capture full screen | ⌥⇧1 |
| Capture region after 3 seconds | ⌥⇧3 |
| Scrolling capture | ⌥⇧S |
| Record screen video (start / stop) | ⌥⇧R |
| Capture and extract text (OCR) | ⌥⇧O |
| Open the library | ⌥⇧L |

In the capture overlay: click a window or drag an area; **Esc** or right-click cancels; **Enter** takes the whole screen.
With "Ask screenshot / video / scroll after selecting" turned on (default), a small bar appears next to the selection:
**Enter** = screenshot, **V** = record video, **S** = scrolling capture, **R** = reselect, **Esc** = cancel;
drag the edges to resize, drag inside to move, or type an exact width × height.

In the editor: **V A R E L P H T B N C** pick tools, **⌘C** copies, **⌘S** saves, **⇧⌘S** saves as, **⌘Z / ⇧⌘Z** undo / redo,
**⌘+ / ⌘- / ⌘0 / ⌘1** zoom, **⌘-scroll** or pinch zooms, **Delete** removes the selected annotation.

## Where files go

- Screenshots: `~/Pictures/MiniSnap/MiniSnap_yyyy-MM-dd_HH-mm-ss.png` (also copied to the clipboard)
- Videos: `~/Movies/MiniSnap/` (H.264 MP4, 30 fps)

## Updates

**Check for updates...** (menu or About window) looks at the latest GitHub release, downloads `MiniSnap-macOS.zip`,
verifies its SHA-256 checksum when GitHub provides one, unzips it and shows the new `MiniSnap.app` in Finder.
Quit MiniSnap and drag the new app into Applications (Replace). MiniSnap also checks silently once a day.

## License

MIT — © Nguyễn Năng Quốc Bảo
