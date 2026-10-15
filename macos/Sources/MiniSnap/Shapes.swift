import AppKit

enum Tool: Int, CaseIterable {
    case select, arrow, rectangle, ellipse, line, pen, highlight, text, blur, step, crop
}

/// An sRGB colour stored as plain components so shapes are cheap to clone and compare.
struct RGBAColor: Equatable {
    var r: CGFloat
    var g: CGFloat
    var b: CGFloat

    init(_ r: Int, _ g: Int, _ b: Int) {
        self.r = CGFloat(r) / 255
        self.g = CGFloat(g) / 255
        self.b = CGFloat(b) / 255
    }

    init(ns: NSColor) {
        let c = ns.usingColorSpace(.sRGB) ?? NSColor.black
        r = c.redComponent
        g = c.greenComponent
        b = c.blueComponent
    }

    func cg(_ alpha: CGFloat = 1) -> CGColor {
        CGColor(srgbRed: r, green: g, blue: b, alpha: alpha)
    }

    func ns(_ alpha: CGFloat = 1) -> NSColor {
        NSColor(srgbRed: r, green: g, blue: b, alpha: alpha)
    }

    var isLight: Bool { r * 0.299 + g * 0.587 + b * 0.114 > 165.0 / 255.0 }

    /// Black or white, whichever reads better on top of this colour.
    func contrast(_ alpha: CGFloat) -> CGColor {
        isLight ? CGColor(srgbRed: 25 / 255, green: 25 / 255, blue: 25 / 255, alpha: alpha) : CGColor(srgbRed: 1, green: 1, blue: 1, alpha: alpha)
    }

    var hex: String {
        String(format: "#%02X%02X%02X", Int((r * 255).rounded()), Int((g * 255).rounded()), Int((b * 255).rounded()))
    }
}

enum Geo {
    static func norm(_ a: CGPoint, _ b: CGPoint) -> CGRect {
        CGRect(x: min(a.x, b.x), y: min(a.y, b.y), width: abs(a.x - b.x), height: abs(a.y - b.y))
    }

    static func dist(_ a: CGPoint, _ b: CGPoint) -> CGFloat {
        let dx = a.x - b.x, dy = a.y - b.y
        return (dx * dx + dy * dy).squareRoot()
    }

    static func distToSegment(_ p: CGPoint, _ a: CGPoint, _ b: CGPoint) -> CGFloat {
        let dx = b.x - a.x, dy = b.y - a.y
        let len2 = dx * dx + dy * dy
        if len2 < 0.0001 { return dist(p, a) }
        let t = max(0, min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2))
        return dist(p, CGPoint(x: a.x + t * dx, y: a.y + t * dy))
    }
}

/// Annotations stay as vector objects on top of the base image until saved, so they can be
/// selected, moved, recoloured and undone. All coordinates are image pixels, top-left origin.
/// Main-actor bound because text drawing goes through NSGraphicsContext / AppKit string drawing.
@MainActor
class Shape {
    var color: RGBAColor
    var width: CGFloat

    init(color: RGBAColor, width: CGFloat) {
        self.color = color
        self.width = width
    }

    /// `ctx` must have a y-down coordinate system.
    func draw(_ ctx: CGContext) {}
    var bounds: CGRect { .zero }
    func offset(dx: CGFloat, dy: CGFloat) {}

    func hitTest(_ p: CGPoint, tolerance: CGFloat) -> Bool {
        bounds.insetBy(dx: -tolerance, dy: -tolerance).contains(p)
    }

    func clone() -> Shape { Shape(color: color, width: width) }
}

class TwoPointShape: Shape {
    var a: CGPoint = .zero
    var b: CGPoint = .zero

    var rect: CGRect { Geo.norm(a, b) }
    override var bounds: CGRect { rect.insetBy(dx: -width / 2, dy: -width / 2) }

    override func offset(dx: CGFloat, dy: CGFloat) {
        a = CGPoint(x: a.x + dx, y: a.y + dy)
        b = CGPoint(x: b.x + dx, y: b.y + dy)
    }

    func copyPoints(to other: TwoPointShape) -> Shape {
        other.a = a
        other.b = b
        return other
    }
}

