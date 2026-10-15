import AppKit
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import CoreVideo

/// Records a display area to H.264 MP4 with ScreenCaptureKit + AVAssetWriter (video only, 30 fps, cursor included).
final class ScreenRecorder: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    static let fps: Int32 = 30

    let url: URL
    private let displayID: CGDirectDisplayID
    private let localRect: CGRect
    private let fullDisplay: Bool
    private let outWidth: Int
    private let outHeight: Int

    private var stream: SCStream?
    private var writer: AVAssetWriter?
    private var input: AVAssetWriterInput?
    private var adaptor: AVAssetWriterInputPixelBufferAdaptor?
    private let queue = DispatchQueue(label: "io.github.kingrubic.minisnap.recorder")
    private let lock = NSLock()

    // Guarded by `lock`.
    private var paused = false
    private var resumePending = false
    private var stopping = false
    private var sessionStarted = false
    private var offset = CMTime.zero
    private var lastPTS = CMTime.invalid
    private var activeSince: Date?
    private var accumulated: TimeInterval = 0
    private var framesWritten = 0

    /// Called on the main queue if the stream stops by itself (display gone, permission revoked...).
    var onStreamError: ((Error) -> Void)?

    /// `localRect`: points relative to the display's top-left corner.
    init(display: DisplayInfo, localRect: CGRect, url: URL) {
        self.url = url
        displayID = display.displayID
        let full = CGRect(x: 0, y: 0, width: display.frame.width, height: display.frame.height)
        let clipped = localRect.intersection(full)
        let area = clipped.isNull ? full : clipped
        self.localRect = area
        fullDisplay = abs(area.width - full.width) < 1 && abs(area.height - full.height) < 1
        // H.264 needs even dimensions; very large areas are scaled down to 4K.
        let pxW = Double(area.width * display.scale)
        let pxH = Double(area.height * display.scale)
        let s = min(1.0, min(3840.0 / max(1, pxW), 2160.0 / max(1, pxH)))
        outWidth = max(2, Int(pxW * s) & ~1)
        outHeight = max(2, Int(pxH * s) & ~1)
        super.init()
    }

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    var isPaused: Bool { locked { paused } }

    var elapsed: TimeInterval {
        locked { () -> TimeInterval in
            var t = accumulated
            if let s = activeSince { t += Date().timeIntervalSince(s) }
            return t
        }
    }

    func start() async throws {
        let content = try await ScreenCapture.shareableContent()
        guard let display = content.displays.first(where: { $0.displayID == displayID }) else { throw CaptureError.noDisplay }
        let filter = ScreenCapture.filter(for: display, in: content)

        let config = SCStreamConfiguration()
        if !fullDisplay { config.sourceRect = localRect }
        config.width = outWidth
        config.height = outHeight
        config.minimumFrameInterval = CMTime(value: 1, timescale: ScreenRecorder.fps)
        config.showsCursor = true
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.queueDepth = 6

        try? FileManager.default.removeItem(at: url)
        let w = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let bitrate = max(2_000_000, min(16_000_000, outWidth * outHeight * Int(ScreenRecorder.fps) / 8))
        let settings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: outWidth,
            AVVideoHeightKey: outHeight,
            AVVideoCompressionPropertiesKey: [
                AVVideoAverageBitRateKey: bitrate,
                AVVideoExpectedSourceFrameRateKey: Int(ScreenRecorder.fps),
                AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel
            ] as [String: Any]
        ]
        let inp = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        inp.expectsMediaDataInRealTime = true
        guard w.canAdd(inp) else { throw CaptureError.failed("The video encoder rejected the output settings") }
        w.add(inp)
        let ad = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: inp, sourcePixelBufferAttributes: nil)
        guard w.startWriting() else {
            throw w.error ?? CaptureError.failed("Could not start writing the video file")
        }
        writer = w
        input = inp
        adaptor = ad

        let s = SCStream(filter: filter, configuration: config, delegate: self)
        try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: queue)
        stream = s
        try await s.startCapture()
        locked { () -> Void in activeSince = Date() }
    }

    func pause() {
        locked { () -> Void in
            if paused { return }
            paused = true
            if let s = activeSince { accumulated += Date().timeIntervalSince(s) }
            activeSince = nil
        }
    }

    func resume() {
        locked { () -> Void in
            if !paused { return }
            paused = false
            resumePending = true
            activeSince = Date()
        }
    }

    /// Stops capturing and finalises the file. Returns an error, or nil on success.
    func stop() async -> Error? {
        locked { () -> Void in
            stopping = true
            if let s = activeSince { accumulated += Date().timeIntervalSince(s) }
            activeSince = nil
        }
        if let s = stream {
            try? await s.stopCapture()
        }
        stream = nil
        guard let w = writer, let inp = input else { return CaptureError.failed("Recording did not start") }
        // Make sure no sample callback is still running before finishing.
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            queue.async { cont.resume() }
        }
        let started = locked { sessionStarted }
        if !started {
            w.cancelWriting()
            try? FileManager.default.removeItem(at: url)
            return CaptureError.failed("No video frames were captured")
        }
        inp.markAsFinished()
        await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
            w.finishWriting { cont.resume() }
        }
        if w.status == .failed { return w.error ?? CaptureError.failed("Could not finish the video file") }
        return nil
    }

    // MARK: SCStreamOutput

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen, CMSampleBufferIsValid(sampleBuffer) else { return }
        guard let attachmentsArray = CMSampleBufferGetSampleAttachmentsArray(sampleBuffer, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
              let attachments = attachmentsArray.first,
              let statusRaw = attachments[SCStreamFrameInfo.status] as? Int,
              let status = SCFrameStatus(rawValue: statusRaw),
              status == .complete,
              let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)

        lock.lock()
        defer { lock.unlock() }
        guard !stopping, !paused, let w = writer, let inp = input, let ad = adaptor else { return }
        if w.status != .writing { return }
        if !sessionStarted {
            w.startSession(atSourceTime: pts)
            sessionStarted = true
            lastPTS = pts
        }
        if resumePending {
            // Remove the paused gap from the timeline.
            if lastPTS.isValid {
                let gap = CMTimeSubtract(CMTimeSubtract(pts, lastPTS), CMTime(value: 1, timescale: ScreenRecorder.fps))
                if CMTimeCompare(gap, .zero) > 0 { offset = CMTimeAdd(offset, gap) }
            }
            resumePending = false
        }
        let t = CMTimeSubtract(pts, offset)
        if inp.isReadyForMoreMediaData {
            if ad.append(pixelBuffer, withPresentationTime: t) { framesWritten += 1 }
        }
        lastPTS = pts
    }

    // MARK: SCStreamDelegate

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        let alreadyStopping = locked { stopping }
        if alreadyStopping { return }
        let handler = onStreamError
        DispatchQueue.main.async {
            handler?(error)
        }
    }
}

