using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Windows.Forms;

namespace MiniSnap
{
    enum CaptureChoice { Image, Video, Scroll }

    // Full-screen frozen screenshot on which the user picks a window or drags a region.
    // With AskMode the selection stays editable and a small bar asks: screenshot, video or scrolling capture?
    class CaptureOverlay : Form
    {
        static readonly Color Accent = Color.FromArgb(255, 120, 30);
        static readonly Color BarBlue = Color.FromArgb(25, 110, 225);
        static readonly Color BarGray = Color.FromArgb(70, 72, 80);
        const int MagPixels = 15;
        const int EdgeL = 1, EdgeT = 2, EdgeR = 4, EdgeB = 8;

        enum DragKind { None, Move, Resize }

        readonly Bitmap src, dim;
        readonly Rectangle screenBounds, imageRect;
        readonly List<Rectangle> windows = new List<Rectangle>();
        readonly Font labelFont;
        readonly float ui;
        readonly int magZoom, gap, handle;

        Point cursor = new Point(-10000, -10000);
        Point dragStart;
        bool mouseDown, dragging, selected;
        Rectangle selection, hover, lastHighlight, dragOrig;
        DragKind dragKind;
        int dragEdges;
        readonly List<Rectangle> lastDirty = new List<Rectangle>();

        Panel bar;
        TextBox widthBox, heightBox;
        readonly ToolTip tips = new ToolTip();

        public Rectangle Selection { get; private set; }
        public CaptureChoice Choice { get; private set; }

        // Ask screenshot / video / scroll after a region is chosen, instead of returning at once.
        public bool AskMode { get; set; }

        // Optional instruction shown at the top of the screen the cursor is on.
        public string Prompt { get; set; }
        Rectangle promptRect;

        public CaptureOverlay(Bitmap shot, Rectangle virtualScreen, List<Rectangle> windowRects)
        {
            screenBounds = virtualScreen;
            imageRect = new Rectangle(0, 0, shot.Width, shot.Height);
            src = new Bitmap(shot.Width, shot.Height, PixelFormat.Format32bppPArgb);
            dim = new Bitmap(shot.Width, shot.Height, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(src)) DrawCopy(g, shot, imageRect);
            using (var g = Graphics.FromImage(dim))
            {
                DrawCopy(g, shot, imageRect);
                using (var b = new SolidBrush(Color.FromArgb(125, 0, 0, 0))) g.FillRectangle(b, imageRect);
            }
            if (windowRects != null)
            {
                foreach (var r in windowRects)
                {
                    var rr = r;
                    rr.Offset(-screenBounds.X, -screenBounds.Y);
                    rr.Intersect(imageRect);
                    if (rr.Width > 4 && rr.Height > 4) windows.Add(rr);
                }
            }

            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.Manual;
            Bounds = screenBounds;
            ShowInTaskbar = false;
            TopMost = true;
            Cursor = Cursors.Cross;
            Text = "MiniSnap";
            KeyPreview = true;
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.UserPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.Opaque, true);

            using (var g = CreateGraphics()) ui = g.DpiX / 96f;
            magZoom = Math.Max(6, (int)Math.Round(8 * ui));
            gap = (int)(22 * ui);
            handle = Math.Max(6, (int)(7 * ui));
            labelFont = new Font("Segoe UI", 9f, FontStyle.Bold);
        }

        static void DrawCopy(Graphics g, Image img, Rectangle r)
        {
            g.CompositingMode = CompositingMode.SourceCopy;
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(img, r, r, GraphicsUnit.Pixel);
            g.CompositingMode = CompositingMode.SourceOver;
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            Bounds = screenBounds;
            if (!string.IsNullOrEmpty(Prompt))
            {
                var mon = Screen.FromPoint(Cursor.Position).Bounds;
                mon.Offset(-screenBounds.X, -screenBounds.Y);
                var sz = TextRenderer.MeasureText(Prompt, labelFont);
                int w = sz.Width + 32, h = sz.Height + 16;
                promptRect = new Rectangle(mon.X + (mon.Width - w) / 2, mon.Y + 24, w, h);
                Invalidate(promptRect);
            }
            Activate();
            UpdateState(PointToClient(Cursor.Position));
        }

        // Used by --selftest to render states without real mouse input.
        public void SimulateDrag(Point from, Point to)
        {
            mouseDown = true;
            dragStart = from;
            UpdateState(to);
            Invalidate();
        }

