using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;

namespace MiniSnap
{
    enum IconKind
    {
        Select, Arrow, Rectangle, Ellipse, Line, Pen, Highlight, Text, Blur, Step, Crop, Capture, Undo, Redo, Copy, Save, SaveAs, Folder,
        Ocr, Library, Video, Scroll, Record, Pause, Stop, Refresh, Delete, Open, Keyboard, Globe, Camera, Close, Info, Update,
    }

    static class AppIcon
    {
        static Icon icon, small;

        public static Icon Get()
        {
            if (icon == null) icon = Icon.FromHandle(Render(32).GetHicon());
            return icon;
        }

        public static Icon Small(int size)
        {
            if (small == null) small = Icon.FromHandle(Render(size).GetHicon());
            return small;
        }

        public static Bitmap Render(int size)
        {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.ScaleTransform(size / 32f, size / 32f);
                using (var path = Icons.RoundedRect(new RectangleF(1, 1, 30, 30), 7))
                using (var br = new LinearGradientBrush(new PointF(0, 0), new PointF(32, 32), Color.FromArgb(255, 110, 50), Color.FromArgb(225, 40, 85)))
                    g.FillPath(br, path);
                using (var pen = new Pen(Color.White, 3f))
                {
                    pen.StartCap = pen.EndCap = LineCap.Round;
                    pen.LineJoin = LineJoin.Round;
                    g.DrawLines(pen, new[] { new PointF(8, 15), new PointF(8, 8), new PointF(15, 8) });
                    g.DrawLines(pen, new[] { new PointF(17, 24), new PointF(24, 24), new PointF(24, 17) });
                }
                g.FillEllipse(Brushes.White, 13, 13, 6, 6);
            }
            return bmp;
        }