/// Red outline drawn just outside the recorded area; click-through and hidden from capture.
@MainActor
final class RegionFrameWindow {
    let window: NSWindow

    final class FrameView: NSView {
        override func draw(_ dirtyRect: NSRect) {
            NSColor(srgbRed: 235 / 255, green: 40 / 255, blue: 40 / 255, alpha: 0.9).setStroke()
            let p = NSBezierPath(rect: bounds.insetBy(dx: 1.5, dy: 1.5))
            p.lineWidth = 3
            p.stroke()
        }
    }

    /// `area` in Cocoa screen coordinates.
    init(area: NSRect) {
        let t: CGFloat = 3
        window = NSWindow(contentRect: area.insetBy(dx: -t, dy: -t), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = false
        window.ignoresMouseEvents = true
        window.level = .statusBar
        window.sharingType = .none
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        window.contentView = FrameView(frame: NSRect(origin: .zero, size: window.frame.size))
    }

    func show() { window.orderFrontRegardless() }
    func close() { window.orderOut(nil) }
}

/// Countdown, timer, pause and stop controls for a recording.
@MainActor
final class RecordingController: NSObject {
    private let display: DisplayInfo
    private let localRect: CGRect
    private let onDone: (URL?, Error?) -> Void
    private let bar = FloatingBar()
    private var timeLabel = NSTextField(labelWithString: "")
    private var pauseButton = NSButton()
    private var stopButton = NSButton()
    private var frame: RegionFrameWindow?
    private var recorder: ScreenRecorder?
    private var ticker: Task<Void, Never>?
    private var stopping = false
    private var finished = false

