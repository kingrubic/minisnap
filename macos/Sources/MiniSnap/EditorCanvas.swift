import AppKit
import Carbon

/// Keeps the document centred when it is smaller than the visible area.
final class CenteringClipView: NSClipView {
    override func constrainBoundsRect(_ proposedBounds: NSRect) -> NSRect {
        var rect = super.constrainBoundsRect(proposedBounds)
        if let doc = documentView {
            if rect.width > doc.frame.width { rect.origin.x = (doc.frame.width - rect.width) / 2 }
            if rect.height > doc.frame.height { rect.origin.y = (doc.frame.height - rect.height) / 2 }
        }
        return rect
    }
}

/// Window that lets the editor see key equivalents (⌘C, ⌘S, ⌘Z...) before the menu does.
final class EditorWindow: NSWindow {
    var keyHandler: ((NSEvent) -> Bool)?

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if let h = keyHandler, h(event) { return true }
        return super.performKeyEquivalent(with: event)
    }
}

/// The drawing surface. Its bounds are the image size in pixels; NSScrollView magnification does the zoom.
@MainActor
final class CanvasView: NSView {
    weak var editor: EditorController?
    private var trackingArea: NSTrackingArea?

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override var isOpaque: Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let t = trackingArea { removeTrackingArea(t) }
        let t = NSTrackingArea(rect: .zero, options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect, .cursorUpdate],
                               owner: self, userInfo: nil)
        addTrackingArea(t)
        trackingArea = t
    }

    override func draw(_ dirtyRect: NSRect) {
        guard let ctx = NSGraphicsContext.current?.cgContext, let ed = editor else { return }
        ctx.setFillColor(NSColor.white.cgColor)
        ctx.fill(dirtyRect)
        let zoom = ed.devicePixelsPerImagePixel
        ctx.interpolationQuality = zoom >= 1 ? .none : .high
        if let img = ed.cache {
            ImageUtil.drawUpright(img, in: bounds, context: ctx)
        }
        ctx.interpolationQuality = .default
        ctx.setShouldAntialias(true)
        if let cur = ed.current { cur.draw(ctx) }

        let mag = max(0.01, ed.magnification)
        if let sel = ed.selected, ed.tool == .select {
            let b = sel.bounds.insetBy(dx: -3 / mag, dy: -3 / mag)
            ctx.saveGState()
            ctx.setStrokeColor(CGColor(srgbRed: 30 / 255, green: 140 / 255, blue: 1, alpha: 1))
            ctx.setLineWidth(1.5 / mag)
            ctx.setLineDash(phase: 0, lengths: [5 / mag, 4 / mag])
            ctx.stroke(b)
            ctx.restoreGState()
        }
        if ed.cropping {
            let r = ed.cropRect
            ctx.saveGState()
            ctx.setFillColor(CGColor(gray: 0, alpha: 140.0 / 255.0))
            ctx.beginPath()
            ctx.addRect(bounds)
            ctx.addRect(r)
            ctx.fillPath(using: .evenOdd)
            ctx.setStrokeColor(CGColor(gray: 1, alpha: 1))
            ctx.setLineWidth(1.5 / mag)
            ctx.setLineDash(phase: 0, lengths: [5 / mag, 4 / mag])
            ctx.stroke(r)
            ctx.restoreGState()
        }
    }

    private func point(_ e: NSEvent) -> CGPoint { convert(e.locationInWindow, from: nil) }

    override func mouseDown(with event: NSEvent) {
        window?.makeFirstResponder(self)
        editor?.canvasMouseDown(point(event), clickCount: event.clickCount, shift: event.modifierFlags.contains(.shift))
    }

    override func mouseDragged(with event: NSEvent) {
        editor?.canvasMouseDragged(point(event), shift: event.modifierFlags.contains(.shift))
    }

    override func mouseUp(with event: NSEvent) {
        editor?.canvasMouseUp(point(event))
    }

    override func mouseMoved(with event: NSEvent) {
        editor?.canvasMouseMoved(point(event))
    }

    override func mouseExited(with event: NSEvent) {
        editor?.canvasMouseExited()
    }

    override func cursorUpdate(with event: NSEvent) {
        editor?.updateCursor(at: point(event))
    }

    override func scrollWheel(with event: NSEvent) {
        if event.modifierFlags.contains(.command), let ed = editor {
            let dy = event.scrollingDeltaY != 0 ? event.scrollingDeltaY : event.deltaY
            if dy != 0 {
                ed.zoom(by: dy > 0 ? 1.1 : 1 / 1.1, around: point(event))
            }
            return
        }
        super.scrollWheel(with: event)
    }

    override func keyDown(with event: NSEvent) {
        if editor?.canvasKeyDown(event) == true { return }
        super.keyDown(with: event)
    }
}

/// A round colour swatch button.
@MainActor
final class SwatchButton: NSButton {
    var swatchColor = RGBAColor(0, 0, 0)
    var isChosen = false { didSet { image = SwatchButton.makeImage(swatchColor, chosen: isChosen) } }

    static func makeImage(_ c: RGBAColor, chosen: Bool) -> NSImage {
        let size: CGFloat = 22
        return NSImage(size: NSSize(width: size, height: size), flipped: false) { rect in
            let inner = rect.insetBy(dx: 3, dy: 3)
            c.ns().setFill()
            let p = NSBezierPath(ovalIn: inner)
            p.fill()
            NSColor(white: 0.5, alpha: 0.6).setStroke()
            p.lineWidth = 1
            p.stroke()
            if chosen {
                let ring = NSBezierPath(ovalIn: rect.insetBy(dx: 0.75, dy: 0.75))
                ring.lineWidth = 1.5
                NSColor.controlAccentColor.setStroke()
                ring.stroke()
            }
            return true
        }
    }
}

/// Multi-line text entry placed over the canvas while typing a text annotation.
@MainActor
final class AnnotationTextView: NSTextView {
    var onCommit: (() -> Void)?
    var onCancel: (() -> Void)?

    override func doCommand(by selector: Selector) {
        if selector == #selector(NSResponder.insertNewline(_:)) {
            if NSApp.currentEvent?.modifierFlags.contains(.shift) == true {
                insertNewlineIgnoringFieldEditor(nil)
            } else {
                onCommit?()
            }
            return
        }
        if selector == #selector(NSResponder.cancelOperation(_:)) {
            onCancel?()
            return
        }
        super.doCommand(by: selector)
    }
}
