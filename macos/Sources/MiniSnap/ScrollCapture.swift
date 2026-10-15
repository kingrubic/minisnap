import AppKit
import Carbon

/// Row-matching stitcher for scrolling capture (port of the Windows ScrollStitcher).
/// Kept free of UI so it can be reasoned about on synthetic frames.
final class ScrollStitcher {
    private struct Rows {
        var hash: [UInt64]
        var uniform: [Bool]
    }

    private struct Segment {
        let frame: CGImage
        let y: Int
        var height: Int
    }

    enum Outcome {
        case added
        case noMovement
        case noMatch
    }

    private var segments: [Segment] = []
    private var frames: [CGImage] = []
    private var prevRows: Rows?
    private var frameH = 0

    private(set) var totalHeight = 0
    private(set) var lastShift = 0
    private(set) var lastUsableHeight = 0
    var frameCount: Int { frames.count }

    private static func analyze(_ img: CGImage) -> Rows? {
        guard let px = PixelImage(img) else { return nil }
        let w = px.width, h = px.height
        // Skip the right edge: a moving scrollbar thumb would make every row look different.
        let x0 = min(4, w / 4)
        let x1 = max(x0 + 1, w - min(28, w / 4))
        var hashes = [UInt64](repeating: 0, count: h)
        var uniform = [Bool](repeating: false, count: h)
        // `pixels` points into memory owned by `px`, so keep `px` alive while reading it.
        withExtendedLifetime(px) {
            let p = px.pixels
            for y in 0..<h {
                let o = y * w
                var hash: UInt64 = 1_469_598_103_934_665_603
                let first = p[o + x0] & 0x00FF_FFFF
                var uni = true
                var x = x0
                while x < x1 {
                    let v = p[o + x] & 0x00FF_FFFF
                    if v != first { uni = false }
                    hash = (hash ^ UInt64(v)) &* 1_099_511_628_211
                    x += 1
                }
                hashes[y] = hash
                uniform[y] = uni
            }
        }
        return Rows(hash: hashes, uniform: uniform)
    }

    func addFirst(_ frame: CGImage) {
        frames.append(frame)
        frameH = frame.height
        prevRows = ScrollStitcher.analyze(frame)
        segments.append(Segment(frame: frame, y: 0, height: frameH))
        totalHeight = frameH
    }

    func add(_ frame: CGImage) -> Outcome {
        guard let prev = prevRows, let cur = ScrollStitcher.analyze(frame), frame.height == frameH else { return .noMatch }
        let h = frameH
        var top = 0, bottom = 0
        while top < h && cur.hash[top] == prev.hash[top] { top += 1 }
        if top == h { return .noMovement }
        while bottom < h - top && cur.hash[h - 1 - bottom] == prev.hash[h - 1 - bottom] { bottom += 1 }
        // Unchanged bands at the edges are sticky headers/footers (or browser chrome).
        top = min(top, h * 2 / 5)
        bottom = min(bottom, h * 2 / 5)
        let usable = h - top - bottom
        lastUsableHeight = usable
        let minOverlap = 12

        var bestD = -1
        var bestScore = 0.0
        if usable - minOverlap >= 1 {
            for d in 1...(usable - minOverlap) {
                var total = 0, matches = 0
                var i = top
                while i + d < h - bottom {
                    if !cur.uniform[i] {
                        total += 1
                        if cur.hash[i] == prev.hash[i + d] { matches += 1 }
                    }
                    i += 1
                }
                if total < 6 { continue }
                let score = Double(matches) / Double(total)
                if score > bestScore + 1e-9 {
                    bestScore = score
                    bestD = d
                }
            }
        }
        if bestD < 0 || bestScore < 0.9 { return .noMatch }

        // Drop the previous frame's footer, then append the newly revealed rows plus the current footer.
        trim(bottom)
        segments.append(Segment(frame: frame, y: h - bottom - bestD, height: bestD + bottom))
        totalHeight += bestD + bottom
        frames.append(frame)
        prevRows = cur
        lastShift = bestD
        return .added
    }

    private func trim(_ rowsToDrop: Int) {
        var rows = rowsToDrop
        totalHeight -= rows
        while rows > 0, var last = segments.last {
            let take = min(rows, last.height)
            last.height -= take
            rows -= take
            segments.removeLast()
            if last.height > 0 { segments.append(last) }
        }
    }

    func compose() -> CGImage? {
        guard let first = frames.first, totalHeight > 0 else { return nil }
        let w = first.width
        guard let ctx = ImageUtil.makeContext(width: w, height: totalHeight) else { return nil }
        ctx.interpolationQuality = .none
        var y = 0
        for s in segments where s.height > 0 {
            if let piece = s.frame.cropping(to: CGRect(x: 0, y: s.y, width: w, height: s.height)) {
                // CGContext has a bottom-left origin: row y from the top lands at totalHeight - y - height.
                ctx.draw(piece, in: CGRect(x: 0, y: totalHeight - y - s.height, width: w, height: s.height))
            }
            y += s.height
        }
        return ctx.makeImage()
    }

