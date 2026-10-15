import AppKit
import ScreenCaptureKit
import ImageIO
import UniformTypeIdentifiers

/// One physical display. `frame` is in global Quartz points (top-left origin of the primary display).
struct DisplayInfo {
    let displayID: CGDirectDisplayID
    let frame: CGRect
    let scale: CGFloat
}

/// A frozen screenshot of one display, in that display's pixel space.
struct DisplayShot {
    let display: DisplayInfo
    let image: CGImage
}

enum CaptureError: LocalizedError {
    case noDisplay
    case failed(String)

    var errorDescription: String? {
        switch self {
        case .noDisplay: return "No display found"
        case .failed(let s): return s
        }
    }
}

enum ScreenCapture {
    @MainActor
    static func screenNumber(_ screen: NSScreen) -> CGDirectDisplayID? {
        let key = NSDeviceDescriptionKey("NSScreenNumber")
        if let n = screen.deviceDescription[key] as? NSNumber { return n.uint32Value }
        return nil
    }

    @MainActor
    static func screen(for id: CGDirectDisplayID) -> NSScreen? {
        NSScreen.screens.first { screenNumber($0) == id }
    }

    /// Converts a global Quartz rect (top-left origin) to Cocoa screen coordinates (bottom-left origin).
    @MainActor
    static func cocoaRect(fromQuartz r: CGRect) -> NSRect {
        let primaryHeight = NSScreen.screens.first?.frame.height ?? r.maxY
        return NSRect(x: r.minX, y: primaryHeight - r.maxY, width: r.width, height: r.height)
    }

    /// Converts a Cocoa global point (bottom-left origin) to Quartz (top-left origin).
    @MainActor
    static func quartzPoint(fromCocoa p: NSPoint) -> CGPoint {
        let primaryHeight = NSScreen.screens.first?.frame.height ?? 0
        return CGPoint(x: p.x, y: primaryHeight - p.y)
    }

    @MainActor
    static func displayInfo(for display: SCDisplay) -> DisplayInfo {
        let id = display.displayID
        let bounds = CGDisplayBounds(id)
        var scale: CGFloat = 1
        if let s = screen(for: id) {
            scale = s.backingScaleFactor
        } else if bounds.width > 0, let mode = CGDisplayCopyDisplayMode(id) {
            scale = CGFloat(mode.pixelWidth) / bounds.width
        }
        return DisplayInfo(displayID: id, frame: bounds, scale: max(1, scale))
    }

    /// The display under the mouse pointer.
    @MainActor
    static func displayIDUnderMouse() -> CGDirectDisplayID? {
        let p = NSEvent.mouseLocation
        for s in NSScreen.screens where NSMouseInRect(p, s.frame, false) {
            return screenNumber(s)
        }
        if let main = NSScreen.main { return screenNumber(main) }
        return nil
    }

    static func shareableContent() async throws -> SCShareableContent {
        try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
    }

    /// Captures everything on `display`; with `excludeSelf`, MiniSnap's own windows (recording bar,
    /// red frame, scrolling-capture panel) are left out.
    static func filter(for display: SCDisplay, in content: SCShareableContent, excludeSelf: Bool = true) -> SCContentFilter {
        if !excludeSelf {
            return SCContentFilter(display: display, excludingWindows: [])
        }
        let pid = ProcessInfo.processInfo.processIdentifier
        let mine = content.applications.filter { $0.processID == pid }
        return SCContentFilter(display: display, excludingApplications: mine, exceptingWindows: [])
    }

    /// Screenshots every display at full pixel resolution (MiniSnap's own windows, e.g. an editor, are included).
    @MainActor
    static func captureAllDisplays() async throws -> [DisplayShot] {
        let content = try await shareableContent()
        var shots: [DisplayShot] = []
        for d in content.displays {
            let info = displayInfo(for: d)
            let img = try await capture(display: d, content: content, info: info, localRect: nil, excludeSelf: false)
            shots.append(DisplayShot(display: info, image: img))
        }
        if shots.isEmpty { throw CaptureError.noDisplay }
        return shots
    }

    /// Screenshot of one display without MiniSnap's own windows, optionally only `localRect`
    /// (points, relative to the display's top-left). Used by scrolling capture.
    @MainActor
    static func captureDisplay(id: CGDirectDisplayID, localRect: CGRect?) async throws -> CGImage {
        let content = try await shareableContent()
        guard let d = content.displays.first(where: { $0.displayID == id }) else { throw CaptureError.noDisplay }
        let info = displayInfo(for: d)
        return try await capture(display: d, content: content, info: info, localRect: localRect, excludeSelf: true)
    }

    @MainActor
    private static func capture(display: SCDisplay, content: SCShareableContent, info: DisplayInfo, localRect: CGRect?, excludeSelf: Bool) async throws -> CGImage {
        let filter = self.filter(for: display, in: content, excludeSelf: excludeSelf)
        let config = SCStreamConfiguration()
        let area = localRect ?? CGRect(x: 0, y: 0, width: info.frame.width, height: info.frame.height)
        if localRect != nil { config.sourceRect = area }
        config.width = max(1, Int((area.width * info.scale).rounded()))
        config.height = max(1, Int((area.height * info.scale).rounded()))
        config.showsCursor = false
        config.scalesToFit = false
        return try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
    }