        public void SimulateSelect(Rectangle r) { EnterSelected(Rectangle.Intersect(r, imageRect)); }

        Rectangle Highlight { get { return selected || dragging ? selection : hover; } }

        void UpdateState(Point p)
        {
            cursor = p;
            if (mouseDown)
            {
                if (!dragging && (Math.Abs(p.X - dragStart.X) > 3 || Math.Abs(p.Y - dragStart.Y) > 3)) dragging = true;
                if (dragging) selection = FromPoints(dragStart, p);
            }
            if (!dragging) hover = FindWindowAt(p);
            InvalidateDirty();
        }

        Rectangle FindWindowAt(Point p)
        {
            foreach (var r in windows) if (r.Contains(p)) return r;
            var mon = Screen.FromPoint(new Point(p.X + screenBounds.X, p.Y + screenBounds.Y)).Bounds;
            mon.Offset(-screenBounds.X, -screenBounds.Y);
            return Rectangle.Intersect(mon, imageRect);
        }

        Rectangle FromPoints(Point a, Point b)
        {
            var r = Rectangle.FromLTRB(Math.Min(a.X, b.X), Math.Min(a.Y, b.Y), Math.Max(a.X, b.X) + 1, Math.Max(a.Y, b.Y) + 1);
            return Rectangle.Intersect(r, imageRect);
        }

        // Only repaint what changed: a full-screen repaint per mouse move is too slow on 4K screens.
        void InvalidateDirty()
        {
            var h = Highlight;
            if (h != lastHighlight)
            {
                using (var region = new Region(lastHighlight))
                {
                    region.Xor(h);
                    Invalidate(region);
                }
                AddFrame(lastHighlight);
                AddFrame(h);
                Invalidate(LabelRect(lastHighlight));
                Invalidate(LabelRect(h));
                lastHighlight = h;
            }
            var now = new List<Rectangle>();
            if (!selected)
            {
                now.Add(new Rectangle(0, cursor.Y - 1, Width, 3));
                now.Add(new Rectangle(cursor.X - 1, 0, 3, Height));
                now.Add(Rectangle.Inflate(MagnifierRect(), 2, 2));
            }
            foreach (var r in lastDirty) Invalidate(r);
            foreach (var r in now) Invalidate(r);
            lastDirty.Clear();
            lastDirty.AddRange(now);
        }

        void AddFrame(Rectangle r)
        {
            if (r.IsEmpty) return;
            int t = handle + 4;
            Invalidate(new Rectangle(r.X - t, r.Y - t, r.Width + 2 * t, 2 * t));
            Invalidate(new Rectangle(r.X - t, r.Bottom - t, r.Width + 2 * t, 2 * t));
            Invalidate(new Rectangle(r.X - t, r.Y - t, 2 * t, r.Height + 2 * t));
            Invalidate(new Rectangle(r.Right - t, r.Y - t, 2 * t, r.Height + 2 * t));
            Invalidate(new Rectangle(r.X + r.Width / 2 - t, r.Y - t, 2 * t, 2 * t));
        }

        string SizeText(Rectangle r) { return r.Width + L.T(" × ") + r.Height; }

        Rectangle LabelRect(Rectangle h)
        {
            if (h.IsEmpty) return Rectangle.Empty;
            var sz = TextRenderer.MeasureText(SizeText(h), labelFont);
            int w = sz.Width + 12, ht = sz.Height + 6;
            int x = Math.Max(0, Math.Min(h.X, Width - w));
            int y = h.Y - ht - 6 - (selected ? handle / 2 : 0);
            if (y < 0) y = h.Y + 6 + (selected ? handle : 0);
            return new Rectangle(x, y, w, ht);
        }

        Rectangle MagnifierRect()
        {
            int zoomSize = MagPixels * magZoom;
            int infoH = TextRenderer.MeasureText("0\n0", labelFont).Height + 10;
            int w = zoomSize, h = zoomSize + infoH;
            int x = cursor.X + gap, y = cursor.Y + gap;
            if (x + w > Width) x = cursor.X - gap - w;
            if (y + h > Height) y = cursor.Y - gap - h;
            return new Rectangle(x, y, w, h);
        }