    func reset() {
        frames.removeAll()
        segments.removeAll()
        prevRows = nil
        totalHeight = 0
    }
}

/// Drives the target window with scroll-wheel events and feeds frames to the stitcher.
/// Posting events needs the Accessibility permission (checked by the caller).
@MainActor
final class ScrollCaptureSession: NSObject {
    private static let maxHeight = 30000
    private static let maxFrames = 120
    private static let settleNanos: UInt64 = 450_000_000
    private static let pointsPerNotch: Int32 = 80

    private let displayID: CGDirectDisplayID
    private let localRect: CGRect
    private let globalRect: CGRect
    private let onDone: (CGImage?) -> Void
    private let stitcher = ScrollStitcher()
    private let bar = FloatingBar()
    private var status = NSTextField(labelWithString: "")
    private var notches: Int
    private var pendingScroll = 0
    private var failures = 0
    private var finished = false
    private var loop: Task<Void, Never>?
    private var globalMonitor: Any?
    private var localMonitor: Any?

    /// `localRect`: points relative to the display's top-left corner.
    init(display: DisplayInfo, localRect: CGRect, onDone: @escaping (CGImage?) -> Void) {
        displayID = display.displayID
        self.localRect = localRect
        globalRect = localRect.offsetBy(dx: display.frame.minX, dy: display.frame.minY)
        self.onDone = onDone
        notches = localRect.height < 350 ? 1 : 3
        super.init()
        status = bar.makeLabel(L.t("Đang chuẩn bị chụp cuộn..."))
        let stop = bar.makeButton(L.t("Dừng (Esc)"), symbolName: "stop.fill", target: self, action: #selector(stopPressed))
        bar.stack.addArrangedSubview(status)
        bar.stack.addArrangedSubview(stop)
    }

    func start() {
        let screen = ScreenCapture.screen(for: displayID)
        bar.place(near: ScreenCapture.cocoaRect(fromQuartz: globalRect), on: screen)
        bar.orderFrontRegardless()
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] e in
            if Int(e.keyCode) == kVK_Escape {
                MainActor.assumeIsolated { self?.finish() }
            }
        }
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            if Int(e.keyCode) == kVK_Escape {
                MainActor.assumeIsolated { self?.finish() }
                return nil
            }
            return e
        }
        loop = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 250_000_000) // let the selection overlay disappear first
            await self?.run()
        }
    }

    @objc private func stopPressed() { finish() }

    private var center: CGPoint { CGPoint(x: globalRect.midX, y: globalRect.midY) }

    private func scroll(_ n: Int) {
        _ = CGWarpMouseCursorPosition(center)
        let amount = Int32(-n) * ScrollCaptureSession.pointsPerNotch
        guard let ev = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1, wheel1: amount, wheel2: 0, wheel3: 0) else { return }
        ev.location = center
        ev.post(tap: .cghidEventTap)
    }

    private func settle() async {
        try? await Task.sleep(nanoseconds: ScrollCaptureSession.settleNanos)
    }

    private func run() async {
        while !finished {
            if pendingScroll != 0 {
                scroll(pendingScroll)
                pendingScroll = 0
                await settle()
                continue
            }
            let frame: CGImage
            do {
                frame = try await ScreenCapture.captureDisplay(id: displayID, localRect: localRect)
            } catch {
                finish()
                return
            }
            if finished { return }
            if stitcher.frameCount == 0 {
                stitcher.addFirst(frame)
                _ = CGWarpMouseCursorPosition(center)
            } else {
                switch stitcher.add(frame) {
                case .noMovement:
                    finish()
                    return
                case .noMatch:
                    // Probably scrolled further than one screen: go back and retry with a smaller step.
                    if failures < 2 && notches > 1 {
                        failures += 1
                        scroll(-notches)
                        notches = max(1, notches / 2)
                        pendingScroll = notches
                        await settle()
                        continue
                    }
                    finish()
                    return
                case .added:
                    failures = 0
                    let perNotch = Double(stitcher.lastShift) / Double(notches)
                    if perNotch > 0 {
                        notches = max(1, min(10, Int(Double(stitcher.lastUsableHeight) * 0.6 / perNotch)))
                    }
                }
            }
            status.stringValue = L.t("Đang chụp cuộn... ") + String(stitcher.frameCount) + L.t(" lần, cao ") + String(stitcher.totalHeight) + " px"
            bar.place(near: ScreenCapture.cocoaRect(fromQuartz: globalRect), on: ScreenCapture.screen(for: displayID))
            if stitcher.totalHeight >= ScrollCaptureSession.maxHeight || stitcher.frameCount >= ScrollCaptureSession.maxFrames {
                finish()
                return
            }
            scroll(notches)
            await settle()
        }
    }

    func finish() {
        if finished { return }
        finished = true
        loop?.cancel()
        if let m = globalMonitor { NSEvent.removeMonitor(m) }
        if let m = localMonitor { NSEvent.removeMonitor(m) }
        globalMonitor = nil
        localMonitor = nil
        bar.orderOut(nil)
        let result = stitcher.frameCount > 0 ? stitcher.compose() : nil
        stitcher.reset()
        onDone(result)
    }
}