final class ArrowShape: TwoPointShape {
    override func draw(_ ctx: CGContext) {
        let dx = b.x - a.x, dy = b.y - a.y
        let len = (dx * dx + dy * dy).squareRoot()
        if len < 1 { return }
        let ux = dx / len, uy = dy / len, px = -uy, py = ux
        let head = min(len, max(12, width * 3.6))
        let headHalf = head * 0.6, neck = width * 0.8, tail = width * 0.35
        let base = CGPoint(x: b.x - ux * head, y: b.y - uy * head)
        ctx.saveGState()
        ctx.beginPath()
        ctx.move(to: CGPoint(x: a.x + px * tail, y: a.y + py * tail))
        ctx.addLine(to: CGPoint(x: base.x + px * neck, y: base.y + py * neck))
        ctx.addLine(to: CGPoint(x: base.x + px * headHalf, y: base.y + py * headHalf))
        ctx.addLine(to: b)
        ctx.addLine(to: CGPoint(x: base.x - px * headHalf, y: base.y - py * headHalf))
        ctx.addLine(to: CGPoint(x: base.x - px * neck, y: base.y - py * neck))
        ctx.addLine(to: CGPoint(x: a.x - px * tail, y: a.y - py * tail))
        ctx.closePath()
        ctx.setFillColor(color.cg())
        ctx.fillPath()
        ctx.restoreGState()
    }

    override var bounds: CGRect {
        let m = max(12, width * 3.6) * 0.6
        return rect.insetBy(dx: -m, dy: -m)
    }

    override func hitTest(_ p: CGPoint, tolerance: CGFloat) -> Bool {
        Geo.distToSegment(p, a, b) <= tolerance + width * 1.5
    }

    override func clone() -> Shape { copyPoints(to: ArrowShape(color: color, width: width)) }
}

final class LineShape: TwoPointShape {
    override func draw(_ ctx: CGContext) {
        ctx.saveGState()
        ctx.setStrokeColor(color.cg())
        ctx.setLineWidth(width)
        ctx.setLineCap(.round)
        ctx.beginPath()
        ctx.move(to: a)
        ctx.addLine(to: b)
        ctx.strokePath()
        ctx.restoreGState()
    }

    override func hitTest(_ p: CGPoint, tolerance: CGFloat) -> Bool {
        Geo.distToSegment(p, a, b) <= tolerance + width / 2
    }

    override func clone() -> Shape { copyPoints(to: LineShape(color: color, width: width)) }
}

final class RectShape: TwoPointShape {
    override func draw(_ ctx: CGContext) {
        let r = rect
        if r.width < 1 || r.height < 1 { return }
        ctx.saveGState()
        ctx.setStrokeColor(color.cg())
        ctx.setLineWidth(width)
        ctx.setLineJoin(.round)
        ctx.stroke(r)
        ctx.restoreGState()
    }

    override func clone() -> Shape { copyPoints(to: RectShape(color: color, width: width)) }
}

final class EllipseShape: TwoPointShape {
    override func draw(_ ctx: CGContext) {
        let r = rect
        if r.width < 1 || r.height < 1 { return }
        ctx.saveGState()
        ctx.setStrokeColor(color.cg())
        ctx.setLineWidth(width)
        ctx.strokeEllipse(in: r)
        ctx.restoreGState()
    }

    override func clone() -> Shape { copyPoints(to: EllipseShape(color: color, width: width)) }
}

final class HighlightShape: TwoPointShape {
    override func draw(_ ctx: CGContext) {
        ctx.saveGState()
        ctx.setFillColor(color.cg(105.0 / 255.0))
        ctx.fill(rect)
        ctx.restoreGState()
    }

    override var bounds: CGRect { rect }
    override func clone() -> Shape { copyPoints(to: HighlightShape(color: color, width: width)) }
}

final class BlurShape: TwoPointShape {
    /// Preview while dragging; the real pixelation happens in `apply` on the flattened image.
    override func draw(_ ctx: CGContext) {
        let r = rect
        ctx.saveGState()
        ctx.setFillColor(CGColor(gray: 0.35, alpha: 0.35))
        ctx.fill(r)
        ctx.setStrokeColor(CGColor(gray: 0.15, alpha: 0.8))
        ctx.setLineWidth(1)
        ctx.setLineDash(phase: 0, lengths: [4, 3])
        ctx.stroke(r)
        ctx.restoreGState()
    }

