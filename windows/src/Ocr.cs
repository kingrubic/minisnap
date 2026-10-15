using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Windows.Foundation;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage.Streams;

namespace MiniSnap
{
    // Text recognition with the OCR engine built into Windows 10/11 (no download, works offline).
    static class OcrService
    {
        public class Result
        {
            public string Text;
            public string Language;
            public bool HasVietnamese;
        }

        static T Wait<T>(IAsyncOperation<T> op)
        {
            while (op.Status == AsyncStatus.Started) Thread.Sleep(5);
            if (op.Status != AsyncStatus.Completed) throw new InvalidOperationException(L.T("OCR thất bại: ") + op.ErrorCode);
            return op.GetResults();
        }

        public static bool HasVietnamese()
        {
            return OcrEngine.AvailableRecognizerLanguages.Any(l => l.LanguageTag.StartsWith("vi", StringComparison.OrdinalIgnoreCase));
        }

        static OcrEngine CreateEngine()
        {
            var vi = OcrEngine.AvailableRecognizerLanguages.FirstOrDefault(l => l.LanguageTag.StartsWith("vi", StringComparison.OrdinalIgnoreCase));
            OcrEngine engine = vi != null ? OcrEngine.TryCreateFromLanguage(vi) : OcrEngine.TryCreateFromUserProfileLanguages();
            if (engine == null)
            {
                var first = OcrEngine.AvailableRecognizerLanguages.FirstOrDefault();
                if (first != null) engine = OcrEngine.TryCreateFromLanguage(first);
            }
            if (engine == null) throw new InvalidOperationException(L.T("Windows chưa cài gói nhận dạng chữ (OCR) cho ngôn ngữ nào."));
            return engine;
        }

        public static Result Recognize(Bitmap source)
        {
            var engine = CreateEngine();
            using (var prepared = Prepare(source, (int)OcrEngine.MaxImageDimension))
            {
                var bmpData = prepared.LockBits(new Rectangle(0, 0, prepared.Width, prepared.Height), ImageLockMode.ReadOnly, PixelFormat.Format32bppPArgb);
                var bytes = new byte[bmpData.Stride * prepared.Height];
                Marshal.Copy(bmpData.Scan0, bytes, 0, bytes.Length);
                prepared.UnlockBits(bmpData);
                var writer = new DataWriter();
                writer.WriteBytes(bytes);
                var sb = SoftwareBitmap.CreateCopyFromBuffer(writer.DetachBuffer(), BitmapPixelFormat.Bgra8, prepared.Width, prepared.Height, BitmapAlphaMode.Premultiplied);
                var ocr = Wait(engine.RecognizeAsync(sb));
                var text = new StringBuilder();
                foreach (var line in ocr.Lines) text.AppendLine(line.Text);
                return new Result
                {
                    Text = text.ToString().TrimEnd(),
                    Language = engine.RecognizerLanguage.DisplayName + " (" + engine.RecognizerLanguage.LanguageTag + ")",
                    HasVietnamese = engine.RecognizerLanguage.LanguageTag.StartsWith("vi", StringComparison.OrdinalIgnoreCase),
                };
            }
        }

