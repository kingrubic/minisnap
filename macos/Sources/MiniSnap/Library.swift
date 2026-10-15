import AppKit
import QuickLookThumbnailing

/// One file in the library grid.
struct LibraryItem {
    let url: URL
    let date: Date
    let size: Int
    var isVideo: Bool { LibraryPaths.isVideo(url) }
    var key: String { url.path + "|" + String(date.timeIntervalSince1970) }
}

/// A thumbnail cell, drawn by hand (image, play badge, name).
@MainActor
final class ThumbTile: NSView {
    static let size = NSSize(width: 200, height: 168)
    static let thumbHeight: CGFloat = 130

    let item: LibraryItem
    var image: NSImage? { didSet { needsDisplay = true } }
    var isSelected = false { didSet { if oldValue != isSelected { needsDisplay = true } } }

    init(item: LibraryItem) {
        self.item = item
        super.init(frame: NSRect(origin: .zero, size: ThumbTile.size))
    }

    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }

    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil } // the grid handles all mouse events

    override func draw(_ dirtyRect: NSRect) {
        let b = bounds
        if isSelected {
            NSColor.controlAccentColor.withAlphaComponent(0.28).setFill()
            NSBezierPath(roundedRect: b.insetBy(dx: 2, dy: 2), xRadius: 10, yRadius: 10).fill()
        }
        let area = NSRect(x: 10, y: 8, width: b.width - 20, height: ThumbTile.thumbHeight - 8)
        if let img = image, img.size.width > 0, img.size.height > 0 {
            let s = min(area.width / img.size.width, area.height / img.size.height, 1.0 * 4)
            let w = img.size.width * s, h = img.size.height * s
            let r = NSRect(x: area.midX - w / 2, y: area.midY - h / 2, width: w, height: h)
            NSGraphicsContext.saveGraphicsState()
            let shadow = NSShadow()
            shadow.shadowColor = NSColor.black.withAlphaComponent(0.25)
            shadow.shadowBlurRadius = 4
            shadow.shadowOffset = NSSize(width: 0, height: -1)
            shadow.set()
            img.draw(in: r, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: [.interpolation: NSNumber(value: NSImageInterpolation.high.rawValue)])
            NSGraphicsContext.restoreGraphicsState()
            if item.isVideo { drawPlayBadge(in: r) }
        } else {
            NSColor.gray.withAlphaComponent(0.15).setFill()
            NSBezierPath(roundedRect: area, xRadius: 6, yRadius: 6).fill()
            if item.isVideo { drawPlayBadge(in: area) }
        }
        let para = NSMutableParagraphStyle()
        para.alignment = .center
        para.lineBreakMode = .byTruncatingMiddle
        let name = item.url.deletingPathExtension().lastPathComponent
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11),
            .foregroundColor: isSelected ? NSColor.labelColor : NSColor.secondaryLabelColor,
            .paragraphStyle: para
        ]
        (name as NSString).draw(in: NSRect(x: 8, y: ThumbTile.thumbHeight + 6, width: b.width - 16, height: 16), withAttributes: attrs)
    }

    private func drawPlayBadge(in r: NSRect) {
        let d = min(40, min(r.width, r.height) * 0.45)
        let c = NSRect(x: r.midX - d / 2, y: r.midY - d / 2, width: d, height: d)
        NSColor.black.withAlphaComponent(0.55).setFill()
        NSBezierPath(ovalIn: c).fill()
        let tri = NSBezierPath()
        tri.move(to: NSPoint(x: c.minX + d * 0.38, y: c.minY + d * 0.28))
        tri.line(to: NSPoint(x: c.minX + d * 0.38, y: c.maxY - d * 0.28))
        tri.line(to: NSPoint(x: c.maxX - d * 0.26, y: c.midY))
        tri.close()
        NSColor.white.setFill()
        tri.fill()
    }
}