    override var bounds: CGRect { rect }
    override func clone() -> Shape { copyPoints(to: BlurShape(color: color, width: width)) }

    /// Pixelates the area directly in the RGBA bitmap memory of `ctx` (memory row 0 = image top).
    func apply(to ctx: CGContext, width w: Int, height h: Int) {
        var r = rect.integral.intersection(CGRect(x: 0, y: 0, width: w, height: h))
        if r.isNull { return }
        r = r.integral
        let x0 = Int(r.minX), y0 = Int(r.minY), rw = Int(r.width), rh = Int(r.height)
        if rw < 2 || rh < 2 { return }
        guard let raw = ctx.data else { return }
        let bpr = ctx.bytesPerRow
        let px = raw.bindMemory(to: UInt8.self, capacity: bpr * h)
        let block = max(6, Int(width * 3))
        var by = y0
        while by < y0 + rh {
            let bh = min(block, y0 + rh - by)
            var bx = x0
            while bx < x0 + rw {
                let bw = min(block, x0 + rw - bx)
                var sr = 0, sg = 0, sb = 0, sa = 0
                for y in by..<(by + bh) {
                    var o = y * bpr + bx * 4
                    for _ in 0..<bw {
                        sr += Int(px[o]); sg += Int(px[o + 1]); sb += Int(px[o + 2]); sa += Int(px[o + 3])
                        o += 4
                    }
                }
                let n = bw * bh
                let cr = UInt8(sr / n), cg = UInt8(sg / n), cb = UInt8(sb / n), ca = UInt8(sa / n)
                for y in by..<(by + bh) {
                    var o = y * bpr + bx * 4
                    for _ in 0..<bw {
                        px[o] = cr; px[o + 1] = cg; px[o + 2] = cb; px[o + 3] = ca
                        o += 4
                    }
                }
                bx += block
            }
            by += block
        }
    }
}

final class PenShape: Shape {
    var points: [CGPoint] = []

    override func draw(_ ctx: CGContext) {
        guard let first = points.first else { return }
        ctx.saveGState()
        if points.count == 1 {
            ctx.setFillColor(color.cg())
            ctx.fillEllipse(in: CGRect(x: first.x - width / 2, y: first.y - width / 2, width: width, height: width))
        } else {
            ctx.setStrokeColor(color.cg())
            ctx.setLineWidth(width)
            ctx.setLineCap(.round)
            ctx.setLineJoin(.round)
            ctx.beginPath()
            ctx.addLines(between: points)
            ctx.strokePath()
        }
        ctx.restoreGState()
    }

    override var bounds: CGRect {
        guard let f = points.first else { return .zero }
        var x1 = f.x, y1 = f.y, x2 = f.x, y2 = f.y
        for p in points {
            x1 = min(x1, p.x); y1 = min(y1, p.y)
            x2 = max(x2, p.x); y2 = max(y2, p.y)
        }
        return CGRect(x: x1, y: y1, width: x2 - x1, height: y2 - y1).insetBy(dx: -width / 2, dy: -width / 2)
    }

    override func offset(dx: CGFloat, dy: CGFloat) {
        points = points.map { CGPoint(x: $0.x + dx, y: $0.y + dy) }
    }

    override func hitTest(_ p: CGPoint, tolerance: CGFloat) -> Bool {
        if points.count == 1 { return Geo.dist(p, points[0]) <= tolerance + width / 2 }
        if points.count < 2 { return false }
        for i in 1..<points.count where Geo.distToSegment(p, points[i - 1], points[i]) <= tolerance + width / 2 {
            return true
        }
        return false
    }

    override func clone() -> Shape {
        let c = PenShape(color: color, width: width)
        c.points = points
        return c
    }
}

final class TextShape: Shape {
    var pos: CGPoint = .zero
    var text: String = ""

    static func fontSize(for width: CGFloat) -> CGFloat { 12 + width * 3 }
    var fontSize: CGFloat { TextShape.fontSize(for: width) }

    static func font(size: CGFloat) -> NSFont { NSFont.boldSystemFont(ofSize: max(4, size)) }