        IEnumerable<Rectangle> Handles(Rectangle r)
        {
            int s = handle, hs = s / 2;
            int[] xs = { r.Left, r.Left + r.Width / 2, r.Right };
            int[] ys = { r.Top, r.Top + r.Height / 2, r.Bottom };
            foreach (int y in ys)
                foreach (int x in xs)
                    if (!(x == xs[1] && y == ys[1])) yield return new Rectangle(x - hs, y - hs, s, s);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            Rectangle clip = e.ClipRectangle;
            g.CompositingMode = CompositingMode.SourceCopy;
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(dim, clip, clip, GraphicsUnit.Pixel);
            var h = Highlight;
            var lit = Rectangle.Intersect(h, clip);
            if (lit.Width > 0 && lit.Height > 0) g.DrawImage(src, lit, lit, GraphicsUnit.Pixel);
            g.CompositingMode = CompositingMode.SourceOver;
            g.PixelOffsetMode = PixelOffsetMode.Default;

            if (!selected)
            {
                using (var pen = new Pen(Color.FromArgb(170, 255, 255, 255), 1f))
                {
                    pen.DashPattern = new float[] { 4, 3 };
                    g.DrawLine(pen, 0, cursor.Y, Width, cursor.Y);
                    g.DrawLine(pen, cursor.X, 0, cursor.X, Height);
                }
            }

            if (!h.IsEmpty)
            {
                using (var pen = new Pen(Accent, 2f)) g.DrawRectangle(pen, h.X - 1, h.Y - 1, h.Width + 1, h.Height + 1);
                if (selected)
                    using (var pen = new Pen(Accent, 1.5f))
                        foreach (var hr in Handles(h))
                        {
                            g.FillRectangle(Brushes.White, hr);
                            g.DrawRectangle(pen, hr);
                        }
                var lr = LabelRect(h);
                g.SmoothingMode = SmoothingMode.AntiAlias;
                using (var path = Icons.RoundedRect(lr, 4))
                using (var br = new SolidBrush(Color.FromArgb(220, 25, 25, 28)))
                    g.FillPath(br, path);
                g.SmoothingMode = SmoothingMode.None;
                TextRenderer.DrawText(g, SizeText(h), labelFont, lr, Color.White,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding);
            }

            if (!promptRect.IsEmpty && promptRect.IntersectsWith(clip) && !selected)
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                using (var path = Icons.RoundedRect(promptRect, promptRect.Height / 2f))
                using (var br = new SolidBrush(Color.FromArgb(235, 255, 120, 30)))
                    g.FillPath(br, path);
                g.SmoothingMode = SmoothingMode.None;
                TextRenderer.DrawText(g, Prompt, labelFont, promptRect, Color.White, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            }

            if (!selected) DrawMagnifier(g);
        }

        void DrawMagnifier(Graphics g)
        {
            Rectangle box = MagnifierRect();
            int zoomSize = MagPixels * magZoom, half = MagPixels / 2;
            var zoomRect = new Rectangle(box.X, box.Y, zoomSize, zoomSize);
            g.FillRectangle(Brushes.Black, box);
            g.InterpolationMode = InterpolationMode.NearestNeighbor;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            g.DrawImage(src, zoomRect, new Rectangle(cursor.X - half, cursor.Y - half, MagPixels, MagPixels), GraphicsUnit.Pixel);
            g.PixelOffsetMode = PixelOffsetMode.Default;

            using (var band = new SolidBrush(Color.FromArgb(50, Accent)))
            {
                g.FillRectangle(band, zoomRect.X, zoomRect.Y + half * magZoom, zoomSize, magZoom);
                g.FillRectangle(band, zoomRect.X + half * magZoom, zoomRect.Y, magZoom, zoomSize);
            }
            using (var pen = new Pen(Accent, 1f))
                g.DrawRectangle(pen, zoomRect.X + half * magZoom, zoomRect.Y + half * magZoom, magZoom, magZoom);
            g.DrawRectangle(Pens.White, box.X, box.Y, box.Width - 1, box.Height - 1);

            Color c = imageRect.Contains(cursor) ? src.GetPixel(cursor.X, cursor.Y) : Color.Black;
            var info = new Rectangle(box.X, zoomRect.Bottom, box.Width, box.Height - zoomSize);
            int sw = info.Height / 2;
            var swatch = new Rectangle(info.X + 8, info.Y + (info.Height - sw) / 2, sw, sw);
            using (var br = new SolidBrush(c)) g.FillRectangle(br, swatch);
            g.DrawRectangle(Pens.Gray, swatch);
            string text = cursor.X + ", " + cursor.Y + "\n#" + c.R.ToString("X2") + c.G.ToString("X2") + c.B.ToString("X2");
            var textRect = new Rectangle(swatch.Right + 8, info.Y, info.Right - swatch.Right - 8, info.Height);
            TextRenderer.DrawText(g, text, labelFont, textRect, Color.White, TextFormatFlags.VerticalCenter | TextFormatFlags.Left);
        }