/// Flipped document view that lays out group headers and tiles, and handles selection.
@MainActor
final class LibraryGridView: NSView, NSDraggingSource {
    weak var owner: LibraryWindow?
    private(set) var tiles: [ThumbTile] = []
    private var headers: [NSTextField] = []
    private var groups: [(title: String, items: [LibraryItem])] = []
    private var anchorIndex: Int?
    private var mouseDownPoint: NSPoint?
    private var mouseDownTile: ThumbTile?

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }

    func setGroups(_ g: [(title: String, items: [LibraryItem])], selected: Set<URL>) -> [ThumbTile] {
        for t in tiles { t.removeFromSuperview() }
        for h in headers { h.removeFromSuperview() }
        tiles.removeAll()
        headers.removeAll()
        groups = g
        for grp in g {
            let h = NSTextField(labelWithString: grp.title)
            h.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
            h.textColor = .labelColor
            addSubview(h)
            headers.append(h)
            for it in grp.items {
                let t = ThumbTile(item: it)
                t.isSelected = selected.contains(it.url)
                t.toolTip = tooltip(for: it)
                addSubview(t)
                tiles.append(t)
            }
        }
        relayout()
        return tiles
    }

    private func tooltip(for it: LibraryItem) -> String {
        let f = DateFormatter()
        f.dateFormat = "dd/MM/yyyy HH:mm"
        let size: String
        if it.size >= 1 << 20 {
            size = String(format: "%.1f MB", Double(it.size) / 1_048_576.0)
        } else {
            size = String(max(1, it.size / 1024)) + " KB"
        }
        return it.url.lastPathComponent + "\n" + f.string(from: it.date) + " • " + size
    }

    func relayout() {
        let width = max(ThumbTile.size.width + 24, superview?.bounds.width ?? bounds.width)
        let pad: CGFloat = 12, gap: CGFloat = 6
        let cols = max(1, Int((width - 2 * pad + gap) / (ThumbTile.size.width + gap)))
        var y: CGFloat = 8
        var tileIndex = 0
        for (gi, grp) in groups.enumerated() {
            let h = headers[gi]
            h.sizeToFit()
            h.frame = NSRect(x: pad + 4, y: y + 6, width: width - 2 * pad, height: h.frame.height)
            y += 34
            for (i, _) in grp.items.enumerated() {
                let col = i % cols, row = i / cols
                let t = tiles[tileIndex]
                t.frame = NSRect(x: pad + CGFloat(col) * (ThumbTile.size.width + gap),
                                 y: y + CGFloat(row) * (ThumbTile.size.height + gap),
                                 width: ThumbTile.size.width, height: ThumbTile.size.height)
                tileIndex += 1
            }
            let rows = (grp.items.count + cols - 1) / cols
            y += CGFloat(rows) * (ThumbTile.size.height + gap) + 8
        }
        let minH = superview?.bounds.height ?? 0
        setFrameSize(NSSize(width: width, height: max(y + 8, minH)))
    }

    var selectedURLs: [URL] { tiles.filter { $0.isSelected }.map { $0.item.url } }

    private func tile(at p: NSPoint) -> ThumbTile? {
        tiles.first { $0.frame.contains(p) }
    }

    func selectOnly(_ t: ThumbTile?) {
        for x in tiles { x.isSelected = (x === t) }
        if let t = t { anchorIndex = tiles.firstIndex { $0 === t } }
        owner?.selectionChanged()
    }

    func selectAll() {
        for t in tiles { t.isSelected = true }
        owner?.selectionChanged()
    }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        let p = convert(event.locationInWindow, from: nil)
        let t = tile(at: p)
        mouseDownPoint = p
        mouseDownTile = t
        let flags = event.modifierFlags
        if let t = t {
            if flags.contains(.command) {
                t.isSelected.toggle()
                anchorIndex = tiles.firstIndex { $0 === t }
                owner?.selectionChanged()
            } else if flags.contains(.shift), let a = anchorIndex, let i = tiles.firstIndex(where: { $0 === t }) {
                for (k, x) in tiles.enumerated() { x.isSelected = k >= min(a, i) && k <= max(a, i) }
                owner?.selectionChanged()
            } else if !t.isSelected {
                selectOnly(t)
            }
            if event.clickCount == 2 { owner?.openSelected() }
        } else if !flags.contains(.command) {
            selectOnly(nil)
        }
    }

    override func mouseUp(with event: NSEvent) {
        let p = convert(event.locationInWindow, from: nil)
        if let t = tile(at: p), t === mouseDownTile, event.clickCount == 1,
           !event.modifierFlags.contains(.command), !event.modifierFlags.contains(.shift) {
            selectOnly(t)
        }
        mouseDownTile = nil
        mouseDownPoint = nil
    }

    override func mouseDragged(with event: NSEvent) {
        guard let start = mouseDownPoint, mouseDownTile != nil else { return }
        let p = convert(event.locationInWindow, from: nil)
        if abs(p.x - start.x) + abs(p.y - start.y) < 5 { return }
        mouseDownPoint = nil
        var items: [NSDraggingItem] = []
        for t in tiles where t.isSelected {
            let di = NSDraggingItem(pasteboardWriter: t.item.url as NSURL)
            let img = t.image ?? NSImage(size: NSSize(width: 64, height: 64))
            di.setDraggingFrame(t.frame, contents: img)
            items.append(di)
        }
        if !items.isEmpty {
            _ = beginDraggingSession(with: items, event: event, source: self)
        }
    }

    func draggingSession(_ session: NSDraggingSession, sourceOperationMaskFor context: NSDraggingContext) -> NSDragOperation {
        .copy
    }

    override func menu(for event: NSEvent) -> NSMenu? {
        let p = convert(event.locationInWindow, from: nil)
        guard let t = tile(at: p) else { return nil }
        if !t.isSelected { selectOnly(t) }
        return owner?.contextMenu()
    }

    // Edit menu ⌘C routes here through the responder chain (⌘A falls through to keyDown).
    @objc func copy(_ sender: Any?) { owner?.copySelected() }

    override func keyDown(with event: NSEvent) {
        let code = event.keyCode
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if code == 51 || code == 117 { owner?.trashSelected(); return }          // Delete / Forward delete
        if code == 36 || code == 76 { owner?.openSelected(); return }            // Return / Enter
        if flags.contains(.command) {
            let ch = (event.charactersIgnoringModifiers ?? "").lowercased()
            if ch == "a" { selectAll(); return }
            if ch == "c" { owner?.copySelected(); return }
        }
        super.keyDown(with: event)
    }
}

