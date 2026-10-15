using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.Linq;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;

namespace MiniSnap
{
    // Windows 11 look for WinForms: follows the system light/dark setting and accent colour,
    // Mica title bars, rounded corners, Segoe UI Variable text and Segoe Fluent Icons glyphs.
    static class Theme
    {
        public static bool Dark { get; private set; }
        public static Color Accent { get; private set; }
        public static Color OnAccent { get; private set; }
        public static Color Window { get; private set; }
        public static Color Surface { get; private set; }
        public static Color Canvas { get; private set; }
        public static Color Field { get; private set; }
        public static Color FieldFocus { get; private set; }
        public static Color Text { get; private set; }
        public static Color TextSecondary { get; private set; }
        public static Color TextDisabled { get; private set; }
        public static Color Border { get; private set; }
        public static Color Hover { get; private set; }
        public static Color Pressed { get; private set; }
        public static Color Danger { get; private set; }
        public static Color Success { get; private set; }

        static string uiFamily, iconFamily;

        static Theme() { Load(); }

        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] static extern int SetWindowTheme(IntPtr hwnd, string app, string idList);

        // MINISNAP_THEME=dark|light overrides the system setting (used by --selftest).
        public static void Load()
        {
            string over = Environment.GetEnvironmentVariable("MINISNAP_THEME");
            if (!string.IsNullOrEmpty(over)) Dark = over == "dark";
            else
            {
                try
                {
                    using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"))
                        Dark = k != null && k.GetValue("AppsUseLightTheme") is int && (int)k.GetValue("AppsUseLightTheme") == 0;
                }
                catch (Exception) { Dark = false; }
            }

            Color accent = Dark ? Color.FromArgb(76, 194, 255) : Color.FromArgb(0, 95, 184);
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\DWM"))
                {
                    object v = k == null ? null : k.GetValue("AccentColor");
                    if (v is int)
                    {
                        int abgr = (int)v;
                        var sys = Color.FromArgb(abgr & 0xFF, (abgr >> 8) & 0xFF, (abgr >> 16) & 0xFF);
                        // Dark mode uses a lighter tint of the accent, light mode a deeper one (as Windows 11 does).
                        accent = Dark ? Blend(sys, Color.White, 0.35f) : Blend(sys, Color.Black, 0.15f);
                    }
                }
            }
            catch (Exception) { }
            Accent = accent;
            OnAccent = Dark ? Color.Black : Color.White;

            if (Dark)
            {
                Window = Color.FromArgb(32, 32, 32);
                Surface = Color.FromArgb(43, 43, 43);
                Canvas = Color.FromArgb(24, 24, 24);
                Field = Color.FromArgb(45, 45, 45);
                FieldFocus = Color.FromArgb(31, 31, 31);
                Text = Color.FromArgb(255, 255, 255);
                TextSecondary = Color.FromArgb(200, 200, 200);
                TextDisabled = Color.FromArgb(120, 120, 120);
                Border = Color.FromArgb(62, 62, 62);
                Hover = Color.FromArgb(58, 58, 58);
                Pressed = Color.FromArgb(50, 50, 50);
                Danger = Color.FromArgb(255, 153, 164);
                Success = Color.FromArgb(108, 203, 95);
            }
            else
            {
                Window = Color.FromArgb(243, 243, 243);
                Surface = Color.FromArgb(251, 251, 251);
                Canvas = Color.FromArgb(229, 229, 229);
                Field = Color.FromArgb(255, 255, 255);
                FieldFocus = Color.FromArgb(255, 255, 255);
                Text = Color.FromArgb(27, 27, 27);
                TextSecondary = Color.FromArgb(96, 96, 96);
                TextDisabled = Color.FromArgb(160, 160, 160);
                Border = Color.FromArgb(229, 229, 229);
                Hover = Color.FromArgb(234, 234, 234);
                Pressed = Color.FromArgb(224, 224, 224);
                Danger = Color.FromArgb(196, 43, 28);
                Success = Color.FromArgb(15, 123, 15);
            }