        // ---------- Selected state: editable selection + mode bar ----------

        void EnterSelected(Rectangle r)
        {
            selection = r;
            selected = true;
            mouseDown = dragging = false;
            dragKind = DragKind.None;
            Cursor = Cursors.Default;
            ShowBar();
            Invalidate();
        }

        void Reselect()
        {
            selected = false;
            dragKind = DragKind.None;
            if (bar != null) bar.Visible = false;
            ActiveControl = null;
            Cursor = Cursors.Cross;
            Invalidate();
            UpdateState(PointToClient(Cursor.Position));
        }

        void Finish(CaptureChoice choice)
        {
            if (selection.Width < 3 || selection.Height < 3) return;
            Choice = choice;
            Selection = selection;
            DialogResult = DialogResult.OK;
        }

        int HitEdges(Point p)
        {
            var r = selection;
            int t = handle;
            if (!Rectangle.Inflate(r, t, t).Contains(p)) return 0;
            int e = 0;
            if (Math.Abs(p.X - r.Left) <= t) e |= EdgeL; else if (Math.Abs(p.X - r.Right) <= t) e |= EdgeR;
            if (Math.Abs(p.Y - r.Top) <= t) e |= EdgeT; else if (Math.Abs(p.Y - r.Bottom) <= t) e |= EdgeB;
            return e;
        }

        static Cursor CursorFor(int edges)
        {
            switch (edges)
            {
                case EdgeL | EdgeT: case EdgeR | EdgeB: return Cursors.SizeNWSE;
                case EdgeR | EdgeT: case EdgeL | EdgeB: return Cursors.SizeNESW;
                case EdgeL: case EdgeR: return Cursors.SizeWE;
                case EdgeT: case EdgeB: return Cursors.SizeNS;
            }
            return Cursors.Default;
        }

        void SetSelection(Rectangle r)
        {
            r = Rectangle.Intersect(r, imageRect);
            if (r.Width < 4 || r.Height < 4) return;
            selection = r;
            InvalidateDirty();
            PositionBar();
        }

        void DragSelection(Point p)
        {
            int dx = p.X - dragStart.X, dy = p.Y - dragStart.Y;
            var o = dragOrig;
            if (dragKind == DragKind.Move)
            {
                int x = Math.Max(imageRect.Left, Math.Min(o.X + dx, imageRect.Right - o.Width));
                int y = Math.Max(imageRect.Top, Math.Min(o.Y + dy, imageRect.Bottom - o.Height));
                SetSelection(new Rectangle(x, y, o.Width, o.Height));
                return;
            }
            int l = o.Left, t = o.Top, rr = o.Right, b = o.Bottom;
            if ((dragEdges & EdgeL) != 0) l += dx;
            if ((dragEdges & EdgeR) != 0) rr += dx;
            if ((dragEdges & EdgeT) != 0) t += dy;
            if ((dragEdges & EdgeB) != 0) b += dy;
            SetSelection(Rectangle.FromLTRB(Math.Min(l, rr), Math.Min(t, b), Math.Max(l, rr), Math.Max(t, b)));
        }

        Button BarButton(IconKind icon, Color back, string tip, Action onClick)
        {
            int s = (int)(42 * ui);
            var b = new Button
            {
                Size = new Size(s, s),
                FlatStyle = FlatStyle.Flat,
                BackColor = back,
                Image = Icons.Draw(icon, (int)(24 * ui), Color.White, back),
                Margin = new Padding((int)(3 * ui)),
                Cursor = Cursors.Hand,
                TabStop = false,
            };
            b.FlatAppearance.BorderSize = 0;
            b.FlatAppearance.MouseOverBackColor = ControlPaint.Light(back, 0.3f);
            b.FlatAppearance.MouseDownBackColor = ControlPaint.Dark(back, 0.1f);
            using (var path = Icons.RoundedRect(new RectangleF(0, 0, s, s), 6 * ui)) b.Region = new Region(path);
            b.Click += (sender, e) => onClick();
            tips.SetToolTip(b, tip);
            return b;
        }

