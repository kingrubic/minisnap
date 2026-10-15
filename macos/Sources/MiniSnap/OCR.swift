import AppKit
import Vision

/// Text recognition with Apple's Vision framework (on-device, works offline).
enum OcrService {
    struct Result {
        let text: String
        let languages: [String]
    }

    /// Runs on a background queue; `completion` is called on the main queue.
    static func recognize(_ image: CGImage, completion: @escaping (Result?, String?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            var output: Result?
            var failure: String?
            do {
                output = try recognizeSync(image)
            } catch {
                failure = error.localizedDescription
            }
            let r = output, f = failure
            DispatchQueue.main.async {
                completion(r, f)
            }
        }
    }

    static func recognizeSync(_ image: CGImage) throws -> Result {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        var langs: [String] = []
        if let supported = try? request.supportedRecognitionLanguages() {
            // Vietnamese is reported as "vi-VT" on current systems; accept any "vi" variant.
            if let vi = supported.first(where: { $0.lowercased().hasPrefix("vi") }) { langs.append(vi) }
            if supported.contains("en-US") { langs.append("en-US") }
        }
        if !langs.isEmpty { request.recognitionLanguages = langs }

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        try handler.perform([request])

        var lines: [(y: CGFloat, x: CGFloat, text: String)] = []
        for o in request.results ?? [] {
            guard let best = o.topCandidates(1).first else { continue }
            lines.append((o.boundingBox.midY, o.boundingBox.minX, best.string))
        }
        // Vision boxes are normalised with a bottom-left origin: read top to bottom, left to right.
        lines.sort { a, b in
            if abs(a.y - b.y) > 0.01 { return a.y > b.y }
            return a.x < b.x
        }
        let text = lines.map { $0.text }.joined(separator: "\n")
        return Result(text: text.trimmingCharacters(in: .whitespacesAndNewlines), languages: langs)
    }
}

/// Result window: editable text, auto-copied to the clipboard.
@MainActor
final class OcrWindow: NSObject, NSWindowDelegate {
    let window: NSWindow
    private let textView = NSTextView()
    private let infoLabel = NSTextField(labelWithString: "")
    private var copyButton = NSButton()
    var onClose: (() -> Void)?

    init(image: CGImage) {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 480),
                          styleMask: [.titled, .closable, .resizable, .miniaturizable],
                          backing: .buffered, defer: false)
        super.init()
        window.isReleasedWhenClosed = false
        window.title = L.t("Trích chữ (OCR) — MiniSnap")
        window.minSize = NSSize(width: 380, height: 260)
        window.level = .floating
        window.delegate = self
        applyGlassWindowStyle(window)
        build()
        window.center()

        textView.string = L.t("Đang nhận dạng chữ...")
        textView.isEditable = false
        OcrService.recognize(image) { [weak self] result, error in
            MainActor.assumeIsolated {
                self?.show(result, error)
            }
        }
    }

    private func build() {
        let (root, content) = makeGlassWindowBackground()

        let scroll = NSScrollView()
        scroll.hasVerticalScroller = true
        scroll.borderType = .noBorder
        scroll.drawsBackground = false
        scroll.translatesAutoresizingMaskIntoConstraints = false
        textView.isRichText = false
        textView.font = NSFont.systemFont(ofSize: 15)
        textView.textContainerInset = NSSize(width: 10, height: 10)
        textView.drawsBackground = true
        textView.backgroundColor = NSColor.textBackgroundColor.withAlphaComponent(0.85)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.minSize = NSSize(width: 0, height: 0)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        scroll.documentView = textView

        let rounded = NSView()
        rounded.wantsLayer = true
        rounded.layer?.cornerRadius = 10
        rounded.layer?.masksToBounds = true
        rounded.translatesAutoresizingMaskIntoConstraints = false
        rounded.addSubview(scroll)

        infoLabel.textColor = .secondaryLabelColor
        infoLabel.font = NSFont.systemFont(ofSize: 11)
        infoLabel.lineBreakMode = .byWordWrapping
        infoLabel.maximumNumberOfLines = 2
        infoLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        copyButton = NSButton(title: L.t("Sao chép chữ"), target: self, action: #selector(copyText))
        copyButton.isEnabled = false
        styleGlassButton(copyButton, prominent: true, tint: NSColor.systemBlue)
        let close = NSButton(title: L.t("Đóng"), target: self, action: #selector(closePressed))
        close.keyEquivalent = "\u{1b}"
        styleGlassButton(close, prominent: false, tint: nil)
        for b in [copyButton, close] where !glassAvailable() {
            b.translatesAutoresizingMaskIntoConstraints = false
            b.heightAnchor.constraint(equalToConstant: 30).isActive = true
            b.widthAnchor.constraint(greaterThanOrEqualToConstant: 110).isActive = true
        }
        let spacer = NSView()
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        let bottom = NSStackView(views: [infoLabel, spacer, copyButton, close])
        bottom.orientation = .horizontal
        bottom.spacing = 10
        bottom.translatesAutoresizingMaskIntoConstraints = false

        content.addSubview(rounded)
        content.addSubview(bottom)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: rounded.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: rounded.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: rounded.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: rounded.bottomAnchor),
            rounded.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 14),
            rounded.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            rounded.topAnchor.constraint(equalTo: content.topAnchor, constant: 38),
            rounded.bottomAnchor.constraint(equalTo: bottom.topAnchor, constant: -12),
            bottom.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            bottom.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -14),
            bottom.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -12)
        ])
        window.contentView = root
    }

    func show() {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
    }

    private func show(_ result: OcrService.Result?, _ error: String?) {
        if let e = error {
            textView.string = L.t("Không nhận dạng được chữ: ") + e
            return
        }
        guard let r = result else { return }
        textView.isEditable = true
        if r.text.isEmpty {
            textView.string = L.t("(Không tìm thấy chữ nào trong ảnh)")
        } else {
            textView.string = r.text
        }
        copyButton.isEnabled = !r.text.isEmpty
        var info = L.t("Ngôn ngữ: ") + (r.languages.isEmpty ? "auto" : r.languages.joined(separator: ", "))
        if !r.text.isEmpty {
            copyText()
            info += " • " + L.t("Đã tự sao chép vào clipboard.")
            textView.setSelectedRange(NSRange(location: 0, length: 0))
        }
        infoLabel.stringValue = info
    }

    @objc private func copyText() {
        let s = textView.string
        if s.isEmpty { return }
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(s, forType: .string)
        copyButton.title = L.t("✓ Đã sao chép")
        styleGlassButton(copyButton, prominent: true, tint: NSColor.systemBlue)
    }

    @objc private func closePressed() { window.close() }

    func windowWillClose(_ notification: Notification) {
        onClose?()
    }
}