    var isActive: Bool { !finished }

    /// `localRect`: points relative to the display's top-left corner.
    init(display: DisplayInfo, localRect: CGRect, onDone: @escaping (URL?, Error?) -> Void) {
        self.display = display
        self.localRect = localRect
        self.onDone = onDone
        super.init()
        timeLabel = bar.makeLabel(L.t("Bắt đầu sau 3..."), bold: true)
        timeLabel.translatesAutoresizingMaskIntoConstraints = false
        timeLabel.widthAnchor.constraint(greaterThanOrEqualToConstant: 120).isActive = true
        pauseButton = bar.makeButton(L.t("Tạm dừng"), symbolName: "pause.fill", target: self, action: #selector(pausePressed))
        pauseButton.isEnabled = false
        stopButton = bar.makeButton(L.t("Dừng"), symbolName: "stop.fill", target: self, action: #selector(stopPressed))
        bar.stack.addArrangedSubview(timeLabel)
        bar.stack.addArrangedSubview(pauseButton)
        bar.stack.addArrangedSubview(stopButton)
    }

    private var globalRect: CGRect { localRect.offsetBy(dx: display.frame.minX, dy: display.frame.minY) }

    func start() {
        let cocoa = ScreenCapture.cocoaRect(fromQuartz: globalRect)
        let screen = ScreenCapture.screen(for: display.displayID)
        bar.place(near: cocoa, on: screen)
        bar.orderFrontRegardless()
        let f = RegionFrameWindow(area: cocoa)
        f.show()
        frame = f
        ticker = Task { [weak self] in
            for n in [3, 2, 1] {
                self?.timeLabel.stringValue = L.t("Bắt đầu sau ") + String(n) + "..."
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                if Task.isCancelled { return }
            }
            await self?.beginRecording()
        }
    }

    private func beginRecording() async {
        if stopping { return }
        let rec = ScreenRecorder(display: display, localRect: localRect, url: LibraryPaths.newVideoURL())
        rec.onStreamError = { [weak self] _ in
            MainActor.assumeIsolated { self?.stopRecording() }
        }
        recorder = rec
        do {
            try await rec.start()
        } catch {
            recorder = nil
            done(nil, error)
            return
        }
        if stopping { return }
        pauseButton.isEnabled = true
        ticker = Task { [weak self] in
            while !Task.isCancelled {
                self?.updateTime()
                try? await Task.sleep(nanoseconds: 250_000_000)
            }
        }
    }

    private func updateTime() {
        guard let r = recorder else { return }
        let t = Int(r.elapsed)
        let paused = r.isPaused
        timeLabel.stringValue = (paused ? "⏸ " : "● ") + String(format: "%02d:%02d", t / 60, t % 60)
        timeLabel.textColor = paused ? NSColor.systemYellow : NSColor(srgbRed: 1, green: 90 / 255, blue: 90 / 255, alpha: 1)
    }

    @objc private func pausePressed() {
        guard let r = recorder else { return }
        if r.isPaused {
            r.resume()
            pauseButton.title = L.t("Tạm dừng")
            pauseButton.image = symbol("pause.fill", size: 13, weight: .semibold)
        } else {
            r.pause()
            pauseButton.title = L.t("Tiếp tục")
            pauseButton.image = symbol("record.circle", size: 13, weight: .semibold)
        }
        updateTime()
        bar.place(near: ScreenCapture.cocoaRect(fromQuartz: globalRect), on: ScreenCapture.screen(for: display.displayID))
    }

    @objc private func stopPressed() { stopRecording() }

    func stopRecording() {
        if stopping { return }
        stopping = true
        ticker?.cancel()
        guard let r = recorder else {
            done(nil, nil)
            return
        }
        timeLabel.stringValue = L.t("Đang lưu video...")
        timeLabel.textColor = .white
        pauseButton.isEnabled = false
        stopButton.isEnabled = false
        Task { [weak self] in
            let err = await r.stop()
            self?.done(err == nil ? r.url : nil, err)
        }
    }

    private func done(_ url: URL?, _ error: Error?) {
        if finished { return }
        finished = true
        ticker?.cancel()
        frame?.close()
        bar.orderOut(nil)
        onDone(url, error)
    }
}