        TextBox SizeBox(string tip)
        {
            var t = new TextBox
            {
                Width = (int)(58 * ui),
                TextAlign = HorizontalAlignment.Center,
                BackColor = Color.FromArgb(58, 60, 66),
                ForeColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 10.5f),
                Margin = new Padding((int)(3 * ui), (int)(11 * ui), (int)(3 * ui), 0),
                MaxLength = 5,
            };
            t.KeyPress += (s, e) => { if (!char.IsDigit(e.KeyChar) && !char.IsControl(e.KeyChar)) e.Handled = true; };
            t.KeyDown += (s, e) =>
            {
                if (e.KeyCode == Keys.Enter) { e.SuppressKeyPress = true; ApplySizeBoxes(); ActiveControl = null; }
                else if (e.KeyCode == Keys.Escape) { e.SuppressKeyPress = true; UpdateSizeBoxes(); ActiveControl = null; }
            };
            t.Leave += (s, e) => ApplySizeBoxes();
            tips.SetToolTip(t, tip);
            return t;
        }

        void BuildBar()
        {
            var flow = new FlowLayoutPanel
            {
                AutoSize = true,
                AutoSizeMode = AutoSizeMode.GrowAndShrink,
                WrapContents = false,
                BackColor = Color.FromArgb(34, 35, 40),
                Padding = new Padding((int)(5 * ui)),
                Location = Point.Empty,
            };
            flow.Controls.Add(BarButton(IconKind.Camera, BarBlue, L.T("Chụp ảnh (Enter)"), () => Finish(CaptureChoice.Image)));
            flow.Controls.Add(BarButton(IconKind.Video, BarBlue, L.T("Quay video (V)"), () => Finish(CaptureChoice.Video)));
            flow.Controls.Add(BarButton(IconKind.Scroll, BarBlue, L.T("Chụp cuộn (S)"), () => Finish(CaptureChoice.Scroll)));
            widthBox = SizeBox(L.T("Rộng (px) — nhập rồi nhấn Enter"));
            heightBox = SizeBox(L.T("Cao (px) — nhập rồi nhấn Enter"));
            widthBox.Margin = new Padding((int)(14 * ui), widthBox.Margin.Top, widthBox.Margin.Right, 0);
            flow.Controls.Add(widthBox);
            flow.Controls.Add(new Label { Text = "×", AutoSize = true, ForeColor = Color.Silver, Font = new Font("Segoe UI", 11f), Margin = new Padding(0, (int)(11 * ui), 0, 0) });
            flow.Controls.Add(heightBox);
            var reselect = BarButton(IconKind.Refresh, BarGray, L.T("Chọn lại (R)"), Reselect);
            reselect.Margin = new Padding((int)(14 * ui), reselect.Margin.Top, reselect.Margin.Right, reselect.Margin.Bottom);
            flow.Controls.Add(reselect);
            flow.Controls.Add(BarButton(IconKind.Close, BarGray, L.T("Huỷ (Esc)"), () => DialogResult = DialogResult.Cancel));

            bar = new Panel { BackColor = flow.BackColor, Cursor = Cursors.Default };
            bar.Controls.Add(flow);
            bar.Size = flow.PreferredSize;
            using (var path = Icons.RoundedRect(new RectangleF(0, 0, bar.Width, bar.Height), 8 * ui)) bar.Region = new Region(path);
            Controls.Add(bar);
        }

        void ShowBar()
        {
            if (bar == null) BuildBar();
            UpdateSizeBoxes();
            PositionBar();
            bar.Visible = true;
            bar.BringToFront();
            ActiveControl = null;
        }

        void UpdateSizeBoxes()
        {
            if (widthBox == null) return;
            if (!widthBox.Focused) widthBox.Text = selection.Width.ToString();
            if (!heightBox.Focused) heightBox.Text = selection.Height.ToString();
        }

        void ApplySizeBoxes()
        {
            int w, h;
            if (!int.TryParse(widthBox.Text, out w) || !int.TryParse(heightBox.Text, out h)) { UpdateSizeBoxes(); return; }
            w = Math.Max(4, Math.Min(w, imageRect.Right - selection.X));
            h = Math.Max(4, Math.Min(h, imageRect.Bottom - selection.Y));
            SetSelection(new Rectangle(selection.X, selection.Y, w, h));
            UpdateSizeBoxes();
        }

        // Below the selection, else above it, else inside its bottom edge; always on the selection's monitor.
        void PositionBar()
        {
            if (bar == null) return;
            UpdateSizeBoxes();
            var monScreen = Screen.FromRectangle(new Rectangle(selection.X + screenBounds.X, selection.Y + screenBounds.Y, selection.Width, selection.Height)).Bounds;
            monScreen.Offset(-screenBounds.X, -screenBounds.Y);
            int pad = (int)(10 * ui);
            int x = selection.X + (selection.Width - bar.Width) / 2;
            x = Math.Max(monScreen.Left + pad, Math.Min(x, monScreen.Right - bar.Width - pad));
            int y = selection.Bottom + pad + handle;
            if (y + bar.Height > monScreen.Bottom - pad) y = selection.Top - bar.Height - pad - handle - LabelRect(selection).Height;
            if (y < monScreen.Top + pad) y = selection.Bottom - bar.Height - pad;
            bar.Location = new Point(x, y);
        }

        bool EditingSize { get { return widthBox != null && (widthBox.Focused || heightBox.Focused); } }

        // ---------- Mouse and keyboard ----------

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right) { DialogResult = DialogResult.Cancel; return; }
            if (e.Button != MouseButtons.Left) return;
            if (selected)
            {
                ActiveControl = null;
                int edges = HitEdges(e.Location);
                if (edges != 0 || selection.Contains(e.Location))
                {
                    dragKind = edges != 0 ? DragKind.Resize : DragKind.Move;
                    dragEdges = edges;
                    dragStart = e.Location;
                    dragOrig = selection;
                    return;
                }
                // Clicking outside starts a brand-new selection.
                selected = false;
                bar.Visible = false;
                Cursor = Cursors.Cross;
                Invalidate();
            }
            mouseDown = true;
            dragging = false;
            dragStart = e.Location;
            UpdateState(e.Location);
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            if (selected)
            {
                if (dragKind != DragKind.None) { DragSelection(e.Location); return; }
                int edges = HitEdges(e.Location);
                Cursor = edges != 0 ? CursorFor(edges) : selection.Contains(e.Location) ? Cursors.SizeAll : Cursors.Default;
                return;
            }
            UpdateState(e.Location);
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left) return;
            if (selected) { dragKind = DragKind.None; return; }
            if (!mouseDown) return;
            mouseDown = false;
            Rectangle r = dragging ? selection : hover;
            dragging = false;
            if (r.Width < 3 || r.Height < 3) { UpdateState(e.Location); return; }
            if (AskMode) { EnterSelected(r); return; }
            selection = r;
            Finish(CaptureChoice.Image);
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (EditingSize) return base.ProcessCmdKey(ref msg, keyData);
            int step = (keyData & Keys.Shift) != 0 ? 10 : 1;
            Keys key = keyData & Keys.KeyCode;
            if (selected)
            {
                switch (key)
                {
                    case Keys.Escape: DialogResult = DialogResult.Cancel; return true;
                    case Keys.Enter:
                    case Keys.Space:
                    case Keys.C: Finish(CaptureChoice.Image); return true;
                    case Keys.V: Finish(CaptureChoice.Video); return true;
                    case Keys.S: Finish(CaptureChoice.Scroll); return true;
                    case Keys.R:
                    case Keys.Back: Reselect(); return true;
                    case Keys.Left: SetSelection(new Rectangle(selection.X - step, selection.Y, selection.Width, selection.Height)); return true;
                    case Keys.Right: SetSelection(new Rectangle(selection.X + step, selection.Y, selection.Width, selection.Height)); return true;
                    case Keys.Up: SetSelection(new Rectangle(selection.X, selection.Y - step, selection.Width, selection.Height)); return true;
                    case Keys.Down: SetSelection(new Rectangle(selection.X, selection.Y + step, selection.Width, selection.Height)); return true;
                }
                return base.ProcessCmdKey(ref msg, keyData);
            }
            switch (key)
            {
                case Keys.Escape: DialogResult = DialogResult.Cancel; return true;
                case Keys.Enter:
                case Keys.Space:
                    if (AskMode) EnterSelected(imageRect);
                    else { selection = imageRect; Finish(CaptureChoice.Image); }
                    return true;
                case Keys.Left: Nudge(-step, 0); return true;
                case Keys.Right: Nudge(step, 0); return true;
                case Keys.Up: Nudge(0, -step); return true;
                case Keys.Down: Nudge(0, step); return true;
            }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        void Nudge(int dx, int dy)
        {
            var p = Cursor.Position;
            Cursor.Position = new Point(p.X + dx, p.Y + dy);
            UpdateState(PointToClient(Cursor.Position));
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                src.Dispose();
                dim.Dispose();
                labelFont.Dispose();
                tips.Dispose();
            }
            base.Dispose(disposing);
        }
    }
}