        // Small screenshots are upscaled (OCR is far more accurate on larger glyphs); huge ones are shrunk to the engine limit.
        static Bitmap Prepare(Bitmap src, int maxDim)
        {
            float scale = 1f;
            int longest = Math.Max(src.Width, src.Height);
            if (longest < 1500) scale = Math.Min(3f, 1500f / longest);
            if (longest * scale > maxDim) scale = (float)maxDim / longest;
            int w = Math.Max(1, (int)(src.Width * scale)), h = Math.Max(1, (int)(src.Height * scale));
            var bmp = new Bitmap(w, h, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.White);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                g.DrawImage(src, new Rectangle(0, 0, w, h));
            }
            return bmp;
        }
    }

    class OcrForm : Form
    {
        readonly TextBox textBox;
        readonly Label infoLabel;
        readonly Button copyBtn;

        public OcrForm(Bitmap image)
        {
            float ui;
            using (var g = CreateGraphics()) ui = g.DpiX / 96f;
            Text = L.T("Trích chữ (OCR) — MiniSnap");
            Icon = AppIcon.Get();
            Font = Theme.UiFont(9.5f);
            Size = new Size((int)(640 * ui), (int)(480 * ui));
            MinimumSize = new Size((int)(380 * ui), (int)(260 * ui));
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;

            textBox = new TextBox
            {
                Multiline = true,
                ScrollBars = ScrollBars.Vertical,
                Dock = DockStyle.Fill,
                Font = Theme.UiFont(11f),
                Text = L.T("Đang nhận dạng chữ..."),
                ReadOnly = true,
                BorderStyle = BorderStyle.None,
            };
            var textHost = new Panel { Dock = DockStyle.Fill, Padding = new Padding((int)(12 * ui)), BackColor = Theme.Field };
            textHost.Controls.Add(textBox);

            var bottom = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                FlowDirection = FlowDirection.RightToLeft,
                AutoSize = true,
                Padding = new Padding((int)(8 * ui)),
            };
            var closeBtn = new FluentButton { Text = L.T("Đóng"), MinimumSize = new Size((int)(96 * ui), (int)(32 * ui)) };
            closeBtn.Click += (s, e) => Close();
            copyBtn = new FluentButton { Text = L.T("Sao chép chữ"), Primary = true, MinimumSize = new Size((int)(120 * ui), (int)(32 * ui)), Enabled = false };
            copyBtn.Click += (s, e) => CopyText();
            infoLabel = new Label { AutoSize = true, ForeColor = Theme.TextSecondary, Margin = new Padding(0, (int)(8 * ui), (int)(16 * ui), 0), MaximumSize = new Size((int)(380 * ui), 0) };
            bottom.Controls.Add(closeBtn);
            bottom.Controls.Add(copyBtn);
            bottom.Controls.Add(infoLabel);
            CancelButton = closeBtn;

            Controls.Add(textHost);
            Controls.Add(bottom);
            Theme.Apply(this);
            textBox.BackColor = Theme.Field;
            textBox.ForeColor = Theme.Text;

            var copy = new Bitmap(image);
            var t = new Thread(() =>
            {
                OcrService.Result result = null;
                string error = null;
                try { result = OcrService.Recognize(copy); }
                catch (Exception ex) { error = ex.Message; }
                finally { copy.Dispose(); }
                try { BeginInvoke(new Action(() => ShowResult(result, error))); }
                catch (InvalidOperationException) { }
            });
            t.IsBackground = true;
            Load += (s, e) => t.Start();
        }

        void ShowResult(OcrService.Result result, string error)
        {
            if (error != null)
            {
                textBox.Text = L.T("Không nhận dạng được chữ: ") + error;
                return;
            }
            textBox.ReadOnly = false;
            textBox.Text = result.Text.Length > 0 ? result.Text.Replace("\n", "\r\n").Replace("\r\r\n", "\r\n") : "";
            if (result.Text.Length == 0) textBox.Text = L.T("(Không tìm thấy chữ nào trong ảnh)");
            copyBtn.Enabled = result.Text.Length > 0;
            infoLabel.Text = L.T("Ngôn ngữ: ") + result.Language;
            if (!result.HasVietnamese)
                infoLabel.Text += L.T("\nMuốn đọc tiếng Việt có dấu: Settings → Time & language → Language & region → Add a language → Tiếng Việt.");
            if (result.Text.Length > 0)
            {
                CopyText();
                textBox.SelectionStart = 0;
                textBox.SelectionLength = 0;
            }
        }

        void CopyText()
        {
            if (textBox.Text.Length == 0) return;
            try
            {
                Clipboard.SetText(textBox.Text);
                copyBtn.Text = L.T("✓ Đã sao chép");
            }
            catch (ExternalException) { }
        }
    }
}
