using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace MiniSnap
{
    // Small always-on-top bar that never takes focus and is invisible to screen capture,
    // so it can sit over the area being scrolled or recorded.
    class FloatingBar : Form
    {
        protected readonly float ui;

        public FloatingBar()
        {
            using (var g = CreateGraphics()) ui = g.DpiX / 96f;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.FromArgb(32, 32, 36);
            ForeColor = Color.White;
            Font = Theme.UiFont(9.5f);
            Padding = new Padding((int)(6 * ui));
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x08000000 | 0x00000080; // WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            NativeMethods.ExcludeFromCapture(Handle);
            Theme.RoundCorners(Handle);
        }

        // Puts the bar just below (or above, or inside) the target rectangle.
        protected void PlaceNear(Rectangle target)
        {
            var wa = Screen.FromRectangle(target).WorkingArea;
            int gap = (int)(8 * ui);
            int x = Math.Max(wa.Left, Math.Min(target.Left + (target.Width - Width) / 2, wa.Right - Width));
            int y = target.Bottom + gap;
            if (y + Height > wa.Bottom) y = target.Top - Height - gap;
            if (y < wa.Top) y = target.Bottom - Height - gap;
            Location = new Point(x, y);
        }

        protected Button MakeButton(string text, IconKind icon)
        {
            var b = new Button
            {
                Text = text,
                Image = Icons.Draw(icon, (int)(16 * ui), Color.FromArgb(30, 30, 30), Color.FromArgb(240, 240, 242)),
                TextImageRelation = TextImageRelation.ImageBeforeText,
                FlatStyle = FlatStyle.Flat,
                BackColor = Color.FromArgb(240, 240, 242),
                ForeColor = Color.FromArgb(30, 30, 30),
                AutoSize = true,
                Padding = new Padding((int)(4 * ui), 0, (int)(4 * ui), 0),
                Margin = new Padding((int)(4 * ui)),
                Cursor = Cursors.Hand,
            };
            b.FlatAppearance.BorderSize = 0;
            return b;
        }
    }

    // Row-matching stitcher for scrolling capture. Kept free of UI so it can be tested on synthetic frames.
    class ScrollStitcher
    {
        class Rows
        {
            public long[] Hash;
            public bool[] Uniform;
        }

        class Segment
        {
            public Bitmap Frame;
            public int Y, Height;
        }

        readonly List<Segment> segments = new List<Segment>();
        readonly List<Bitmap> frames = new List<Bitmap>();
        Rows prevRows;
        int frameH;

        public int TotalHeight { get; private set; }
        public int FrameCount { get { return frames.Count; } }
        public int LastShift { get; private set; }
        public int LastUsableHeight { get; private set; }

        public enum Outcome { Added, NoMovement, NoMatch }

        static Rows Analyze(Bitmap bmp)
        {
            int w = bmp.Width, h = bmp.Height;
            var data = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppRgb);
            var px = new int[data.Stride / 4 * h];
            Marshal.Copy(data.Scan0, px, 0, px.Length);
            int stride = data.Stride / 4;
            bmp.UnlockBits(data);
            // Skip the right edge: a moving scrollbar thumb would make every row look different.
            int x0 = Math.Min(4, w / 4), x1 = Math.Max(x0 + 1, w - Math.Min(28, w / 4));
            var rows = new Rows { Hash = new long[h], Uniform = new bool[h] };
            for (int y = 0; y < h; y++)
            {
                int o = y * stride;
                long hash = 1469598103934665603L;
                int first = px[o + x0] & 0xFFFFFF;
                bool uniform = true;
                for (int x = x0; x < x1; x++)
                {
                    int v = px[o + x] & 0xFFFFFF;
                    if (v != first) uniform = false;
                    hash = (hash ^ v) * 1099511628211L;
                }
                rows.Hash[y] = hash;
                rows.Uniform[y] = uniform;
            }
            return rows;
        }

        public void AddFirst(Bitmap frame)
        {
            frames.Add(frame);
            frameH = frame.Height;
            prevRows = Analyze(frame);
            segments.Add(new Segment { Frame = frame, Y = 0, Height = frameH });
            TotalHeight = frameH;
        }

        public Outcome Add(Bitmap frame)
        {
            var cur = Analyze(frame);
            int h = frameH;
            int top = 0, bottom = 0;
            while (top < h && cur.Hash[top] == prevRows.Hash[top]) top++;
            if (top == h) return Outcome.NoMovement;
            while (bottom < h - top && cur.Hash[h - 1 - bottom] == prevRows.Hash[h - 1 - bottom]) bottom++;
            // Unchanged bands at the edges are sticky headers/footers (or browser chrome).
            top = Math.Min(top, h * 2 / 5);
            bottom = Math.Min(bottom, h * 2 / 5);
            int usable = h - top - bottom;
            LastUsableHeight = usable;
            const int minOverlap = 12;

            int bestD = -1;
            double bestScore = 0;
            for (int d = 1; d <= usable - minOverlap; d++)
            {
                int total = 0, matches = 0;
                for (int i = top; i + d < h - bottom; i++)
                {
                    if (cur.Uniform[i]) continue;
                    total++;
                    if (cur.Hash[i] == prevRows.Hash[i + d]) matches++;
                }
                if (total < 6) continue;
                double score = (double)matches / total;
                if (score > bestScore + 1e-9) { bestScore = score; bestD = d; }
            }
            if (bestD < 0 || bestScore < 0.9) return Outcome.NoMatch;

            // Drop the previous frame's footer, then append the newly revealed rows plus the current footer.
            Trim(bottom);
            segments.Add(new Segment { Frame = frame, Y = h - bottom - bestD, Height = bestD + bottom });
            TotalHeight += bestD + bottom;
            frames.Add(frame);
            prevRows = cur;
            LastShift = bestD;
            return Outcome.Added;
        }

        void Trim(int rows)
        {
            TotalHeight -= rows;
            while (rows > 0 && segments.Count > 0)
            {
                var last = segments[segments.Count - 1];
                int take = Math.Min(rows, last.Height);
                last.Height -= take;
                rows -= take;
                if (last.Height == 0) segments.RemoveAt(segments.Count - 1);
            }
        }

        public Bitmap Compose()
        {
            int w = frames[0].Width;
            var result = new Bitmap(w, TotalHeight, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(result))
            {
                g.CompositingMode = CompositingMode.SourceCopy;
                g.InterpolationMode = InterpolationMode.NearestNeighbor;
                g.PixelOffsetMode = PixelOffsetMode.Half;
                int y = 0;
                foreach (var s in segments)
                {
                    g.DrawImage(s.Frame, new Rectangle(0, y, w, s.Height), new Rectangle(0, s.Y, w, s.Height), GraphicsUnit.Pixel);
                    y += s.Height;
                }
            }
            return result;
        }

        public void DisposeFrames()
        {
            foreach (var f in frames) f.Dispose();
            frames.Clear();
            segments.Clear();
        }
    }

    // Drives the target window with mouse-wheel input and feeds frames to the stitcher.
    class ScrollCaptureSession : FloatingBar
    {
        const int MaxHeight = 30000, MaxFrames = 120, SettleMs = 450;

        readonly Rectangle screenRect;
        readonly Action<Bitmap> onDone;
        readonly ScrollStitcher stitcher = new ScrollStitcher();
        readonly Timer timer = new Timer();
        readonly Label status;
        int notches, pendingScroll, failures;
        bool finished;

        public ScrollCaptureSession(Rectangle screenRect, Action<Bitmap> onDone)
        {
            this.screenRect = screenRect;
            this.onDone = onDone;
            notches = screenRect.Height < 350 ? 1 : 3;

            var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = false, BackColor = BackColor };
            status = new Label { AutoSize = true, ForeColor = Color.White, Margin = new Padding((int)(8 * ui), (int)(10 * ui), (int)(12 * ui), 0), Text = L.T("Đang chuẩn bị chụp cuộn...") };
            var stop = MakeButton(L.T("Dừng (Esc)"), IconKind.Stop);
            stop.Click += (s, e) => Finish();
            flow.Controls.Add(status);
            flow.Controls.Add(stop);
            Controls.Add(flow);
            AutoSize = true;
            AutoSizeMode = AutoSizeMode.GrowAndShrink;

            timer.Tick += (s, e) => Step();
        }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            PlaceNear(screenRect);
            timer.Interval = 250; // let the selection overlay disappear first
            timer.Start();
        }

        Point Center { get { return new Point(screenRect.Left + screenRect.Width / 2, screenRect.Top + screenRect.Height / 2); } }

        void ScrollBy(int n)
        {
            Cursor.Position = Center;
            NativeMethods.MouseWheel(-120 * n);
        }

        void Step()
        {
            timer.Stop();
            if (finished) return;
            if (NativeMethods.IsKeyDown(Keys.Escape)) { Finish(); return; }

            if (pendingScroll != 0)
            {
                ScrollBy(pendingScroll);
                pendingScroll = 0;
                timer.Interval = SettleMs;
                timer.Start();
                return;
            }

            var frame = ScreenCapture.Capture(screenRect);
            if (stitcher.FrameCount == 0)
            {
                stitcher.AddFirst(frame);
                Cursor.Position = Center;
            }
            else
            {
                var outcome = stitcher.Add(frame);
                if (outcome == ScrollStitcher.Outcome.NoMovement) { frame.Dispose(); Finish(); return; }
                if (outcome == ScrollStitcher.Outcome.NoMatch)
                {
                    frame.Dispose();
                    // Probably scrolled further than one screen: go back and retry with a smaller step.
                    if (failures++ < 2 && notches > 1)
                    {
                        ScrollBy(-notches);
                        notches = Math.Max(1, notches / 2);
                        pendingScroll = notches;
                        timer.Interval = SettleMs;
                        timer.Start();
                        return;
                    }
                    Finish();
                    return;
                }
                failures = 0;
                double perNotch = (double)stitcher.LastShift / notches;
                if (perNotch > 0) notches = Math.Max(1, Math.Min(10, (int)(stitcher.LastUsableHeight * 0.6 / perNotch)));
            }
            status.Text = L.T("Đang chụp cuộn... ") + stitcher.FrameCount + L.T(" lần, cao ") + stitcher.TotalHeight + " px";
            if (stitcher.TotalHeight >= MaxHeight || stitcher.FrameCount >= MaxFrames) { Finish(); return; }
            ScrollBy(notches);
            timer.Interval = SettleMs;
            timer.Start();
        }

        void Finish()
        {
            if (finished) return;
            finished = true;
            timer.Stop();
            Bitmap result = null;
            if (stitcher.FrameCount > 0) result = stitcher.Compose();
            stitcher.DisposeFrames();
            Close();
            if (result != null) onDone(result);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) timer.Dispose();
            base.Dispose(disposing);
        }
    }
}