            var names = new InstalledFontCollection().Families.Select(f => f.Name).ToList();
            uiFamily = names.Contains("Segoe UI Variable Text") ? "Segoe UI Variable Text" : "Segoe UI";
            iconFamily = names.Contains("Segoe Fluent Icons") ? "Segoe Fluent Icons" : names.Contains("Segoe MDL2 Assets") ? "Segoe MDL2 Assets" : null;
        }

        public static Color Blend(Color a, Color b, float t)
        {
            return Color.FromArgb((int)(a.R + (b.R - a.R) * t), (int)(a.G + (b.G - a.G) * t), (int)(a.B + (b.B - a.B) * t));
        }

        public static Font UiFont(float size, FontStyle style = FontStyle.Regular)
        {
            string fam = uiFamily;
            if ((style & FontStyle.Bold) != 0 && uiFamily == "Segoe UI Variable Text") { fam = "Segoe UI Variable Text Semibold"; style &= ~FontStyle.Bold; }
            try { return new Font(fam, size, style); }
            catch (ArgumentException) { return new Font("Segoe UI", size, style); }
        }

        public static bool HasIconFont { get { return iconFamily != null; } }

        // A Segoe Fluent Icons glyph rendered to a transparent bitmap.
        public static Bitmap Glyph(char code, int size, Color color)
        {
            var bmp = new Bitmap(size, size, PixelFormat.Format32bppPArgb);
            using (var g = Graphics.FromImage(bmp))
            using (var font = new Font(iconFamily, size * 0.8f, FontStyle.Regular, GraphicsUnit.Pixel))
            using (var br = new SolidBrush(color))
            using (var sf = new StringFormat(StringFormat.GenericTypographic) { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
            {
                g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
                g.DrawString(code.ToString(), font, br, new RectangleF(0, 0, size, size), sf);
            }
            return bmp;
        }

        // ---------- Window chrome ----------

        const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20, DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWA_SYSTEMBACKDROP_TYPE = 38;

        static void Dwm(IntPtr hwnd, int attr, int value)
        {
            try { DwmSetWindowAttribute(hwnd, attr, ref value, 4); }
            catch (Exception) { }
        }

        public static void RoundCorners(IntPtr hwnd, bool small = false) { Dwm(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, small ? 3 : 2); }

        public static void ThemeControl(IntPtr hwnd, bool explorerStyle)
        {
            try { SetWindowTheme(hwnd, Dark ? (explorerStyle ? "DarkMode_Explorer" : "DarkMode_CFD") : (explorerStyle ? "Explorer" : null), null); }
            catch (Exception) { }
        }

        // Title bar (dark/light + Mica), colours, fonts and renderers for a whole form.
        public static void Apply(Form f)
        {
            f.BackColor = Window;
            f.ForeColor = Text;
            if (f.IsHandleCreated) Chrome(f);
            else f.HandleCreated += (s, e) => Chrome(f);
            StyleTree(f.Controls);
        }

        static void Chrome(Form f)
        {
            Dwm(f.Handle, DWMWA_USE_IMMERSIVE_DARK_MODE, Dark ? 1 : 0);
            Dwm(f.Handle, DWMWA_SYSTEMBACKDROP_TYPE, 2);
            RoundCorners(f.Handle);
        }

        public static void StyleTree(Control.ControlCollection controls)
        {
            foreach (Control c in controls)
            {
                if (c.Tag as string == "keep-style") continue;
                var ts = c as ToolStrip;
                if (ts != null) { StyleStrip(ts); continue; }
                var tb = c as TextBox;
                if (tb != null && !tb.ReadOnly || c is RichTextBox) { c.BackColor = Field; c.ForeColor = Text; }
                var cb = c as ComboBox;
                if (cb != null) { cb.FlatStyle = FlatStyle.Flat; cb.BackColor = Field; cb.ForeColor = Text; HookTheme(cb, false); }
                var lv = c as ListView;
                if (lv != null) { lv.BackColor = Window; lv.ForeColor = Text; HookItemsView(lv); }
                var chk = c as CheckBox;
                if (chk != null) chk.ForeColor = Text;
                var sp = c as ScrollableControl;
                if (sp != null && sp.AutoScroll) HookTheme(sp, true);
                if (c.HasChildren) StyleTree(c.Controls);
            }
        }

        // Explorer's own list theme: dark group headers and rounded selection on Windows 11.
        static void HookItemsView(Control c)
        {
            Action apply = () => { try { SetWindowTheme(c.Handle, Dark ? "DarkMode_ItemsView" : "ItemsView", null); } catch (Exception) { } };
            if (c.IsHandleCreated) apply(); else c.HandleCreated += (s, e) => apply();
        }

        static void HookTheme(Control c, bool explorer)
        {
            if (c.IsHandleCreated) ThemeControl(c.Handle, explorer);
            else c.HandleCreated += (s, e) => ThemeControl(c.Handle, explorer);
        }

        public static void StyleStrip(ToolStrip ts)
        {
            ts.Renderer = new FluentRenderer();
            ts.BackColor = ts is StatusStrip ? Window : Surface;
            ts.ForeColor = Text;
            ts.Font = UiFont(9f);
            foreach (ToolStripItem item in ts.Items)
            {
                item.ForeColor = Text;
                var host = item as ToolStripComboBox;
                if (host != null) { host.ComboBox.FlatStyle = FlatStyle.Flat; host.BackColor = Field; host.ForeColor = Text; HookTheme(host.ComboBox, false); }
                var tbox = item as ToolStripTextBox;
                if (tbox != null) { tbox.BackColor = Field; tbox.ForeColor = Text; tbox.BorderStyle = BorderStyle.FixedSingle; }
            }
            var dd = ts as ToolStripDropDown;
            if (dd != null)
            {
                if (dd.IsHandleCreated) RoundCorners(dd.Handle, true);
                else dd.HandleCreated += (s, e) => RoundCorners(dd.Handle, true);
            }
        }

        public static GraphicsPath Rounded(RectangleF r, float radius) { return Icons.RoundedRect(r, radius); }
    }

    // Flat Windows 11 style for toolbars, status bars and menus.
    class FluentRenderer : ToolStripRenderer
    {
        protected override void Initialize(ToolStrip toolStrip)
        {
            base.Initialize(toolStrip);
            toolStrip.Padding = new Padding(Math.Max(toolStrip.Padding.Left, 4), toolStrip.Padding.Top, toolStrip.Padding.Right, toolStrip.Padding.Bottom);
        }

        protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
        {
            using (var br = new SolidBrush(e.ToolStrip.BackColor)) e.Graphics.FillRectangle(br, e.AffectedBounds);
        }

        protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
        {
            var r = e.ToolStrip.ClientRectangle;
            using (var pen = new Pen(Theme.Border))
            {
                if (e.ToolStrip is ToolStripDropDown) e.Graphics.DrawRectangle(pen, 0, 0, r.Width - 1, r.Height - 1);
                else if (e.ToolStrip is StatusStrip) e.Graphics.DrawLine(pen, 0, 0, r.Width, 0);
                else e.Graphics.DrawLine(pen, 0, r.Height - 1, r.Width, r.Height - 1);
            }
        }

        static void FillRounded(Graphics g, Rectangle r, Color c, float radius)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (var path = Theme.Rounded(r, radius))
            using (var br = new SolidBrush(c))
                g.FillPath(br, path);
            g.SmoothingMode = SmoothingMode.None;
        }

        protected override void OnRenderButtonBackground(ToolStripItemRenderEventArgs e)
        {
            var b = e.Item as ToolStripButton;
            var r = new Rectangle(1, 1, e.Item.Width - 2, e.Item.Height - 2);
            bool on = b != null && b.Checked;
            if (e.Item.Pressed) FillRounded(e.Graphics, r, Theme.Pressed, 5);
            else if (e.Item.Selected && e.Item.Enabled) FillRounded(e.Graphics, r, Theme.Hover, 5);
            else if (on) FillRounded(e.Graphics, r, Theme.Dark ? Color.FromArgb(50, 50, 50) : Color.FromArgb(237, 237, 237), 5);
            if (on)
            {
                // Windows 11 "selected tool" pill under the icon.
                int w = Math.Min(16, r.Width / 3);
                FillRounded(e.Graphics, new Rectangle(r.X + (r.Width - w) / 2, r.Bottom - 3, w, 3), Theme.Accent, 1.5f);
            }
        }

        protected override void OnRenderDropDownButtonBackground(ToolStripItemRenderEventArgs e) { OnRenderButtonBackground(e); }

        protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
        {
            if (!e.Item.Selected || !e.Item.Enabled) return;
            var r = new Rectangle(4, 1, e.Item.Width - 8, e.Item.Height - 2);
            FillRounded(e.Graphics, r, Theme.Hover, 4);
        }

        protected override void OnRenderImageMargin(ToolStripRenderEventArgs e) { }

        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = e.Item.Enabled ? Theme.Text : Theme.TextDisabled;
            base.OnRenderItemText(e);
        }

        protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e)
        {
            var r = e.ImageRectangle;
            if (Theme.HasIconFont)
                using (var glyph = Theme.Glyph('', Math.Max(12, r.Height), Theme.Accent))
                    e.Graphics.DrawImage(glyph, r.X + (r.Width - glyph.Width) / 2, r.Y + (r.Height - glyph.Height) / 2);
            else base.OnRenderItemCheck(e);
        }

        protected override void OnRenderArrow(ToolStripArrowRenderEventArgs e)
        {
            e.ArrowColor = Theme.TextSecondary;
            base.OnRenderArrow(e);
        }

        protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
        {
            var r = e.Item.ContentRectangle;
            using (var pen = new Pen(Theme.Border))
            {
                if (e.Vertical) e.Graphics.DrawLine(pen, r.Width / 2, r.Top + 6, r.Width / 2, r.Bottom - 6);
                else e.Graphics.DrawLine(pen, r.Left + 8, r.Height / 2, r.Right - 8, r.Height / 2);
            }
        }

        protected override void OnRenderStatusStripSizingGrip(ToolStripRenderEventArgs e) { }
    }

    // Rounded Fluent button: accent-filled when Primary, neutral otherwise.
    class FluentButton : Button
    {
        bool hover, down;
        public bool Primary { get; set; }

        public FluentButton()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            Font = Theme.UiFont(9.5f);
            Cursor = Cursors.Hand;
            MinimumSize = new Size(96, 32);
            AutoSize = true;
            Padding = new Padding(10, 0, 10, 0);
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = down = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs mevent) { down = true; Invalidate(); base.OnMouseDown(mevent); }
        protected override void OnMouseUp(MouseEventArgs mevent) { down = false; Invalidate(); base.OnMouseUp(mevent); }
        protected override void OnEnabledChanged(EventArgs e) { Invalidate(); base.OnEnabledChanged(e); }
        protected override void OnTextChanged(EventArgs e) { Invalidate(); base.OnTextChanged(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            Color parentBack = Parent != null ? Parent.BackColor : Theme.Window;
            g.Clear(parentBack);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Color fill, text, border;
            if (Primary)
            {
                fill = !Enabled ? Theme.Border : down ? Theme.Blend(Theme.Accent, parentBack, 0.25f) : hover ? Theme.Blend(Theme.Accent, parentBack, 0.1f) : Theme.Accent;
                text = Enabled ? Theme.OnAccent : Theme.TextDisabled;
                border = fill;
            }
            else
            {
                fill = down ? Theme.Pressed : hover ? Theme.Hover : Theme.Field;
                text = Enabled ? Theme.Text : Theme.TextDisabled;
                border = Theme.Dark ? Color.FromArgb(70, 70, 70) : Color.FromArgb(214, 214, 214);
            }
            var r = new RectangleF(0.5f, 0.5f, Width - 1.5f, Height - 1.5f);
            using (var path = Theme.Rounded(r, 4.5f))
            using (var br = new SolidBrush(fill))
            using (var pen = new Pen(border))
            {
                g.FillPath(br, path);
                g.DrawPath(pen, path);
            }
            TextRenderer.DrawText(g, Text, Font, ClientRectangle, text, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPrefix);
            if (Focused && ShowFocusCues)
                using (var pen = new Pen(Theme.Text, 1.5f))
                using (var path = Theme.Rounded(new RectangleF(1.5f, 1.5f, Width - 3.5f, Height - 3.5f), 4f))
                    g.DrawPath(pen, path);
        }
    }
}