    private func attributed(fill: Bool) -> NSAttributedString {
        var attrs: [NSAttributedString.Key: Any] = [.font: TextShape.font(size: fontSize)]
        if fill {
            attrs[.foregroundColor] = color.ns()
        } else {
            // Positive stroke width = outline only; percentage of the font size (≈ size/7 pen like Windows).
            attrs[.strokeColor] = NSColor(cgColor: color.contrast(220.0 / 255.0)) ?? NSColor.white
            attrs[.strokeWidth] = 14.0
        }
        return NSAttributedString(string: text, attributes: attrs)
    }

    var textSize: CGSize {
        let s = attributed(fill: true).boundingRect(with: CGSize(width: 100_000, height: 100_000),
                                                    options: [.usesLineFragmentOrigin, .usesFontLeading],
                                                    context: nil).size
        return CGSize(width: ceil(s.width), height: ceil(s.height))
    }

    override func draw(_ ctx: CGContext) {
        if text.isEmpty { return }
        ctx.saveGState()
        ctx.setLineJoin(.round)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
        attributed(fill: false).draw(at: pos)
        attributed(fill: true).draw(at: pos)
        NSGraphicsContext.restoreGraphicsState()
        ctx.restoreGState()
    }

    override var bounds: CGRect {
        if text.isEmpty { return CGRect(x: pos.x, y: pos.y, width: 1, height: 1) }
        let s = textSize
        let m = fontSize / 6
        return CGRect(x: pos.x, y: pos.y, width: s.width, height: s.height).insetBy(dx: -m, dy: -m)
    }

    override func offset(dx: CGFloat, dy: CGFloat) { pos = CGPoint(x: pos.x + dx, y: pos.y + dy) }

    override func clone() -> Shape {
        let c = TextShape(color: color, width: width)
        c.pos = pos
        c.text = text
        return c
    }
}

final class StepShape: Shape {
    var center: CGPoint = .zero
    var number: Int = 1

    var radius: CGFloat { 10 + width * 2 }

    override func draw(_ ctx: CGContext) {
        let r = radius
        let rect = CGRect(x: center.x - r, y: center.y - r, width: 2 * r, height: 2 * r)
        ctx.saveGState()
        ctx.setFillColor(color.cg())
        ctx.fillEllipse(in: rect)
        ctx.setStrokeColor(CGColor(gray: 1, alpha: 1))
        ctx.setLineWidth(max(2, r / 8))
        ctx.strokeEllipse(in: rect)

        let para = NSMutableParagraphStyle()
        para.alignment = .center
        let attrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.boldSystemFont(ofSize: r * 1.05),
            .foregroundColor: NSColor(cgColor: color.contrast(1)) ?? NSColor.white,
            .paragraphStyle: para
        ]
        let s = NSAttributedString(string: String(number), attributes: attrs)
        let h = s.size().height
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: true)
        s.draw(in: CGRect(x: rect.minX, y: center.y - h / 2, width: rect.width, height: h))
        NSGraphicsContext.restoreGraphicsState()
        ctx.restoreGState()
    }

    override var bounds: CGRect {
        let r = radius + 2
        return CGRect(x: center.x - r, y: center.y - r, width: 2 * r, height: 2 * r)
    }

    override func offset(dx: CGFloat, dy: CGFloat) { center = CGPoint(x: center.x + dx, y: center.y + dy) }

    override func clone() -> Shape {
        let c = StepShape(color: color, width: width)
        c.center = center
        c.number = number
        return c
    }
}

@MainActor
enum Renderer {
    /// Flattens the base image plus annotations into a new image of the same pixel size.
    static func render(base: CGImage, shapes: [Shape]) -> CGImage? {
        let w = base.width, h = base.height
        guard let ctx = ImageUtil.makeContext(width: w, height: h) else { return nil }
        ctx.interpolationQuality = .none
        ctx.draw(base, in: CGRect(x: 0, y: 0, width: w, height: h))
        // From here on, y points down like the editor's coordinates.
        ctx.translateBy(x: 0, y: CGFloat(h))
        ctx.scaleBy(x: 1, y: -1)
        ctx.setShouldAntialias(true)
        for s in shapes {
            if let blur = s as? BlurShape {
                ctx.flush()
                blur.apply(to: ctx, width: w, height: h)
            } else {
                s.draw(ctx)
            }
        }
        return ctx.makeImage()
    }
}
