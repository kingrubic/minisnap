using System;
using System.Collections.Generic;
using System.Drawing;
using System.Linq;
using System.Windows.Forms;
using Microsoft.Win32;

namespace MiniSnap
{
    enum HotkeyAction { CaptureRegion, CaptureRegionAlt, CaptureFullScreen, CaptureDelayed, ScrollCapture, RecordVideo, Ocr, Library }

    // A global shortcut: Ctrl/Alt/Shift modifiers (RegisterHotKey MOD_* bits) plus one key.
    class Hotkey : IEquatable<Hotkey>
    {
        public static readonly Hotkey None = new Hotkey(0, Keys.None);

        public readonly uint Mods;
        public readonly Keys Key;

        public Hotkey(uint mods, Keys key)
        {
            Mods = mods & (NativeMethods.MOD_CONTROL | NativeMethods.MOD_ALT | NativeMethods.MOD_SHIFT);
            Key = key;
        }

        public bool IsNone { get { return Key == Keys.None; } }

        public static string KeyName(Keys k)
        {
            switch (k)
            {
                case Keys.PrintScreen: return "PrtScn";
                case Keys.Return: return "Enter";
                case Keys.Escape: return "Esc";
                case Keys.Back: return "Backspace";
                case Keys.Prior: return "PageUp";
                case Keys.Next: return "PageDown";
                case Keys.Oemplus: return "=";
                case Keys.OemMinus: return "-";
                case Keys.Oemcomma: return ",";
                case Keys.OemPeriod: return ".";
                case Keys.OemQuestion: return "/";
                case Keys.OemSemicolon: return ";";
                case Keys.OemQuotes: return "'";
                case Keys.OemOpenBrackets: return "[";
                case Keys.OemCloseBrackets: return "]";
                case Keys.OemPipe: return "\\";
                case Keys.Oemtilde: return "`";
                case Keys.Add: return "Num +";
                case Keys.Subtract: return "Num -";
                case Keys.Multiply: return "Num *";
                case Keys.Divide: return "Num /";
                case Keys.Scroll: return "ScrollLock";
            }
            if (k >= Keys.D0 && k <= Keys.D9) return ((int)(k - Keys.D0)).ToString();
            if (k >= Keys.NumPad0 && k <= Keys.NumPad9) return "Num " + (int)(k - Keys.NumPad0);
            return k.ToString();
        }

        public override string ToString()
        {
            if (IsNone) return L.T("(không dùng)");
            var parts = new List<string>();
            if ((Mods & NativeMethods.MOD_CONTROL) != 0) parts.Add("Ctrl");
            if ((Mods & NativeMethods.MOD_ALT) != 0) parts.Add("Alt");
            if ((Mods & NativeMethods.MOD_SHIFT) != 0) parts.Add("Shift");
            parts.Add(KeyName(Key));
            return string.Join(" + ", parts);
        }

        // Compact form for menus, e.g. "Ctrl+Alt+R".
        public string ShortText { get { return IsNone ? null : ToString().Replace(" + ", "+"); } }

        public string Serialize() { return Mods + ":" + (int)Key; }

        public static Hotkey Parse(string s)
        {
            if (string.IsNullOrEmpty(s)) return null;
            var p = s.Split(':');
            uint mods;
            int key;
            if (p.Length != 2 || !uint.TryParse(p[0], out mods) || !int.TryParse(p[1], out key)) return null;
            return new Hotkey(mods, (Keys)key);
        }

        public bool Equals(Hotkey other) { return other != null && other.Mods == Mods && other.Key == Key; }
        public override bool Equals(object obj) { return Equals(obj as Hotkey); }
        public override int GetHashCode() { return (int)Mods * 397 ^ (int)Key; }
    }

    static class HotkeySettings
    {
        const string RegPath = @"Software\MiniSnap\Hotkeys";

        public static readonly HotkeyAction[] All = (HotkeyAction[])Enum.GetValues(typeof(HotkeyAction));