    /// Visible normal (layer 0) windows, front to back, in global Quartz points.
    /// CGWindowListCopyWindowInfo is used (not the obsoleted CGWindowListCreateImage) because it returns z-order.
    static func windowRects() -> [CGRect] {
        let opts: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
        guard let list = CGWindowListCopyWindowInfo(opts, kCGNullWindowID) as? [[String: Any]] else { return [] }
        // Called before the overlay exists, so MiniSnap's own windows here are editors / library: keep them.
        var result: [CGRect] = []
        for w in list {
            let layer = (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0
            if layer != 0 { continue }
            let alpha = (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 1
            if alpha <= 0.01 { continue }
            guard let dict = w[kCGWindowBounds as String] as? NSDictionary,
                  let r = CGRect(dictionaryRepresentation: dict as CFDictionary) else { continue }
            if r.width >= 8 && r.height >= 8 { result.append(r) }
        }
        return result
    }
}

// MARK: - Bitmap helpers

enum ImageUtil {
    static let sRGB: CGColorSpace = CGColorSpace(name: CGColorSpace.sRGB) ?? CGColorSpaceCreateDeviceRGB()

    /// RGBA8 premultiplied context; memory row 0 is the top row of the image.
    static func makeContext(width: Int, height: Int) -> CGContext? {
        CGContext(data: nil, width: max(1, width), height: max(1, height), bitsPerComponent: 8,
                  bytesPerRow: max(1, width) * 4, space: sRGB,
                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
    }

    static func crop(_ image: CGImage, to rect: CGRect) -> CGImage? {
        let bounds = CGRect(x: 0, y: 0, width: image.width, height: image.height)
        let r = rect.integral.intersection(bounds)
        if r.isNull || r.width < 1 || r.height < 1 { return nil }
        return image.cropping(to: r)
    }

    static func pngData(_ image: CGImage) -> Data? {
        let rep = NSBitmapImageRep(cgImage: image)
        return rep.representation(using: .png, properties: [:])
    }

    static func jpegData(_ image: CGImage, quality: Double = 0.92) -> Data? {
        // JPEG has no alpha: flatten onto white first.
        guard let ctx = makeContext(width: image.width, height: image.height) else { return nil }
        let r = CGRect(x: 0, y: 0, width: image.width, height: image.height)
        ctx.setFillColor(CGColor(gray: 1, alpha: 1))
        ctx.fill(r)
        ctx.draw(image, in: r)
        guard let flat = ctx.makeImage() else { return nil }
        let rep = NSBitmapImageRep(cgImage: flat)
        return rep.representation(using: .jpeg, properties: [.compressionFactor: NSNumber(value: quality)])
    }

    static func write(_ image: CGImage, to url: URL) throws {
        let ext = url.pathExtension.lowercased()
        let data: Data?
        if ext == "jpg" || ext == "jpeg" {
            data = jpegData(image)
        } else {
            data = pngData(image)
        }
        guard let d = data else { throw CaptureError.failed("Could not encode the image") }
        try d.write(to: url, options: .atomic)
    }

    static func load(_ url: URL) -> CGImage? {
        guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(src, 0, nil)
    }

    @MainActor
    static func copyToPasteboard(_ image: CGImage) -> Bool {
        let rep = NSBitmapImageRep(cgImage: image)
        let pb = NSPasteboard.general
        pb.clearContents()
        var ok = false
        if let png = rep.representation(using: .png, properties: [:]) {
            ok = pb.setData(png, forType: .png) || ok
        }
        if let tiff = rep.tiffRepresentation {
            ok = pb.setData(tiff, forType: .tiff) || ok
        }
        return ok
    }

    @MainActor
    static func nsImage(_ image: CGImage) -> NSImage {
        NSImage(cgImage: image, size: NSSize(width: image.width, height: image.height))
    }

    /// Draws `image` upright into `rect` of a context whose y axis points down (flipped NSView or flipped CGContext).
    static func drawUpright(_ image: CGImage, in rect: CGRect, context ctx: CGContext) {
        ctx.saveGState()
        ctx.translateBy(x: rect.minX, y: rect.maxY)
        ctx.scaleBy(x: 1, y: -1)
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: rect.width, height: rect.height))
        ctx.restoreGState()
    }
}

/// Direct pixel access to an image (RGBA8, sRGB). Pixel (x, y) uses top-left origin.
final class PixelImage {
    let width: Int
    let height: Int
    let context: CGContext
    let pixels: UnsafeMutablePointer<UInt32>

    init?(_ image: CGImage) {
        width = image.width
        height = image.height
        guard let ctx = ImageUtil.makeContext(width: width, height: height) else { return nil }
        ctx.interpolationQuality = .none
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        guard let raw = ctx.data else { return nil }
        context = ctx
        pixels = raw.bindMemory(to: UInt32.self, capacity: width * height)
    }

    /// 0x00BBGGRR (alpha dropped) — byte order R,G,B,A in memory, read as little-endian UInt32.
    @inline(__always) func rgb(_ x: Int, _ y: Int) -> UInt32 {
        pixels[y * width + x] & 0x00FF_FFFF
    }

    func color(_ x: Int, _ y: Int) -> (r: Int, g: Int, b: Int) {
        guard x >= 0, y >= 0, x < width, y < height else { return (0, 0, 0) }
        let v = pixels[y * width + x]
        return (Int(v & 0xFF), Int((v >> 8) & 0xFF), Int((v >> 16) & 0xFF))
    }
}
