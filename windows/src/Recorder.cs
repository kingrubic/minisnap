using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace MiniSnap
{
    // Minimal Media Foundation interop: just enough of the Sink Writer to encode RGB32 frames to H.264 MP4.
    // Interface methods must stay in vtable order; unused slots are placeholders.
    static class MF
    {
        public static readonly Guid MT_MAJOR_TYPE = new Guid("48eba18e-f8c9-4687-bf11-0a74c9f96a8f");
        public static readonly Guid MT_SUBTYPE = new Guid("f7e34c9a-42e8-4714-b74b-cb29d72c35e5");
        public static readonly Guid MT_AVG_BITRATE = new Guid("20332624-fb0d-4d9e-bd0d-cbf6786c102e");
        public static readonly Guid MT_INTERLACE_MODE = new Guid("e2724bb8-e676-4806-b4b2-a8d6efb44ccd");
        public static readonly Guid MT_FRAME_SIZE = new Guid("1652c33d-d6b2-4012-b834-72030849a37d");
        public static readonly Guid MT_FRAME_RATE = new Guid("c459a2e8-3d2c-4e44-b132-fee5156c7bb0");
        public static readonly Guid MT_PIXEL_ASPECT_RATIO = new Guid("c6376a1e-8d0a-4027-be45-6d9a0ad39bb6");
        public static readonly Guid MT_DEFAULT_STRIDE = new Guid("644b4e48-1e02-4516-b0eb-c01ca9d49ac6");
        public static readonly Guid MediaType_Video = new Guid("73646976-0000-0010-8000-00AA00389B71");
        public static readonly Guid VideoFormat_H264 = new Guid("34363248-0000-0010-8000-00AA00389B71");
        public static readonly Guid VideoFormat_RGB32 = new Guid("00000016-0000-0010-8000-00AA00389B71");
        public static readonly Guid READWRITE_ENABLE_HARDWARE_TRANSFORMS = new Guid("a634a91c-822b-41b9-a494-4de4643612b0");

        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFStartup(int version, int flags);
        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFShutdown();
        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFCreateMediaType(out IMFMediaType type);
        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFCreateAttributes(out IMFAttributes attrs, int initialSize);
        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFCreateSample(out IMFSample sample);
        [DllImport("mfplat.dll", ExactSpelling = true, PreserveSig = false)] public static extern void MFCreateMemoryBuffer(int maxLength, out IMFMediaBuffer buffer);
        [DllImport("mfreadwrite.dll", ExactSpelling = true, PreserveSig = false)]
        public static extern void MFCreateSinkWriterFromURL([MarshalAs(UnmanagedType.LPWStr)] string url, IntPtr byteStream, IMFAttributes attrs, out IMFSinkWriter writer);
        [DllImport("kernel32.dll", EntryPoint = "RtlMoveMemory")] public static extern void CopyMemory(IntPtr dest, IntPtr src, IntPtr count);

        public static long Pack(int hi, int lo) { return ((long)hi << 32) | (uint)lo; }
    }

    [ComImport, Guid("2cd2d921-c447-44a7-a13c-4adabfc247e3"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMFAttributes
    {
        void GetItem(); void GetItemType(); void CompareItem(); void Compare(); void GetUINT32(); void GetUINT64(); void GetDouble(); void GetGUID();
        void GetStringLength(); void GetString(); void GetAllocatedString(); void GetBlobSize(); void GetBlob(); void GetAllocatedBlob(); void GetUnknown();
        void SetItem(); void DeleteItem(); void DeleteAllItems();
        void SetUINT32([MarshalAs(UnmanagedType.LPStruct)] Guid key, int value);
        void SetUINT64([MarshalAs(UnmanagedType.LPStruct)] Guid key, long value);
        void SetDouble();
        void SetGUID([MarshalAs(UnmanagedType.LPStruct)] Guid key, [MarshalAs(UnmanagedType.LPStruct)] Guid value);
    }

    [ComImport, Guid("44ae0fa8-ea31-4109-8d2e-4cae4997c555"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMFMediaType
    {
        void GetItem(); void GetItemType(); void CompareItem(); void Compare(); void GetUINT32(); void GetUINT64(); void GetDouble(); void GetGUID();
        void GetStringLength(); void GetString(); void GetAllocatedString(); void GetBlobSize(); void GetBlob(); void GetAllocatedBlob(); void GetUnknown();
        void SetItem(); void DeleteItem(); void DeleteAllItems();
        void SetUINT32([MarshalAs(UnmanagedType.LPStruct)] Guid key, int value);
        void SetUINT64([MarshalAs(UnmanagedType.LPStruct)] Guid key, long value);
        void SetDouble();
        void SetGUID([MarshalAs(UnmanagedType.LPStruct)] Guid key, [MarshalAs(UnmanagedType.LPStruct)] Guid value);
    }

    [ComImport, Guid("c40a00f2-b93a-4d80-ae8c-5a1c634f58e4"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMFSample
    {
        void GetItem(); void GetItemType(); void CompareItem(); void Compare(); void GetUINT32(); void GetUINT64(); void GetDouble(); void GetGUID();
        void GetStringLength(); void GetString(); void GetAllocatedString(); void GetBlobSize(); void GetBlob(); void GetAllocatedBlob(); void GetUnknown();
        void SetItem(); void DeleteItem(); void DeleteAllItems(); void SetUINT32(); void SetUINT64(); void SetDouble(); void SetGUID();
        void SetString(); void SetBlob(); void SetUnknown(); void LockStore(); void UnlockStore(); void GetCount(); void GetItemByIndex(); void CopyAllItems();
        void GetSampleFlags(); void SetSampleFlags(); void GetSampleTime();
        void SetSampleTime(long time);
        void GetSampleDuration();
        void SetSampleDuration(long duration);
        void GetBufferCount(); void GetBufferByIndex(); void ConvertToContiguousBuffer();
        void AddBuffer(IMFMediaBuffer buffer);
    }

    [ComImport, Guid("045FA593-8799-42b8-BC8D-8968C6453507"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMFMediaBuffer
    {
        void Lock(out IntPtr buffer, out int maxLength, out int currentLength);
        void Unlock();
        void GetCurrentLength(out int length);
        void SetCurrentLength(int length);
    }

    [ComImport, Guid("3137f1cd-fe5e-4805-a5d8-fb477448cb3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMFSinkWriter
    {
        void AddStream(IMFMediaType targetType, out int streamIndex);
        void SetInputMediaType(int streamIndex, IMFMediaType inputType, IMFAttributes encodingParameters);
        void BeginWriting();
        void WriteSample(int streamIndex, IMFSample sample);
        void SendStreamTick(); void PlaceMarker(); void NotifyEndOfSegment(); void Flush();
        void DoFinalize();
    }

    class Mp4Writer : IDisposable
    {
        readonly IMFSinkWriter writer;
        readonly int stream, width, height;

        public Mp4Writer(string path, int width, int height, int fps, bool hardware)
        {
            this.width = width;
            this.height = height;
            IMFAttributes attrs;
            MF.MFCreateAttributes(out attrs, 1);
            attrs.SetUINT32(MF.READWRITE_ENABLE_HARDWARE_TRANSFORMS, hardware ? 1 : 0);
            MF.MFCreateSinkWriterFromURL(path, IntPtr.Zero, attrs, out writer);
            Marshal.ReleaseComObject(attrs);

            int bitrate = (int)Math.Max(2000000, Math.Min(16000000, (long)width * height * fps / 8));
            IMFMediaType output;
            MF.MFCreateMediaType(out output);
            output.SetGUID(MF.MT_MAJOR_TYPE, MF.MediaType_Video);
            output.SetGUID(MF.MT_SUBTYPE, MF.VideoFormat_H264);
            output.SetUINT32(MF.MT_AVG_BITRATE, bitrate);
            output.SetUINT32(MF.MT_INTERLACE_MODE, 2);
            output.SetUINT64(MF.MT_FRAME_SIZE, MF.Pack(width, height));
            output.SetUINT64(MF.MT_FRAME_RATE, MF.Pack(fps, 1));
            output.SetUINT64(MF.MT_PIXEL_ASPECT_RATIO, MF.Pack(1, 1));
            writer.AddStream(output, out stream);
            Marshal.ReleaseComObject(output);

            IMFMediaType input;
            MF.MFCreateMediaType(out input);
            input.SetGUID(MF.MT_MAJOR_TYPE, MF.MediaType_Video);
            input.SetGUID(MF.MT_SUBTYPE, MF.VideoFormat_RGB32);
            input.SetUINT32(MF.MT_INTERLACE_MODE, 2);
            input.SetUINT64(MF.MT_FRAME_SIZE, MF.Pack(width, height));
            input.SetUINT64(MF.MT_FRAME_RATE, MF.Pack(fps, 1));
            input.SetUINT64(MF.MT_PIXEL_ASPECT_RATIO, MF.Pack(1, 1));
            input.SetUINT32(MF.MT_DEFAULT_STRIDE, width * 4); // positive stride = top-down rows, same as GDI+
            writer.SetInputMediaType(stream, input, null);
            Marshal.ReleaseComObject(input);
            writer.BeginWriting();
        }

        public void Write(Bitmap frame, long time, long duration)
        {
            int size = width * height * 4;
            var data = frame.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.ReadOnly, PixelFormat.Format32bppRgb);
            IMFMediaBuffer buffer = null;
            IMFSample sample = null;
            try
            {
                MF.MFCreateMemoryBuffer(size, out buffer);
                IntPtr dest;
                int max, cur;
                buffer.Lock(out dest, out max, out cur);
                MF.CopyMemory(dest, data.Scan0, new IntPtr(size));
                buffer.Unlock();
                buffer.SetCurrentLength(size);
                MF.MFCreateSample(out sample);
                sample.AddBuffer(buffer);
                sample.SetSampleTime(time);
                sample.SetSampleDuration(duration);
                writer.WriteSample(stream, sample);
            }
            finally
            {
                frame.UnlockBits(data);
                if (sample != null) Marshal.ReleaseComObject(sample);
                if (buffer != null) Marshal.ReleaseComObject(buffer);
            }
        }

        public void Dispose()
        {
            try { writer.DoFinalize(); }
            finally { Marshal.ReleaseComObject(writer); }
        }
    }

    class ScreenRecorder
    {
        const int Fps = 30;
        readonly Rectangle rect;
        readonly Size outSize;
        readonly string path;
        readonly Stopwatch active = new Stopwatch();
        Thread thread;
        volatile bool stopRequested;

        public event Action<Exception> Finished;
        public string Path { get { return path; } }
        public TimeSpan Elapsed { get { return active.Elapsed; } }
        public bool Paused { get; private set; }

        public ScreenRecorder(Rectangle screenRect, string path)
        {
            // H.264 needs even dimensions; very large areas are scaled down to 4K.
            rect = new Rectangle(screenRect.X, screenRect.Y, screenRect.Width & ~1, screenRect.Height & ~1);
            this.path = path;
            double scale = Math.Min(1.0, Math.Min(3840.0 / rect.Width, 2160.0 / rect.Height));
            outSize = new Size(Math.Max(2, (int)(rect.Width * scale) & ~1), Math.Max(2, (int)(rect.Height * scale) & ~1));
        }

        public void Start()
        {
            thread = new Thread(Run) { IsBackground = true, Name = "MiniSnap recorder" };
            thread.SetApartmentState(ApartmentState.MTA);
            thread.Start();
        }

        public void Pause() { Paused = true; active.Stop(); }
        public void Resume() { Paused = false; active.Start(); }
        public void Stop() { stopRequested = true; }

        void Run()
        {
            Exception error = null;
            bool started = false;
            try
            {
                MF.MFStartup(0x00020070, 1);
                started = true;
                Mp4Writer writer;
                try { writer = new Mp4Writer(path, outSize.Width, outSize.Height, Fps, true); }
                catch (COMException) { writer = new Mp4Writer(path, outSize.Width, outSize.Height, Fps, false); }
                using (writer)
                using (var capture = new Bitmap(rect.Width, rect.Height, PixelFormat.Format32bppRgb))
                using (var scaled = outSize != rect.Size ? new Bitmap(outSize.Width, outSize.Height, PixelFormat.Format32bppRgb) : null)
                {
                    long frameTicks = TimeSpan.TicksPerSecond / Fps;
                    long last = -frameTicks, next = 0;
                    active.Start();
                    while (!stopRequested)
                    {
                        if (Paused) { Thread.Sleep(20); continue; }
                        long now = active.Elapsed.Ticks;
                        if (now < next)
                        {
                            Thread.Sleep((int)Math.Max(1, (next - now) / TimeSpan.TicksPerMillisecond));
                            continue;
                        }
                        using (var g = Graphics.FromImage(capture))
                        {
                            g.CopyFromScreen(rect.Location, Point.Empty, rect.Size, CopyPixelOperation.SourceCopy);
                            CursorPainter.Draw(g, rect.Location);
                        }
                        Bitmap frame = capture;
                        if (scaled != null)
                        {
                            using (var g = Graphics.FromImage(scaled))
                            {
                                g.InterpolationMode = InterpolationMode.HighQualityBilinear;
                                g.DrawImage(capture, new Rectangle(Point.Empty, outSize));
                            }
                            frame = scaled;
                        }
                        long t = Math.Max(last + frameTicks, now / frameTicks * frameTicks);
                        writer.Write(frame, t, frameTicks);
                        last = t;
                        next = t + frameTicks;
                    }
                    active.Stop();
                }
            }
            catch (Exception ex) { error = ex; }
            finally
            {
                if (started) { try { MF.MFShutdown(); } catch (COMException) { } }
            }
            var handler = Finished;
            if (handler != null) handler(error);
        }
    }

    static class CursorPainter
    {
        [StructLayout(LayoutKind.Sequential)]
        struct CURSORINFO { public int cbSize, flags; public IntPtr hCursor; public Point pt; }

        [StructLayout(LayoutKind.Sequential)]
        struct ICONINFO { public bool fIcon; public int xHotspot, yHotspot; public IntPtr hbmMask, hbmColor; }

        [DllImport("user32.dll")] static extern bool GetCursorInfo(ref CURSORINFO info);
        [DllImport("user32.dll")] static extern bool GetIconInfo(IntPtr hIcon, out ICONINFO info);
        [DllImport("user32.dll")] static extern bool DrawIconEx(IntPtr hdc, int x, int y, IntPtr hIcon, int cx, int cy, int step, IntPtr brush, int flags);
        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);

        static IntPtr lastCursor;
        static Point lastHotspot;

        public static void Draw(Graphics g, Point origin)
        {
            var ci = new CURSORINFO { cbSize = Marshal.SizeOf(typeof(CURSORINFO)) };
            if (!GetCursorInfo(ref ci) || (ci.flags & 1) == 0 || ci.hCursor == IntPtr.Zero) return;
            if (ci.hCursor != lastCursor)
            {
                ICONINFO ii;
                if (!GetIconInfo(ci.hCursor, out ii)) return;
                if (ii.hbmMask != IntPtr.Zero) DeleteObject(ii.hbmMask);
                if (ii.hbmColor != IntPtr.Zero) DeleteObject(ii.hbmColor);
                lastCursor = ci.hCursor;
                lastHotspot = new Point(ii.xHotspot, ii.yHotspot);
            }
            IntPtr hdc = g.GetHdc();
            try { DrawIconEx(hdc, ci.pt.X - origin.X - lastHotspot.X, ci.pt.Y - origin.Y - lastHotspot.Y, ci.hCursor, 0, 0, 0, IntPtr.Zero, 3); }
            finally { g.ReleaseHdc(hdc); }
        }
    }

    // Red outline drawn just outside the recorded area; click-through.
    class RegionFrame : Form
    {
        public RegionFrame(Rectangle area)
        {
            const int t = 3;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.FromArgb(235, 40, 40);
            Opacity = 0.9;
            Bounds = Rectangle.Inflate(area, t, t);
            var region = new Region(new Rectangle(0, 0, Width, Height));
            region.Exclude(new Rectangle(t, t, area.Width, area.Height));
            Region = region;
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x20 | 0x80000 | 0x08000000 | 0x80; // TRANSPARENT | LAYERED | NOACTIVATE | TOOLWINDOW
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            NativeMethods.ExcludeFromCapture(Handle);
        }
    }

    // Countdown, timer, pause and stop controls for a recording.
    class RecorderBar : FloatingBar
    {
        readonly Rectangle area;
        readonly Action<string, Exception> onDone;
        readonly Label timeLabel;
        readonly Button pauseBtn, stopBtn;
        readonly System.Windows.Forms.Timer tick = new System.Windows.Forms.Timer { Interval = 250 };
        RegionFrame frame;
        ScreenRecorder recorder;
        int countdown = 3;
        bool stopping;

        public RecorderBar(Rectangle area, Action<string, Exception> onDone)
        {
            this.area = area;
            this.onDone = onDone;
            var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = false, BackColor = BackColor };
            timeLabel = new Label
            {
                AutoSize = true,
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 11f, FontStyle.Bold),
                Margin = new Padding((int)(8 * ui), (int)(8 * ui), (int)(10 * ui), 0),
                Text = L.T("Bắt đầu sau 3..."),
            };
            pauseBtn = MakeButton(L.T("Tạm dừng"), IconKind.Pause);
            pauseBtn.Enabled = false;
            pauseBtn.Click += (s, e) => TogglePause();
            stopBtn = MakeButton(L.T("Dừng"), IconKind.Stop);
            stopBtn.Click += (s, e) => StopRecording();
            flow.Controls.Add(timeLabel);
            flow.Controls.Add(pauseBtn);
            flow.Controls.Add(stopBtn);
            Controls.Add(flow);
            AutoSize = true;
            AutoSizeMode = AutoSizeMode.GrowAndShrink;
            tick.Tick += (s, e) => OnTick();
        }

        public bool IsRecording { get { return recorder != null && !stopping; } }

        protected override void OnShown(EventArgs e)
        {
            base.OnShown(e);
            PlaceNear(area);
            frame = new RegionFrame(area);
            frame.Show();
            tick.Interval = 1000;
            tick.Start();
        }

        void OnTick()
        {
            if (recorder == null)
            {
                countdown--;
                if (countdown > 0) { timeLabel.Text = L.T("Bắt đầu sau ") + countdown + "..."; return; }
                recorder = new ScreenRecorder(area, Library.NewVideoPath());
                recorder.Finished += ex => BeginInvoke(new Action(() => Done(ex)));
                recorder.Start();
                pauseBtn.Enabled = true;
                tick.Interval = 250;
            }
            var t = recorder.Elapsed;
            timeLabel.Text = (recorder.Paused ? L.T("⏸ ") : L.T("● ")) + ((int)t.TotalMinutes).ToString("00") + ":" + t.Seconds.ToString("00");
            timeLabel.ForeColor = recorder.Paused ? Color.Gold : Color.FromArgb(255, 90, 90);
        }

        void TogglePause()
        {
            if (recorder == null) return;
            if (recorder.Paused) { recorder.Resume(); pauseBtn.Text = L.T("Tạm dừng"); pauseBtn.Image = Icons.Draw(IconKind.Pause, (int)(16 * ui), Color.FromArgb(30, 30, 30), Color.FromArgb(240, 240, 242)); }
            else { recorder.Pause(); pauseBtn.Text = L.T("Tiếp tục"); pauseBtn.Image = Icons.Draw(IconKind.Record, (int)(16 * ui), Color.FromArgb(30, 30, 30), Color.FromArgb(240, 240, 242)); }
            OnTick();
        }

        public void StopRecording()
        {
            if (stopping) return;
            stopping = true;
            tick.Stop();
            if (recorder == null) { Done(null); return; }
            timeLabel.Text = L.T("Đang lưu video...");
            pauseBtn.Enabled = stopBtn.Enabled = false;
            if (recorder.Paused) recorder.Resume();
            recorder.Stop();
        }

        void Done(Exception error)
        {
            tick.Stop();
            if (frame != null) frame.Close();
            Close();
            onDone(recorder != null ? recorder.Path : null, error);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) tick.Dispose();
            base.Dispose(disposing);
        }
    }
}