        public static Dictionary<HotkeyAction, Hotkey> Defaults()
        {
            uint ctrl = NativeMethods.MOD_CONTROL, alt = NativeMethods.MOD_ALT, shift = NativeMethods.MOD_SHIFT;
            return new Dictionary<HotkeyAction, Hotkey>
            {
                { HotkeyAction.CaptureRegion, new Hotkey(0, Keys.PrintScreen) },
                { HotkeyAction.CaptureRegionAlt, new Hotkey(ctrl | shift, Keys.X) },
                { HotkeyAction.CaptureFullScreen, new Hotkey(ctrl, Keys.PrintScreen) },
                { HotkeyAction.CaptureDelayed, new Hotkey(shift, Keys.PrintScreen) },
                { HotkeyAction.ScrollCapture, new Hotkey(ctrl | alt, Keys.S) },
                { HotkeyAction.RecordVideo, new Hotkey(ctrl | alt, Keys.R) },
                { HotkeyAction.Ocr, new Hotkey(ctrl | alt, Keys.O) },
                { HotkeyAction.Library, new Hotkey(ctrl | alt, Keys.L) },
            };
        }

        public static Dictionary<HotkeyAction, Hotkey> Load()
        {
            var result = Defaults();
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(RegPath))
                {
                    if (k == null) return result;
                    foreach (var a in All)
                    {
                        var h = Hotkey.Parse(k.GetValue(a.ToString()) as string);
                        if (h != null) result[a] = h;
                    }
                }
            }
            catch (Exception) { }
            return result;
        }

        public static void Save(Dictionary<HotkeyAction, Hotkey> map)
        {
            using (var k = Registry.CurrentUser.CreateSubKey(RegPath))
                foreach (var kv in map) k.SetValue(kv.Key.ToString(), kv.Value.Serialize());
        }

        public static string Label(HotkeyAction a)
        {
            switch (a)
            {
                case HotkeyAction.CaptureRegion: return L.T("Chụp vùng / cửa sổ");
                case HotkeyAction.CaptureRegionAlt: return L.T("Chụp vùng / cửa sổ (phím phụ)");
                case HotkeyAction.CaptureFullScreen: return L.T("Chụp toàn màn hình");
                case HotkeyAction.CaptureDelayed: return L.T("Chụp vùng sau 3 giây");
                case HotkeyAction.ScrollCapture: return L.T("Chụp cuộn trang dài");
                case HotkeyAction.RecordVideo: return L.T("Quay video (bắt đầu / dừng)");
                case HotkeyAction.Ocr: return L.T("Chụp và trích chữ (OCR)");
                default: return L.T("Mở thư viện ảnh & video");
            }
        }

        public static IconKind Icon(HotkeyAction a)
        {
            switch (a)
            {
                case HotkeyAction.ScrollCapture: return IconKind.Scroll;
                case HotkeyAction.RecordVideo: return IconKind.Video;
                case HotkeyAction.Ocr: return IconKind.Ocr;
                case HotkeyAction.Library: return IconKind.Library;
                default: return IconKind.Capture;
            }
        }

        // Keys that are safe as a shortcut without Ctrl/Alt/Shift (they don't type text).
        public static bool AllowedAlone(Keys k)
        {
            return k == Keys.PrintScreen || k == Keys.Pause || k == Keys.Scroll || (k >= Keys.F1 && k <= Keys.F24);
        }
    }

    // Click it, press a key combination, and it shows/stores that combination.
    class HotkeyBox : TextBox
    {
        Hotkey value = Hotkey.None;
        readonly Timer revert = new Timer { Interval = 1600 };
        readonly Color normalBack = Theme.Field, focusBack = Theme.Dark ? Color.FromArgb(64, 58, 36) : Color.FromArgb(255, 248, 225);

        public event EventHandler ValueChanged;

        public HotkeyBox()
        {
            ReadOnly = true;
            ShortcutsEnabled = false;
            BackColor = normalBack;
            ForeColor = Theme.Text;
            TextAlign = HorizontalAlignment.Center;
            Cursor = Cursors.Hand;
            revert.Tick += (s, e) => { revert.Stop(); ForeColor = Theme.Text; Text = Focused ? L.T("Nhấn tổ hợp phím...") : value.ToString(); };
        }

        public Hotkey Value
        {
            get { return value; }
            set { this.value = value ?? Hotkey.None; if (!Focused) Text = this.value.ToString(); }
        }

        void Set(Hotkey h)
        {
            value = h;
            Text = h.ToString();
            var handler = ValueChanged;
            if (handler != null) handler(this, EventArgs.Empty);
        }

        public void ClearKey() { Set(Hotkey.None); }

        protected override void OnEnter(EventArgs e)
        {
            base.OnEnter(e);
            BackColor = focusBack;
            Text = L.T("Nhấn tổ hợp phím...");
            BeginInvoke(new Action(() => { SelectionStart = 0; SelectionLength = 0; }));
        }

        protected override void OnLeave(EventArgs e)
        {
            base.OnLeave(e);
            BackColor = normalBack;
            revert.Stop();
            ForeColor = Theme.Text;
            Text = value.ToString();
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            SelectionLength = 0;
        }

        // Every key goes to the box, except plain Tab so the dialog can still be navigated.
        protected override bool IsInputKey(Keys keyData) { return keyData != Keys.Tab && keyData != (Keys.Tab | Keys.Shift); }

        static string ModText(Keys mods)
        {
            var parts = new List<string>();
            if ((mods & Keys.Control) != 0) parts.Add("Ctrl");
            if ((mods & Keys.Alt) != 0) parts.Add("Alt");
            if ((mods & Keys.Shift) != 0) parts.Add("Shift");
            return string.Join(" + ", parts);
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            e.Handled = true;
            e.SuppressKeyPress = true;
            Keys k = e.KeyCode;
            if (k == Keys.ControlKey || k == Keys.ShiftKey || k == Keys.Menu)
            {
                Text = ModText(e.Modifiers) + " + ...";
                return;
            }
            if (k == Keys.LWin || k == Keys.RWin) return;
            if (e.Modifiers == Keys.None && (k == Keys.Back || k == Keys.Delete)) { ClearKey(); return; }
            if (e.Modifiers == Keys.None && k == Keys.Escape) { Text = value.ToString(); return; }
            Commit(k, e.Modifiers);
        }

        protected override void OnKeyUp(KeyEventArgs e)
        {
            e.Handled = true;
            // Windows never sends a key-down for PrtScn, only the key-up.
            if (e.KeyCode == Keys.PrintScreen) { Commit(Keys.PrintScreen, e.Modifiers); return; }
            if (e.Modifiers == Keys.None && Text.EndsWith("...") && !revert.Enabled) Text = L.T("Nhấn tổ hợp phím...");
        }

        protected override bool ProcessDialogKey(Keys keyData)
        {
            // Keep Alt+key from triggering mnemonics while a combination is being recorded.
            if ((keyData & Keys.Alt) != 0) return true;
            return base.ProcessDialogKey(keyData);
        }

        void Commit(Keys k, Keys mods)
        {
            uint m = 0;
            if ((mods & Keys.Control) != 0) m |= NativeMethods.MOD_CONTROL;
            if ((mods & Keys.Alt) != 0) m |= NativeMethods.MOD_ALT;
            if ((mods & Keys.Shift) != 0) m |= NativeMethods.MOD_SHIFT;
            if (m == 0 && !HotkeySettings.AllowedAlone(k))
            {
                ForeColor = Theme.Danger;
                Text = L.T("Cần kèm Ctrl, Alt hoặc Shift");
                revert.Stop();
                revert.Start();
                return;
            }
            if (m == NativeMethods.MOD_SHIFT && !HotkeySettings.AllowedAlone(k))
            {
                ForeColor = Theme.Danger;
                Text = L.T("Shift + phím chữ sẽ chặn gõ chữ hoa");
                revert.Stop();
                revert.Start();
                return;
            }
            revert.Stop();
            ForeColor = Theme.Text;
            Set(new Hotkey(m, k));
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) revert.Dispose();
            base.Dispose(disposing);
        }
    }

    class HotkeySettingsForm : Form
    {
        readonly Func<Dictionary<HotkeyAction, Hotkey>, List<HotkeyAction>> apply;
        readonly Dictionary<HotkeyAction, HotkeyBox> boxes = new Dictionary<HotkeyAction, HotkeyBox>();
        readonly Dictionary<HotkeyAction, Label> statuses = new Dictionary<HotkeyAction, Label>();
        readonly Button saveBtn;
        readonly Label footerLabel;
        readonly float ui;

        int S(float v) { return (int)Math.Round(v * ui); }

        // apply: saves + registers the map, returns the actions whose key is taken by another app.
        public HotkeySettingsForm(Dictionary<HotkeyAction, Hotkey> current, Func<Dictionary<HotkeyAction, Hotkey>, List<HotkeyAction>> apply)
        {
            this.apply = apply;
            using (var g = CreateGraphics()) ui = g.DpiX / 96f;
            Text = L.T("Cài đặt phím tắt — MiniSnap");
            Icon = AppIcon.Get();
            Font = Theme.UiFont(9.5f);
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = MinimizeBox = false;
            StartPosition = FormStartPosition.CenterScreen;
            AutoSize = true;
            AutoSizeMode = AutoSizeMode.GrowAndShrink;
            TopMost = true;

            var intro = new Label
            {
                AutoSize = true,
                MaximumSize = new Size(S(620), 0),
                Text = L.T("Bấm vào ô bên phải rồi nhấn tổ hợp phím mới, ví dụ Ctrl + Shift + 1 hoặc F9.\nBackspace để bỏ phím tắt, Esc để giữ phím cũ. Phím tắt dùng được ở mọi nơi, kể cả khi đang ở app khác."),
                Margin = new Padding(0, 0, 0, S(10)),
                UseMnemonic = false,
            };

            var grid = new TableLayoutPanel { AutoSize = true, ColumnCount = 5, Margin = new Padding(0) };
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, S(220)));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, S(190)));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            grid.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, S(200)));
            var tips = new ToolTip();
            foreach (var a in HotkeySettings.All)
            {
                var action = a;
                var icon = new PictureBox { Image = Icons.Draw(HotkeySettings.Icon(a), S(20)), SizeMode = PictureBoxSizeMode.CenterImage, Size = new Size(S(24), S(28)), Margin = new Padding(0, S(3), S(6), S(3)) };
                var name = new Label { Text = HotkeySettings.Label(a), AutoSize = false, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, UseMnemonic = false };
                var box = new HotkeyBox { Value = current[a], Width = S(180), Margin = new Padding(0, S(4), S(4), S(4)) };
                box.ValueChanged += (s, e) => RefreshStatus();
                var clear = new FluentButton { Text = "✕", AutoSize = false, MinimumSize = new Size(S(30), box.Height + S(2)), Size = new Size(S(30), box.Height + S(2)), Padding = new Padding(0), Margin = new Padding(0, S(3), S(10), S(3)), TabStop = false };
                clear.Click += (s, e) => { boxes[action].ClearKey(); };
                tips.SetToolTip(clear, L.T("Bỏ phím tắt này"));
                var status = new Label { AutoSize = false, Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleLeft, UseMnemonic = false };
                grid.Controls.Add(icon);
                grid.Controls.Add(name);
                grid.Controls.Add(box);
                grid.Controls.Add(clear);
                grid.Controls.Add(status);
                boxes[a] = box;
                statuses[a] = status;
            }

            var buttons = new TableLayoutPanel { AutoSize = true, ColumnCount = 4, Dock = DockStyle.Fill, Margin = new Padding(0, S(14), 0, 0) };
            buttons.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            buttons.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            buttons.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            buttons.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            var resetBtn = new FluentButton { Text = L.T("Khôi phục mặc định"), MinimumSize = new Size(0, S(32)) };
            resetBtn.Click += (s, e) =>
            {
                var d = HotkeySettings.Defaults();
                foreach (var kv in boxes) kv.Value.Value = d[kv.Key];
                RefreshStatus();
            };
            footerLabel = new Label { AutoSize = true, Anchor = AnchorStyles.Left, ForeColor = Theme.TextSecondary, Margin = new Padding(S(10), S(8), S(10), 0), UseMnemonic = false };
            saveBtn = new FluentButton { Text = L.T("Lưu"), Primary = true, MinimumSize = new Size(S(96), S(32)) };
            saveBtn.Click += (s, e) => SaveAndApply();
            var closeBtn = new FluentButton { Text = L.T("Đóng"), MinimumSize = new Size(S(96), S(32)) };
            closeBtn.Click += (s, e) => Close();
            // Start on the Close button so a stray key press can't overwrite the first shortcut.
            Shown += (s, e) => closeBtn.Focus();
            buttons.Controls.Add(resetBtn);
            buttons.Controls.Add(footerLabel);
            buttons.Controls.Add(saveBtn);
            buttons.Controls.Add(closeBtn);
            CancelButton = closeBtn;

            var root = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.TopDown, WrapContents = false, Padding = new Padding(S(16), S(12), S(16), S(14)) };
            root.Controls.Add(intro);
            root.Controls.Add(grid);
            root.Controls.Add(buttons);
            buttons.Width = grid.PreferredSize.Width;
            Controls.Add(root);
            Theme.Apply(this);
            RefreshStatus();
        }

        // Used by --selftest: focus one box and type real keystrokes into it.
        public void TestPress(HotkeyAction a, string sendKeys)
        {
            boxes[a].Focus();
            SendKeys.SendWait(sendKeys);
            Application.DoEvents();
        }

        public Dictionary<HotkeyAction, Hotkey> Values
        {
            get { return boxes.ToDictionary(kv => kv.Key, kv => kv.Value.Value); }
        }

        // Marks duplicates and enables Save only when every shortcut is unique.
        bool RefreshStatus()
        {
            bool ok = true;
            var values = Values;
            foreach (var a in HotkeySettings.All)
            {
                var h = values[a];
                var clash = h.IsNone ? null : values.Where(kv => kv.Key != a && kv.Value.Equals(h)).Select(kv => (HotkeyAction?)kv.Key).FirstOrDefault();
                var st = statuses[a];
                if (clash.HasValue)
                {
                    ok = false;
                    st.ForeColor = Theme.Danger;
                    st.Text = L.T("⚠ Trùng: ") + HotkeySettings.Label(clash.Value);
                }
                else
                {
                    st.ForeColor = Theme.TextSecondary;
                    st.Text = h.IsNone ? L.T("Chỉ dùng từ menu") : "";
                }
            }
            saveBtn.Enabled = ok;
            footerLabel.Text = ok ? "" : L.T("Mỗi phím tắt chỉ được gán cho một chức năng.");
            footerLabel.ForeColor = Theme.Danger;
            return ok;
        }

        void SaveAndApply()
        {
            if (!RefreshStatus()) return;
            var failed = apply(Values);
            foreach (var a in HotkeySettings.All)
            {
                var st = statuses[a];
                if (failed.Contains(a))
                {
                    st.ForeColor = Theme.Danger;
                    st.Text = L.T("⚠ App khác đang dùng phím này");
                }
                else if (!boxes[a].Value.IsNone)
                {
                    st.ForeColor = Theme.Success;
                    st.Text = L.T("✓ Đã lưu");
                }
            }
            if (failed.Count == 0)
            {
                footerLabel.ForeColor = Theme.Success;
                footerLabel.Text = L.T("Đã lưu và áp dụng.");
                DialogResult = DialogResult.OK;
                Close();
            }
            else
            {
                footerLabel.ForeColor = Theme.Danger;
                footerLabel.Text = L.T("Đã lưu, nhưng ") + failed.Count + L.T(" phím đang bị app khác chiếm — hãy chọn phím khác.");
            }
        }
    }
}