/// "Library" window: thumbnails of captures and recordings grouped by date.
@MainActor
final class LibraryWindow: NSObject, NSWindowDelegate, NSSearchFieldDelegate {
    private enum Filter: Int { case all = 0, images, videos }

    let window: NSWindow
    var onOpenImage: ((URL) -> Void)?
    var onOcr: ((URL) -> Void)?
    var onClose: (() -> Void)?

    private let scroll = NSScrollView()
    private let grid = LibraryGridView(frame: NSRect(x: 0, y: 0, width: 900, height: 600))
    private let filterControl = NSSegmentedControl(labels: [L.t("Tất cả"), L.t("Ảnh"), L.t("Video")], trackingMode: .selectOne, target: nil, action: nil)
    private let search = NSSearchField()
    private let countLabel = NSTextField(labelWithString: "")
    private let emptyLabel = NSTextField(labelWithString: "")
    private var filter = Filter.all
    private var thumbCache: [String: NSImage] = [:]
    private var watchers: [DispatchSourceFileSystemObject] = []
    private var refreshTask: Task<Void, Never>?
    private var generation = 0
    private var pendingReveal: URL?

    override init() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1000, height: 680),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        super.init()
        window.isReleasedWhenClosed = false
        window.title = L.t("Thư viện — MiniSnap")
        window.minSize = NSSize(width: 520, height: 360)
        window.delegate = self
        window.tabbingMode = .disallowed
        applyGlassWindowStyle(window)
        build()
        window.center()
        startWatching()
        populate()
    }

    private func toolbarButton(_ title: String, symbolName: String, action: Selector) -> NSButton {
        let b = NSButton(title: title, target: self, action: action)
        b.image = symbol(symbolName, size: 13)
        b.imagePosition = .imageLeading
        styleGlassButton(b, prominent: false, tint: nil)
        if !glassAvailable() {
            b.translatesAutoresizingMaskIntoConstraints = false
            b.heightAnchor.constraint(equalToConstant: 26).isActive = true
            b.widthAnchor.constraint(greaterThanOrEqualToConstant: 70).isActive = true
        }
        return b
    }

    private func build() {
        let root = NSView()
        window.contentView = root

        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true
        scroll.drawsBackground = true
        scroll.backgroundColor = NSColor.textBackgroundColor
        grid.owner = self
        scroll.documentView = grid
        scroll.contentView.postsFrameChangedNotifications = true
        NotificationCenter.default.addObserver(self, selector: #selector(clipResized), name: NSView.frameDidChangeNotification, object: scroll.contentView)
        root.addSubview(scroll)

        emptyLabel.alignment = .center
        emptyLabel.textColor = .secondaryLabelColor
        emptyLabel.font = NSFont.systemFont(ofSize: 15)
        emptyLabel.maximumNumberOfLines = 3
        emptyLabel.isHidden = true
        emptyLabel.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(emptyLabel)

        // Toolbar (glass)
        let (barBg, barContent) = makeGlassContainer(cornerRadius: 0, tint: nil, material: .menu)
        root.addSubview(barBg)
        filterControl.selectedSegment = 0
        filterControl.target = self
        filterControl.action = #selector(filterChanged)
        search.placeholderString = L.t("Tìm")
        search.delegate = self
        search.translatesAutoresizingMaskIntoConstraints = false
        search.widthAnchor.constraint(equalToConstant: 200).isActive = true
        let refresh = toolbarButton(L.t("Làm mới"), symbolName: "arrow.clockwise", action: #selector(refreshPressed))
        let imgFolder = toolbarButton(L.t("Thư mục ảnh"), symbolName: "folder", action: #selector(imagesFolderPressed))
        let vidFolder = toolbarButton(L.t("Thư mục video"), symbolName: "film", action: #selector(videosFolderPressed))
        let buttons = NSStackView(views: [refresh, imgFolder, vidFolder])
        buttons.spacing = 6
        let spacer = NSView()
        spacer.setContentHuggingPriority(NSLayoutConstraint.Priority(1), for: .horizontal)
        let bar = NSStackView(views: [filterControl, search, spacer, wrapInGlassGroup(buttons)])
        bar.orientation = .horizontal
        bar.spacing = 10
        bar.edgeInsets = NSEdgeInsets(top: 6, left: 12, bottom: 6, right: 12)
        bar.translatesAutoresizingMaskIntoConstraints = false
        barContent.addSubview(bar)

        let (statusBg, statusContent) = makeGlassContainer(cornerRadius: 0, tint: nil, material: .menu)
        root.addSubview(statusBg)
        countLabel.font = NSFont.systemFont(ofSize: 11)
        countLabel.textColor = .secondaryLabelColor
        countLabel.lineBreakMode = .byTruncatingMiddle
        countLabel.translatesAutoresizingMaskIntoConstraints = false
        statusContent.addSubview(countLabel)

        let topAnchor: NSLayoutYAxisAnchor
        if let guide = window.contentLayoutGuide as? NSLayoutGuide {
            topAnchor = guide.topAnchor
        } else {
            topAnchor = root.topAnchor
        }
        NSLayoutConstraint.activate([
            barBg.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            barBg.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            barBg.topAnchor.constraint(equalTo: topAnchor),
            bar.leadingAnchor.constraint(equalTo: barContent.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: barContent.trailingAnchor),
            bar.topAnchor.constraint(equalTo: barContent.topAnchor),
            bar.bottomAnchor.constraint(equalTo: barContent.bottomAnchor),

            scroll.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            scroll.topAnchor.constraint(equalTo: barBg.bottomAnchor),
            scroll.bottomAnchor.constraint(equalTo: statusBg.topAnchor),

            emptyLabel.centerXAnchor.constraint(equalTo: scroll.centerXAnchor),
            emptyLabel.centerYAnchor.constraint(equalTo: scroll.centerYAnchor),
            emptyLabel.widthAnchor.constraint(lessThanOrEqualTo: scroll.widthAnchor, constant: -40),

            statusBg.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            statusBg.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            statusBg.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            countLabel.leadingAnchor.constraint(equalTo: statusContent.leadingAnchor, constant: 12),
            countLabel.trailingAnchor.constraint(equalTo: statusContent.trailingAnchor, constant: -12),
            countLabel.topAnchor.constraint(equalTo: statusContent.topAnchor, constant: 4),
            countLabel.bottomAnchor.constraint(equalTo: statusContent.bottomAnchor, constant: -4)
        ])
    }

    func show() {
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        grid.relayout()
    }

    func reveal(_ url: URL) {
        pendingReveal = url
        populate()
    }

    // MARK: - Data

    private static func groupName(_ d: Date) -> String {
        let cal = Calendar.current
        let today = cal.startOfDay(for: Date())
        if d >= today { return L.t("Hôm nay") }
        if let y = cal.date(byAdding: .day, value: -1, to: today), d >= y { return L.t("Hôm qua") }
        if let w = cal.date(byAdding: .day, value: -7, to: today), d >= w { return L.t("7 ngày qua") }
        let comps = cal.dateComponents([.year, .month], from: today)
        if let m = cal.date(from: comps), d >= m { return L.t("Tháng này") }
        return L.t("Cũ hơn")
    }

    private static func emptyText() -> String {
        let keys = HotkeySettings.load()
        let cap = keys[.captureRegion] ?? Hotkey.empty
        let rec = keys[.recordVideo] ?? Hotkey.empty
        var hint = cap.isNone ? L.t("Dùng menu trên thanh menu để chụp") : L.t("Nhấn ") + cap.displayText + L.t(" để chụp")
        hint += rec.isNone ? "." : ", " + rec.displayText + L.t(" để quay video.")
        return L.t("Chưa có ảnh hay video nào.\n") + hint
    }

    private func populate() {
        let all = LibraryPaths.allFiles()
        let q = search.stringValue.trimmingCharacters(in: .whitespaces).lowercased()
        var items: [LibraryItem] = []
        for f in all {
            let isVid = LibraryPaths.isVideo(f.url)
            switch filter {
            case .images: if isVid { continue }
            case .videos: if !isVid { continue }
            case .all: break
            }
            if !q.isEmpty && !f.url.lastPathComponent.lowercased().contains(q) { continue }
            items.append(LibraryItem(url: f.url, date: f.date, size: f.size))
        }
        var groups: [(title: String, items: [LibraryItem])] = []
        for it in items {
            let g = LibraryWindow.groupName(it.date)
            if let last = groups.last, last.title == g {
                groups[groups.count - 1].items.append(it)
            } else {
                groups.append((g, [it]))
            }
        }
        var selected = Set(grid.selectedURLs)
        if let r = pendingReveal {
            selected = [r.standardizedFileURL]
        }
        let normalizedSelected = Set(selected.map { $0.standardizedFileURL })
        let tiles = grid.setGroups(groups, selected: normalizedSelected)
        generation += 1
        let gen = generation
        let scale = window.backingScaleFactor
        for t in tiles {
            if let cached = thumbCache[t.item.key] {
                t.image = cached
            } else {
                loadThumb(t, generation: gen, scale: scale)
            }
        }
        if let r = pendingReveal, let t = tiles.first(where: { $0.item.url.standardizedFileURL == r.standardizedFileURL }) {
            grid.selectOnly(t)
            grid.scrollToVisible(t.frame)
            pendingReveal = nil
        }
        emptyLabel.stringValue = LibraryWindow.emptyText()
        emptyLabel.isHidden = !items.isEmpty
        let nImg = items.filter { !$0.isVideo }.count
        let nVid = items.count - nImg
        countLabel.stringValue = String(nImg) + L.t(" ảnh • ") + String(nVid) + L.t(" video   —   ") + LibraryPaths.imagesFolder.path + "  |  " + LibraryPaths.videosFolder.path
    }

    private func loadThumb(_ tile: ThumbTile, generation gen: Int, scale: CGFloat) {
        let key = tile.item.key
        let req = QLThumbnailGenerator.Request(fileAt: tile.item.url,
                                               size: CGSize(width: ThumbTile.size.width - 20, height: ThumbTile.thumbHeight - 8),
                                               scale: scale,
                                               representationTypes: .all)
        QLThumbnailGenerator.shared.generateBestRepresentation(for: req) { [weak self, weak tile] rep, _ in
            guard let img = rep?.nsImage else { return }
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    guard let self = self else { return }
                    self.thumbCache[key] = img
                    if gen == self.generation { tile?.image = img }
                }
            }
        }
    }

    private func scheduleRefresh() {
        refreshTask?.cancel()
        refreshTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 500_000_000)
            if Task.isCancelled { return }
            self?.populate()
        }
    }

    private func startWatching() {
        for folder in [LibraryPaths.imagesFolder, LibraryPaths.videosFolder] {
            let fd = open(folder.path, O_EVTONLY)
            if fd < 0 { continue }
            let src = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: [.write, .delete, .rename, .extend], queue: DispatchQueue.main)
            src.setEventHandler { [weak self] in
                MainActor.assumeIsolated { self?.scheduleRefresh() }
            }
            src.setCancelHandler { close(fd) }
            src.resume()
            watchers.append(src)
        }
    }

    // MARK: - Actions

    func selectionChanged() {}

    func contextMenu() -> NSMenu {
        let urls = grid.selectedURLs
        let m = NSMenu()
        let open = NSMenuItem(title: L.t("Mở"), action: #selector(openPressed), keyEquivalent: "")
        open.target = self
        m.addItem(open)
        if urls.count == 1, let u = urls.first, LibraryPaths.isImage(u) {
            let ocr = NSMenuItem(title: L.t("Trích chữ (OCR)"), action: #selector(ocrPressed), keyEquivalent: "")
            ocr.target = self
            ocr.image = symbol("text.viewfinder", size: 13)
            m.addItem(ocr)
        }
        let copy = NSMenuItem(title: L.t("Sao chép"), action: #selector(copyPressed), keyEquivalent: "c")
        copy.target = self
        copy.image = symbol("doc.on.doc", size: 13)
        m.addItem(copy)
        let finder = NSMenuItem(title: L.t("Hiện trong Finder"), action: #selector(finderPressed), keyEquivalent: "")
        finder.target = self
        finder.image = symbol("folder", size: 13)
        m.addItem(finder)
        m.addItem(NSMenuItem.separator())
        let trash = NSMenuItem(title: L.t("Chuyển vào Thùng rác"), action: #selector(trashPressed), keyEquivalent: "\u{8}")
        trash.target = self
        trash.image = symbol("trash", size: 13)
        m.addItem(trash)
        return m
    }

    func openSelected() {
        for u in grid.selectedURLs.prefix(5) {
            if LibraryPaths.isVideo(u) {
                NSWorkspace.shared.open(u)
            } else {
                onOpenImage?(u)
            }
        }
    }

    func copySelected() {
        let urls = grid.selectedURLs
        guard !urls.isEmpty else { return }
        var ok = false
        if urls.count == 1, let u = urls.first, LibraryPaths.isImage(u), let img = ImageUtil.load(u) {
            ok = ImageUtil.copyToPasteboard(img)
        } else {
            let pb = NSPasteboard.general
            pb.clearContents()
            ok = pb.writeObjects(urls.map { $0 as NSURL })
        }
        if ok {
            let what = urls.count == 1 ? urls[0].lastPathComponent : String(urls.count) + L.t(" mục")
            countLabel.stringValue = L.t("Đã sao chép ") + what + L.t(" vào clipboard")
        } else {
            countLabel.stringValue = L.t("Không sao chép được: ") + (urls.first?.lastPathComponent ?? "")
        }
    }

    func trashSelected() {
        let urls = grid.selectedURLs
        guard !urls.isEmpty else { return }
        let what = urls.count == 1 ? "\"" + urls[0].lastPathComponent + "\"" : String(urls.count) + L.t(" mục")
        let alert = NSAlert()
        alert.messageText = L.t("Chuyển ") + what + L.t(" vào Thùng rác?")
        alert.addButton(withTitle: L.t("Chuyển vào Thùng rác"))
        alert.addButton(withTitle: L.t("Huỷ"))
        if alert.runModal() != .alertFirstButtonReturn { return }
        for u in urls {
            do {
                try FileManager.default.trashItem(at: u, resultingItemURL: nil)
            } catch {
                Alerts.show("MiniSnap", L.t("Không xoá được ") + u.lastPathComponent + ":\n" + error.localizedDescription)
            }
        }
        populate()
    }

    @objc private func openPressed() { openSelected() }
    @objc private func copyPressed() { copySelected() }
    @objc private func trashPressed() { trashSelected() }

    @objc private func ocrPressed() {
        if let u = grid.selectedURLs.first { onOcr?(u) }
    }

    @objc private func finderPressed() {
        let urls = grid.selectedURLs
        if !urls.isEmpty { NSWorkspace.shared.activateFileViewerSelecting(urls) }
    }

    @objc private func filterChanged() {
        filter = Filter(rawValue: filterControl.selectedSegment) ?? .all
        populate()
    }

    @objc private func refreshPressed() { populate() }
    @objc private func imagesFolderPressed() { NSWorkspace.shared.open(LibraryPaths.imagesFolder) }
    @objc private func videosFolderPressed() { NSWorkspace.shared.open(LibraryPaths.videosFolder) }

    @objc private func clipResized() { grid.relayout() }

    func controlTextDidChange(_ obj: Notification) { scheduleRefresh() }

    // MARK: - Window delegate

    func windowDidBecomeKey(_ notification: Notification) { scheduleRefresh() }

    func windowDidResize(_ notification: Notification) { grid.relayout() }

    func windowWillClose(_ notification: Notification) {
        generation += 1
        refreshTask?.cancel()
        for w in watchers { w.cancel() }
        watchers.removeAll()
        NotificationCenter.default.removeObserver(self)
        onClose?()
    }
}
