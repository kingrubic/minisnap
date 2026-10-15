// Draws the MiniSnap app icon into an .iconset folder (converted to .icns by build.sh with iconutil).
// Usage: swift Scripts/make_icon.swift dist/AppIcon.iconset
import AppKit

let outDir = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "AppIcon.iconset"
try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true, attributes: nil)

func drawIcon(_ s: CGFloat) {
    let full = NSRect(x: 0, y: 0, width: s, height: s)
    NSColor.clear.setFill()
    full.fill()

    // Background tile (macOS icon grid: ~10% margin, large corner radius).
    let tile = full.insetBy(dx: s * 0.1, dy: s * 0.1)
    let tilePath = NSBezierPath(roundedRect: tile, xRadius: s * 0.18, yRadius: s * 0.18)
    let top = NSColor(srgbRed: 0.16, green: 0.52, blue: 0.98, alpha: 1)
    let bottom = NSColor(srgbRed: 0.05, green: 0.30, blue: 0.80, alpha: 1)
    if let g = NSGradient(starting: bottom, ending: top) {
        g.draw(in: tilePath, angle: 90)
    } else {
        top.setFill()
        tilePath.fill()
    }

    // Viewfinder corner brackets.
    NSColor.white.setStroke()
    let inner = tile.insetBy(dx: tile.width * 0.17, dy: tile.height * 0.17)
    let len = inner.width * 0.26
    let w = max(1, s * 0.045)
    let corners: [(NSPoint, CGFloat, CGFloat)] = [
        (NSPoint(x: inner.minX, y: inner.maxY), 1, -1),
        (NSPoint(x: inner.maxX, y: inner.maxY), -1, -1),
        (NSPoint(x: inner.minX, y: inner.minY), 1, 1),
        (NSPoint(x: inner.maxX, y: inner.minY), -1, 1)
    ]
    for (p, dx, dy) in corners {
        let path = NSBezierPath()
        path.lineWidth = w
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.move(to: NSPoint(x: p.x + dx * len, y: p.y))
        path.line(to: p)
        path.line(to: NSPoint(x: p.x, y: p.y + dy * len))
        path.stroke()
    }

    // Lens.
    let r = inner.width * 0.2
    let lens = NSRect(x: inner.midX - r, y: inner.midY - r, width: 2 * r, height: 2 * r)
    NSColor.white.setFill()
    NSBezierPath(ovalIn: lens).fill()
    let r2 = r * 0.55
    NSColor(srgbRed: 0.05, green: 0.30, blue: 0.80, alpha: 1).setFill()
    NSBezierPath(ovalIn: NSRect(x: inner.midX - r2, y: inner.midY - r2, width: 2 * r2, height: 2 * r2)).fill()

    // Record dot.
    let d = inner.width * 0.12
    NSColor(srgbRed: 1, green: 0.27, blue: 0.23, alpha: 1).setFill()
    NSBezierPath(ovalIn: NSRect(x: inner.maxX - d * 1.1, y: inner.maxY - d * 1.1, width: d, height: d)).fill()
}

let sizes: [(Int, String)] = [
    (16, "icon_16x16"), (32, "icon_16x16@2x"), (32, "icon_32x32"), (64, "icon_32x32@2x"),
    (128, "icon_128x128"), (256, "icon_128x128@2x"), (256, "icon_256x256"), (512, "icon_256x256@2x"),
    (512, "icon_512x512"), (1024, "icon_512x512@2x")
]

for (px, name) in sizes {
    guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: px, pixelsHigh: px,
                                     bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                     colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { continue }
    rep.size = NSSize(width: px, height: px)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    drawIcon(CGFloat(px))
    NSGraphicsContext.restoreGraphicsState()
    if let data = rep.representation(using: .png, properties: [:]) {
        try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent(name + ".png"))
    }
}
print("Wrote " + outDir)