        // Multi-size .ico (PNG entries) used as the exe icon at build time.
        public static void SaveIco(string path)
        {
            int[] sizes = { 16, 20, 24, 32, 40, 48, 64, 128, 256 };
            var pngs = new List<byte[]>();
            foreach (int s in sizes)
                using (var b = Render(s))
                using (var ms = new MemoryStream())
                {
                    b.Save(ms, ImageFormat.Png);
                    pngs.Add(ms.ToArray());
                }
            using (var w = new BinaryWriter(File.Create(path)))
            {
                w.Write((short)0);
                w.Write((short)1);
                w.Write((short)sizes.Length);
                int offset = 6 + 16 * sizes.Length;
                for (int i = 0; i < sizes.Length; i++)
                {
                    byte dim = (byte)(sizes[i] >= 256 ? 0 : sizes[i]);
                    w.Write(dim);
                    w.Write(dim);
                    w.Write((byte)0);
                    w.Write((byte)0);
                    w.Write((short)1);
                    w.Write((short)32);
                    w.Write(pngs[i].Length);
                    w.Write(offset);
                    offset += pngs[i].Length;
                }
                foreach (var p in pngs) w.Write(p);
            }
        }
    }

    // Toolbar glyphs drawn in code on a 24x24 grid, so the app ships as a single exe.
    static class Icons
    {
        // Default glyph colour follows the light/dark theme.
        static Color Ink { get { return Theme.Dark ? Color.FromArgb(232, 232, 232) : Color.FromArgb(50, 50, 56); } }

        // Segoe Fluent Icons code points used instead of the hand-drawn glyph when the font is available.
        static readonly System.Collections.Generic.Dictionary<IconKind, char> Fluent = new System.Collections.Generic.Dictionary<IconKind, char>
        {
            { IconKind.Copy, '' }, { IconKind.Save, '' }, { IconKind.SaveAs, '' },
            { IconKind.Undo, '' }, { IconKind.Redo, '' }, { IconKind.Folder, '' }, { IconKind.Open, '' },
            { IconKind.Refresh, '' }, { IconKind.Camera, '' }, { IconKind.Video, '' }, { IconKind.Library, '' },
            { IconKind.Keyboard, '' }, { IconKind.Globe, '' }, { IconKind.Close, '' }, { IconKind.Pause, '' },
            { IconKind.Stop, '' }, { IconKind.Crop, '' }, { IconKind.Text, '' }, { IconKind.Highlight, '' },
            { IconKind.Pen, '' }, { IconKind.Delete, '' }, { IconKind.Capture, '' }, { IconKind.Info, '' }, { IconKind.Update, '' },
        };
        static readonly Color Red = Color.FromArgb(232, 38, 38);
        static readonly Color Blue = Color.FromArgb(30, 120, 230);

        public static GraphicsPath RoundedRect(RectangleF r, float radius)
        {
            var path = new GraphicsPath();
            float d = Math.Min(radius * 2, Math.Min(r.Width, r.Height));
            if (d <= 0) { path.AddRectangle(r); return path; }
            path.AddArc(r.X, r.Y, d, d, 180, 90);
            path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }

        public static Bitmap Swatch(Color c, int size, bool ring)
        {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                float inset = size * 0.12f;
                using (var path = RoundedRect(new RectangleF(inset, inset, size - 2 * inset - 1, size - 2 * inset - 1), size * 0.18f))
                using (var br = new SolidBrush(c))
                using (var pen = new Pen(Color.FromArgb(120, 0, 0, 0), 1f))
                {
                    g.FillPath(br, path);
                    g.DrawPath(pen, path);
                }
                if (ring)
                    using (var pen = new Pen(Ink, Math.Max(1.5f, size / 12f)))
                    using (var path = RoundedRect(new RectangleF(1, 1, size - 3, size - 3), size * 0.22f))
                        g.DrawPath(pen, path);
            }
            return bmp;
        }

        public static Bitmap Draw(IconKind kind, int size) { return Draw(kind, size, Ink, Theme.Dark ? Theme.Surface : Color.White); }

        // ink: line/fill colour of the glyph; paper: colour used where a glyph punches out its background.
        public static Bitmap Draw(IconKind kind, int size, Color inkColor, Color paperColor)
        {
            char code;
            if (Theme.HasIconFont && Fluent.TryGetValue(kind, out code)) return Theme.Glyph(code, size, inkColor);

            var bmp = new Bitmap(size, size, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.ScaleTransform(size / 24f, size / 24f);
                using (var pen = Geo.MakePen(inkColor, 2f))
                using (var ink = new SolidBrush(inkColor))
                using (var paper = new SolidBrush(paperColor))
                    DrawGlyph(g, kind, pen, ink, paper);
            }
            return bmp;
        }

        // Round "play" badge drawn over video thumbnails.
        public static void DrawPlayBadge(Graphics g, RectangleF area)
        {
            float d = Math.Min(area.Width, area.Height) * 0.34f;
            var r = new RectangleF(area.X + (area.Width - d) / 2, area.Y + (area.Height - d) / 2, d, d);
            var old = g.SmoothingMode;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (var br = new SolidBrush(Color.FromArgb(170, 0, 0, 0))) g.FillEllipse(br, r);
            using (var pen = new Pen(Color.FromArgb(230, 255, 255, 255), Math.Max(1.5f, d / 18f))) g.DrawEllipse(pen, r);
            float t = d * 0.22f, cx = r.X + d * 0.54f, cy = r.Y + d / 2;
            g.FillPolygon(Brushes.White, new[] { new PointF(cx - t * 0.8f, cy - t), new PointF(cx - t * 0.8f, cy + t), new PointF(cx + t, cy) });
            g.SmoothingMode = old;
        }

        static void DrawGlyph(Graphics g, IconKind kind, Pen pen, Brush ink, Brush paper)
        {
            switch (kind)
            {
                case IconKind.Select:
                    var cursor = new[] { new PointF(6, 3), new PointF(6, 19), new PointF(10, 15.5f), new PointF(13, 21.5f), new PointF(15.8f, 20.2f), new PointF(12.8f, 14.2f), new PointF(18, 14) };
                    g.FillPolygon(Brushes.White, cursor);
                    using (var p = new Pen(Ink, 1.6f) { LineJoin = LineJoin.Round }) g.DrawPolygon(p, cursor);
                    break;
                case IconKind.Arrow:
                    new ArrowShape { A = new PointF(4, 20), B = new PointF(21, 3), Color = Red, Width = 3f }.Draw(g);
                    break;
                case IconKind.Rectangle:
                    using (var p = new Pen(Red, 2.2f)) g.DrawRectangle(p, 3.5f, 5.5f, 17, 13);
                    break;
                case IconKind.Ellipse:
                    using (var p = new Pen(Blue, 2.2f)) g.DrawEllipse(p, 2.5f, 5.5f, 19, 13);
                    break;
                case IconKind.Line:
                    using (var p = Geo.MakePen(Color.FromArgb(40, 170, 70), 2.6f)) g.DrawLine(p, 4, 19, 20, 5);
                    break;
                case IconKind.Pen:
                    using (var p = Geo.MakePen(Color.FromArgb(150, 70, 200), 2.4f)) g.DrawBezier(p, 3, 17, 8, 2, 13, 24, 21, 6);
                    break;
                case IconKind.Highlight:
                    using (var br = new SolidBrush(Color.FromArgb(200, 255, 214, 0))) g.FillRectangle(br, 2, 8, 20, 8);
                    g.DrawLine(pen, 4, 12, 20, 12);
                    break;
                case IconKind.Text:
                    using (var f = new Font("Segoe UI", 19f, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                        g.DrawString("T", f, ink, new RectangleF(0, 0, 24, 25), sf);
                    break;
                case IconKind.Blur:
                    for (int y = 0; y < 4; y++)
                        for (int x = 0; x < 4; x++)
                        {
                            int v = 110 + ((x * 37 + y * 53) % 4) * 35;
                            using (var br = new SolidBrush(Color.FromArgb(v, v, Math.Min(255, v + 10)))) g.FillRectangle(br, 4 + x * 4, 4 + y * 4, 4, 4);
                        }
                    using (var p = new Pen(Ink, 1.2f)) g.DrawRectangle(p, 4, 4, 16, 16);
                    break;
                case IconKind.Step:
                    new StepShape { Center = new PointF(12, 12), Number = 1, Color = Red, Width = 0.5f }.Draw(g);
                    break;
                case IconKind.Crop:
                    g.DrawLines(pen, new[] { new PointF(7, 2), new PointF(7, 17), new PointF(22, 17) });
                    g.DrawLines(pen, new[] { new PointF(2, 7), new PointF(17, 7), new PointF(17, 22) });
                    break;
                case IconKind.Capture:
                    using (var p = new Pen(Red, 2f) { DashPattern = new float[] { 2f, 1.2f } }) g.DrawRectangle(p, 3, 5, 18, 14);
                    g.DrawLine(pen, 12, 9, 12, 15);
                    g.DrawLine(pen, 9, 12, 15, 12);
                    break;
                case IconKind.Undo:
                case IconKind.Redo:
                    if (kind == IconKind.Redo) { g.TranslateTransform(24, 0); g.ScaleTransform(-1, 1); }
                    g.DrawBezier(pen, 19, 19, 20, 9, 13, 7, 6, 9);
                    g.DrawLines(pen, new[] { new PointF(9, 4.5f), new PointF(5, 9), new PointF(10, 12.5f) });
                    break;
                case IconKind.Copy:
                    using (var path = RoundedRect(new RectangleF(8, 3, 12, 14), 2)) g.DrawPath(pen, path);
                    using (var path = RoundedRect(new RectangleF(4, 7, 12, 14), 2)) { g.FillPath(paper, path); g.DrawPath(pen, path); }
                    break;
                case IconKind.Save:
                case IconKind.SaveAs:
                    using (var path = RoundedRect(new RectangleF(3.5f, 3.5f, 17, 17), 2)) g.DrawPath(pen, path);
                    g.DrawRectangle(pen, 8, 3.5f, 8, 5);
                    g.DrawRectangle(pen, 7, 13, 10, 7.5f);
                    if (kind == IconKind.SaveAs)
                    {
                        using (var br = new SolidBrush(Blue)) g.FillEllipse(br, 13, 12, 11, 11);
                        using (var p = Geo.MakePen(Color.White, 1.8f)) { g.DrawLine(p, 18.5f, 14.5f, 18.5f, 20.5f); g.DrawLine(p, 15.5f, 17.5f, 21.5f, 17.5f); }
                    }
                    break;
                case IconKind.Folder:
                case IconKind.Open:
                    var folder = new[] { new PointF(2.5f, 6), new PointF(9, 6), new PointF(11, 8.5f), new PointF(21.5f, 8.5f), new PointF(21.5f, 19.5f), new PointF(2.5f, 19.5f) };
                    using (var br = new SolidBrush(Color.FromArgb(255, 200, 70))) g.FillPolygon(br, folder);
                    using (var p = new Pen(Color.FromArgb(190, 140, 20), 1.5f) { LineJoin = LineJoin.Round }) g.DrawPolygon(p, folder);
                    break;
                case IconKind.Ocr:
                    g.DrawLines(pen, new[] { new PointF(3, 8), new PointF(3, 3), new PointF(8, 3) });
                    g.DrawLines(pen, new[] { new PointF(16, 3), new PointF(21, 3), new PointF(21, 8) });
                    g.DrawLines(pen, new[] { new PointF(3, 16), new PointF(3, 21), new PointF(8, 21) });
                    g.DrawLines(pen, new[] { new PointF(16, 21), new PointF(21, 21), new PointF(21, 16) });
                    using (var p = Geo.MakePen(Blue, 2.2f))
                    {
                        g.DrawLine(p, 8, 8.5f, 16, 8.5f);
                        g.DrawLine(p, 12, 8.5f, 12, 16.5f);
                    }
                    break;
                case IconKind.Library:
                    using (var br = new SolidBrush(Blue))
                        foreach (var r in new[] { new RectangleF(3, 3, 8, 8), new RectangleF(13, 3, 8, 8), new RectangleF(3, 13, 8, 8), new RectangleF(13, 13, 8, 8) })
                            using (var path = RoundedRect(r, 2)) g.FillPath(br, path);
                    break;
                case IconKind.Video:
                    using (var path = RoundedRect(new RectangleF(2.5f, 6, 13, 12), 2.5f)) g.DrawPath(pen, path);
                    g.DrawPolygon(pen, new[] { new PointF(15.5f, 10.5f), new PointF(21.5f, 7), new PointF(21.5f, 17), new PointF(15.5f, 13.5f) });
                    using (var br = new SolidBrush(Red)) g.FillEllipse(br, 6, 9.5f, 5, 5);
                    break;
                case IconKind.Update:
                    g.DrawLine(pen, 12, 3, 12, 15);
                    g.DrawLines(pen, new[] { new PointF(7, 10.5f), new PointF(12, 15.5f), new PointF(17, 10.5f) });
                    g.DrawLine(pen, 5, 20.5f, 19, 20.5f);
                    break;
                case IconKind.Info:
                    g.DrawEllipse(pen, 3, 3, 18, 18);
                    g.DrawLine(pen, 12, 11, 12, 17);
                    g.FillEllipse(ink, 10.8f, 6.6f, 2.4f, 2.4f);
                    break;
                case IconKind.Camera:
                    using (var path = RoundedRect(new RectangleF(2.5f, 7, 19, 13), 3)) g.DrawPath(pen, path);
                    g.DrawLines(pen, new[] { new PointF(8, 7), new PointF(9.5f, 4.5f), new PointF(14.5f, 4.5f), new PointF(16, 7) });
                    g.DrawEllipse(pen, 8.5f, 9.5f, 7, 7);
                    break;
                case IconKind.Close:
                    using (var p = Geo.MakePen(((SolidBrush)ink).Color, 2.4f))
                    {
                        g.DrawLine(p, 6.5f, 6.5f, 17.5f, 17.5f);
                        g.DrawLine(p, 17.5f, 6.5f, 6.5f, 17.5f);
                    }
                    break;
                case IconKind.Scroll:
                    using (var path = RoundedRect(new RectangleF(5, 2.5f, 14, 19), 2)) g.DrawPath(pen, path);
                    // Blue arrow on the default (white) toolbar; ink-coloured on coloured buttons.
                    using (var p = Geo.MakePen(((SolidBrush)ink).Color == Ink ? Blue : ((SolidBrush)ink).Color, 2.2f))
                    {
                        g.DrawLine(p, 12, 6.5f, 12, 16);
                        g.DrawLines(p, new[] { new PointF(8.5f, 12.5f), new PointF(12, 16), new PointF(15.5f, 12.5f) });
                    }
                    break;
                case IconKind.Record:
                    using (var br = new SolidBrush(Red)) g.FillEllipse(br, 5, 5, 14, 14);
                    break;
                case IconKind.Pause:
                    g.FillRectangle(ink, 6, 5, 4, 14);
                    g.FillRectangle(ink, 14, 5, 4, 14);
                    break;
                case IconKind.Stop:
                    using (var path = RoundedRect(new RectangleF(5.5f, 5.5f, 13, 13), 2)) g.FillPath(ink, path);
                    break;
                case IconKind.Refresh:
                    g.DrawArc(pen, 4.5f, 4.5f, 15, 15, -60, 300);
                    g.DrawLines(pen, new[] { new PointF(15, 2.5f), new PointF(16.5f, 6), new PointF(13, 7.5f) });
                    break;
                case IconKind.Globe:
                    using (var p = new Pen(Blue, 1.8f))
                    {
                        g.DrawEllipse(p, 3, 3, 18, 18);
                        g.DrawEllipse(p, 8, 3, 8, 18);
                        g.DrawLine(p, 3, 12, 21, 12);
                        g.DrawLine(p, 4.5f, 7.5f, 19.5f, 7.5f);
                        g.DrawLine(p, 4.5f, 16.5f, 19.5f, 16.5f);
                    }
                    break;
                case IconKind.Keyboard:
                    using (var path = RoundedRect(new RectangleF(2, 6, 20, 13), 2.5f)) g.DrawPath(pen, path);
                    for (int i = 0; i < 4; i++)
                    {
                        g.FillRectangle(ink, 5 + i * 4, 9.2f, 2, 2);
                        g.FillRectangle(ink, 5 + i * 4, 12.2f, 2, 2);
                    }
                    g.DrawLine(pen, 8, 16, 16, 16);
                    break;
                case IconKind.Delete:
                    g.DrawLine(pen, 4, 6.5f, 20, 6.5f);
                    g.DrawLines(pen, new[] { new PointF(9, 6.5f), new PointF(9.5f, 3.5f), new PointF(14.5f, 3.5f), new PointF(15, 6.5f) });
                    g.DrawPolygon(pen, new[] { new PointF(6, 6.5f), new PointF(7.5f, 20.5f), new PointF(16.5f, 20.5f), new PointF(18, 6.5f) });
                    break;
            }
        }
    }
}
