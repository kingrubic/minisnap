using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace MiniSnap
{
    static class Library
    {
        static readonly string[] ImageExts = { ".png", ".jpg", ".jpeg", ".bmp", ".gif" };
        static readonly string[] VideoExts = { ".mp4" };

        public static string Folder { get { return Ensure(Environment.SpecialFolder.MyPictures); } }
        public static string VideoFolder { get { return Ensure(Environment.SpecialFolder.MyVideos); } }

        static string Ensure(Environment.SpecialFolder root)
        {
            // MINISNAP_LIBRARY redirects the library (used by --selftest so it never touches real captures).
            string over = Environment.GetEnvironmentVariable("MINISNAP_LIBRARY");
            string f = string.IsNullOrEmpty(over)
                ? Path.Combine(Environment.GetFolderPath(root), "MiniSnap")
                : Path.Combine(over, root.ToString());
            Directory.CreateDirectory(f);
            return f;
        }

        public static string NewPath() { return Unique(Folder, ".png"); }
        public static string NewVideoPath() { return Unique(VideoFolder, ".mp4"); }

        static string Unique(string folder, string ext)
        {
            string name = "MiniSnap_" + DateTime.Now.ToString("yyyy-MM-dd_HH-mm-ss");
            string p = Path.Combine(folder, name + ext);
            for (int i = 2; File.Exists(p); i++) p = Path.Combine(folder, name + "_" + i + ext);
            return p;
        }

        public static bool IsImage(string path) { return ImageExts.Contains(Path.GetExtension(path).ToLowerInvariant()); }
        public static bool IsVideo(string path) { return VideoExts.Contains(Path.GetExtension(path).ToLowerInvariant()); }

        public static List<FileInfo> AllFiles()
        {
            var files = new DirectoryInfo(Folder).GetFiles().Where(f => IsImage(f.Name))
                .Concat(new DirectoryInfo(VideoFolder).GetFiles().Where(f => IsVideo(f.Name)));
            return files.OrderByDescending(f => f.LastWriteTime).ToList();
        }

        public static void OpenFolder() { Process.Start("explorer.exe", "\"" + Folder + "\""); }
        public static void ShowInExplorer(string path) { Process.Start("explorer.exe", "/select,\"" + path + "\""); }
    }

    static class ShellThumbnail
    {
        [ComImport, Guid("bcc18b79-ba16-442f-80c4-8a59c30c463b"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IShellItemImageFactory
        {
            [PreserveSig] int GetImage(SIZE size, int flags, out IntPtr phbm);
        }

        [StructLayout(LayoutKind.Sequential)]
        struct SIZE { public int cx, cy; }

        [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
        static extern void SHCreateItemFromParsingName(string path, IntPtr pbc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid,
            [MarshalAs(UnmanagedType.Interface)] out IShellItemImageFactory ppv);

        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr h);

        const int SIIGBF_BIGGERSIZEOK = 1, SIIGBF_THUMBNAILONLY = 8;

        // Windows' own thumbnail (works for videos); null when the shell has none.
        public static Bitmap Get(string path, int size)
        {
            IShellItemImageFactory f;
            try { SHCreateItemFromParsingName(path, IntPtr.Zero, typeof(IShellItemImageFactory).GUID, out f); }
            catch (Exception) { return null; }
            try
            {
                IntPtr hbm;
                if (f.GetImage(new SIZE { cx = size, cy = size }, SIIGBF_BIGGERSIZEOK | SIIGBF_THUMBNAILONLY, out hbm) != 0) return null;
                try
                {
                    using (var tmp = Image.FromHbitmap(hbm)) return new Bitmap(tmp);
                }
                finally { DeleteObject(hbm); }
            }
            finally { Marshal.ReleaseComObject(f); }
        }
    }

    class LibraryForm : Form
    {
        enum Filter { All, Images, Videos }

        readonly Action<string> openImage, ocrFile;
        readonly float ui;
        readonly int thumbW, thumbH;
        readonly ListView list;
        readonly ImageList thumbs;
        readonly ToolStripButton allBtn, imgBtn, vidBtn;
        readonly ToolStripTextBox search;
        readonly ToolStripStatusLabel countLabel;
        readonly Label emptyLabel;
        readonly ContextMenuStrip menu;
        readonly ToolStripMenuItem ocrItem;
        readonly List<FileSystemWatcher> watchers = new List<FileSystemWatcher>();
        readonly System.Windows.Forms.Timer refreshTimer;
        Filter filter = Filter.All;
        int generation;
        string pendingReveal;

        public LibraryForm(Action<string> openImage, Action<string> ocrFile)
        {
            this.openImage = openImage;
            this.ocrFile = ocrFile;
            using (var g = CreateGraphics()) ui = g.DpiX / 96f;
            thumbW = Math.Min(256, (int)(200 * ui));
            thumbH = Math.Min(256, (int)(130 * ui));

            Text = L.T("Thư viện — MiniSnap");
            Icon = AppIcon.Get();
            Font = Theme.UiFont(9f);
            KeyPreview = true;
            Size = new Size((int)(1000 * ui), (int)(680 * ui));
            MinimumSize = new Size((int)(520 * ui), (int)(360 * ui));
            StartPosition = FormStartPosition.CenterScreen;

            var bar = new ToolStrip
            {
                GripStyle = ToolStripGripStyle.Hidden,
                ImageScalingSize = new Size((int)(20 * ui), (int)(20 * ui)),
                Padding = new Padding((int)(8 * ui), (int)(4 * ui), (int)(8 * ui), (int)(4 * ui)),
            };
            allBtn = new ToolStripButton(L.T("Tất cả"), null, (s, e) => SetFilter(Filter.All));
            imgBtn = new ToolStripButton(L.T("Ảnh"), null, (s, e) => SetFilter(Filter.Images));
            vidBtn = new ToolStripButton(L.T("Video"), null, (s, e) => SetFilter(Filter.Videos));
            bar.Items.AddRange(new ToolStripItem[] { allBtn, imgBtn, vidBtn, new ToolStripSeparator(), new ToolStripLabel(L.T("Tìm:")) });
            search = new ToolStripTextBox { AutoSize = false, Width = (int)(180 * ui) };
            search.TextChanged += (s, e) => { refreshTimer.Stop(); refreshTimer.Start(); };
            bar.Items.Add(search);
            bar.Items.Add(new ToolStripSeparator());
            bar.Items.Add(MakeButton(L.T("Làm mới"), IconKind.Refresh, (s, e) => Populate()));
            bar.Items.Add(MakeButton(L.T("Thư mục ảnh"), IconKind.Folder, (s, e) => Library.OpenFolder()));
            bar.Items.Add(MakeButton(L.T("Thư mục video"), IconKind.Video, (s, e) => Process.Start("explorer.exe", "\"" + Library.VideoFolder + "\"")));

            thumbs = new ImageList { ColorDepth = ColorDepth.Depth32Bit, ImageSize = new Size(thumbW, thumbH) };
            thumbs.Images.Add("__image", Placeholder(false));
            thumbs.Images.Add("__video", Placeholder(true));

            list = new ListView
            {
                Dock = DockStyle.Fill,
                View = View.LargeIcon,
                LargeImageList = thumbs,
                ShowGroups = true,
                ShowItemToolTips = true,
                HideSelection = false,
                BorderStyle = BorderStyle.None,
                BackColor = Color.FromArgb(248, 248, 250),
            };
            list.ItemActivate += (s, e) => OpenSelected();
            list.ItemDrag += (s, e) =>
            {
                var paths = SelectedPaths();
                if (paths.Length > 0) list.DoDragDrop(new DataObject(DataFormats.FileDrop, paths), DragDropEffects.Copy);
            };

            menu = new ContextMenuStrip();
            var openItem = new ToolStripMenuItem(L.T("Mở"), null, (s, e) => OpenSelected());
            openItem.Font = new Font(openItem.Font, FontStyle.Bold);
            ocrItem = new ToolStripMenuItem(L.T("Trích chữ (OCR)"), Icons.Draw(IconKind.Ocr, 16), (s, e) => { var p = SelectedPaths(); if (p.Length > 0) ocrFile(p[0]); });
            menu.Items.AddRange(new ToolStripItem[]
            {
                openItem,
                ocrItem,
                new ToolStripMenuItem(L.T("Sao chép"), Icons.Draw(IconKind.Copy, 16), (s, e) => CopySelected()) { ShortcutKeyDisplayString = "Ctrl+C" },
                new ToolStripMenuItem(L.T("Hiện trong thư mục"), Icons.Draw(IconKind.Folder, 16), (s, e) => { var p = SelectedPaths(); if (p.Length > 0) Library.ShowInExplorer(p[0]); }),
                new ToolStripSeparator(),
                new ToolStripMenuItem(L.T("Xoá (vào Thùng rác)"), Icons.Draw(IconKind.Delete, 16), (s, e) => DeleteSelected()) { ShortcutKeyDisplayString = "Delete" },
            });
            menu.Opening += (s, e) =>
            {
                var p = SelectedPaths();
                if (p.Length == 0) { e.Cancel = true; return; }
                ocrItem.Visible = p.Length == 1 && Library.IsImage(p[0]);
            };
            list.ContextMenuStrip = menu;

            emptyLabel = new Label
            {
                Dock = DockStyle.Fill,
                TextAlign = ContentAlignment.MiddleCenter,
                ForeColor = Color.Gray,
                Font = Theme.UiFont(12f),
                BackColor = list.BackColor,
                Text = EmptyText(),
                UseMnemonic = false,
                Visible = false,
            };

            var status = new StatusStrip();
            countLabel = new ToolStripStatusLabel { Spring = true, TextAlign = ContentAlignment.MiddleLeft };
            status.Items.Add(countLabel);

            Controls.Add(emptyLabel);
            Controls.Add(list);
            Controls.Add(bar);
            Controls.Add(status);

            refreshTimer = new System.Windows.Forms.Timer { Interval = 500 };
            refreshTimer.Tick += (s, e) => { refreshTimer.Stop(); Populate(); };
            foreach (var folder in new[] { Library.Folder, Library.VideoFolder })
            {
                var w = new FileSystemWatcher(folder) { NotifyFilter = NotifyFilters.FileName | NotifyFilters.LastWrite, SynchronizingObject = this };
                FileSystemEventHandler h = (s, e) => { refreshTimer.Stop(); refreshTimer.Start(); };
                w.Created += h;
                w.Deleted += h;
                w.Changed += h;
                w.Renamed += (s, e) => { refreshTimer.Stop(); refreshTimer.Start(); };
                w.EnableRaisingEvents = true;
                watchers.Add(w);
            }

            Theme.Apply(this);
            Theme.StyleStrip(menu);
            emptyLabel.BackColor = list.BackColor;
            emptyLabel.ForeColor = Theme.TextSecondary;
            UpdateFilterButtons();
            Populate();
        }

        static string EmptyText()
        {
            var keys = HotkeySettings.Load();
            var cap = keys[HotkeyAction.CaptureRegion];
            var rec = keys[HotkeyAction.RecordVideo];
            string hint = (cap.IsNone ? L.T("Dùng menu ở khay hệ thống để chụp") : L.T("Nhấn ") + cap.ShortText + L.T(" để chụp"))
                + (rec.IsNone ? "." : ", " + rec.ShortText + L.T(" để quay video."));
            return L.T("Chưa có ảnh hay video nào.\n") + hint;
        }

        static ToolStripButton MakeButton(string text, IconKind icon, EventHandler onClick)
        {
            return new ToolStripButton(text, Icons.Draw(icon, 20), onClick) { DisplayStyle = ToolStripItemDisplayStyle.ImageAndText };
        }

        Bitmap Placeholder(bool video)
        {
            var bmp = new Bitmap(thumbW, thumbH, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Theme.Dark ? Theme.Surface : Color.FromArgb(232, 232, 236));
                if (video) Icons.DrawPlayBadge(g, new RectangleF(0, 0, thumbW, thumbH));
            }
            return bmp;
        }

        // Letterbox a thumbnail into the fixed ImageList cell.
        Bitmap Fit(Image src, bool video)
        {
            var bmp = new Bitmap(thumbW, thumbH, PixelFormat.Format32bppArgb);
            using (var g = Graphics.FromImage(bmp))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic;
                g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                float s = Math.Min((float)(thumbW - 4) / src.Width, (float)(thumbH - 4) / src.Height);
                s = Math.Min(s, 1f);
                float w = src.Width * s, h = src.Height * s;
                var r = new RectangleF((thumbW - w) / 2, (thumbH - h) / 2, w, h);
                using (var shadow = new SolidBrush(Color.FromArgb(40, 0, 0, 0))) g.FillRectangle(shadow, r.X + 1, r.Y + 2, r.Width, r.Height);
                g.DrawImage(src, r);
                using (var pen = new Pen(Color.FromArgb(50, 0, 0, 0))) g.DrawRectangle(pen, r.X, r.Y, r.Width - 1, r.Height - 1);
                if (video) Icons.DrawPlayBadge(g, r);
            }
            return bmp;
        }

        Bitmap MakeThumb(string path)
        {
            bool video = Library.IsVideo(path);
            if (video)
            {
                using (var shell = ShellThumbnail.Get(path, Math.Max(thumbW, thumbH)))
                    return shell != null ? Fit(shell, true) : null;
            }
            using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var img = Image.FromStream(fs, false, false))
                return Fit(img, false);
        }

        void SetFilter(Filter f)
        {
            filter = f;
            Theme.Apply(this);
            Theme.StyleStrip(menu);
            emptyLabel.BackColor = list.BackColor;
            emptyLabel.ForeColor = Theme.TextSecondary;
            UpdateFilterButtons();
            Populate();
        }

        void UpdateFilterButtons()
        {
            allBtn.Checked = filter == Filter.All;
            imgBtn.Checked = filter == Filter.Images;
            vidBtn.Checked = filter == Filter.Videos;
        }

        static string GroupName(DateTime t)
        {
            var today = DateTime.Today;
            if (t >= today) return L.T("Hôm nay");
            if (t >= today.AddDays(-1)) return L.T("Hôm qua");
            if (t >= today.AddDays(-7)) return L.T("7 ngày qua");
            if (t >= new DateTime(today.Year, today.Month, 1)) return L.T("Tháng này");
            return L.T("Cũ hơn");
        }

        static string HumanSize(long bytes)
        {
            if (bytes >= 1 << 20) return (bytes / 1048576.0).ToString("0.0") + " MB";
            return Math.Max(1, bytes / 1024) + " KB";
        }

        public void Reveal(string path)
        {
            pendingReveal = path;
            Populate();
        }

        void Populate()
        {
            List<FileInfo> files;
            try { files = Library.AllFiles(); }
            catch (IOException) { return; }
            string q = search.Text.Trim();
            files = files.Where(f =>
                (filter == Filter.All || (filter == Filter.Images ? Library.IsImage(f.Name) : Library.IsVideo(f.Name)))
                && (q.Length == 0 || f.Name.IndexOf(q, StringComparison.OrdinalIgnoreCase) >= 0)).ToList();

            var selectedBefore = new HashSet<string>(SelectedPaths());
            int gen = ++generation;
            list.BeginUpdate();
            list.Items.Clear();
            list.Groups.Clear();
            var groups = new Dictionary<string, ListViewGroup>();
            var todo = new List<KeyValuePair<ListViewItem, FileInfo>>();
            ListViewItem reveal = null;
            foreach (var f in files)
            {
                string gname = GroupName(f.LastWriteTime);
                ListViewGroup grp;
                if (!groups.TryGetValue(gname, out grp))
                {
                    grp = new ListViewGroup(gname, gname);
                    groups[gname] = grp;
                    list.Groups.Add(grp);
                }
                bool video = Library.IsVideo(f.Name);
                string key = f.FullName + "|" + f.LastWriteTimeUtc.Ticks;
                var item = new ListViewItem(Path.GetFileNameWithoutExtension(f.Name))
                {
                    Tag = f.FullName,
                    Group = grp,
                    ImageKey = thumbs.Images.ContainsKey(key) ? key : (video ? "__video" : "__image"),
                    ToolTipText = f.Name + "\n" + f.LastWriteTime.ToString("dd/MM/yyyy HH:mm") + L.T(" • ") + HumanSize(f.Length),
                };
                list.Items.Add(item);
                if (selectedBefore.Contains(f.FullName)) item.Selected = true;
                if (pendingReveal != null && string.Equals(pendingReveal, f.FullName, StringComparison.OrdinalIgnoreCase)) reveal = item;
                if (!thumbs.Images.ContainsKey(key)) todo.Add(new KeyValuePair<ListViewItem, FileInfo>(item, f));
            }
            list.EndUpdate();
            if (reveal != null)
            {
                list.SelectedItems.Clear();
                reveal.Selected = true;
                reveal.Focused = true;
                reveal.EnsureVisible();
                pendingReveal = null;
            }
            emptyLabel.Visible = list.Items.Count == 0;
            countLabel.Text = files.Count(f => Library.IsImage(f.Name)) + L.T(" ảnh • ") + files.Count(f => Library.IsVideo(f.Name)) + L.T(" video   —   ")
                + Library.Folder + "  |  " + Library.VideoFolder;
            if (todo.Count > 0) LoadThumbs(gen, todo);
        }

        void LoadThumbs(int gen, List<KeyValuePair<ListViewItem, FileInfo>> todo)
        {
            var t = new Thread(() =>
            {
                foreach (var kv in todo)
                {
                    if (gen != generation || IsDisposed) return;
                    var f = kv.Value;
                    string key = f.FullName + "|" + f.LastWriteTimeUtc.Ticks;
                    Bitmap thumb;
                    try { thumb = MakeThumb(f.FullName); }
                    catch (Exception) { thumb = null; }
                    if (thumb == null) continue;
                    var item = kv.Key;
                    try
                    {
                        BeginInvoke(new Action(() =>
                        {
                            if (!thumbs.Images.ContainsKey(key)) thumbs.Images.Add(key, thumb);
                            if (gen == generation && item.ListView != null) item.ImageKey = key;
                        }));
                    }
                    catch (InvalidOperationException) { return; }
                }
            });
            t.IsBackground = true;
            t.SetApartmentState(ApartmentState.STA);
            t.Start();
        }

        string[] SelectedPaths()
        {
            return list.SelectedItems.Cast<ListViewItem>().Select(i => (string)i.Tag).ToArray();
        }

        void OpenSelected()
        {
            foreach (var p in SelectedPaths().Take(5))
            {
                if (Library.IsVideo(p)) Process.Start(p);
                else openImage(p);
            }
        }

        void CopySelected()
        {
            var paths = SelectedPaths();
            if (paths.Length == 0) return;
            try
            {
                if (paths.Length == 1 && Library.IsImage(paths[0]))
                {
                    using (var img = Image.FromFile(paths[0]))
                    using (var bmp = new Bitmap(img))
                        Clipboard.SetImage(bmp);
                }
                else
                {
                    var sc = new System.Collections.Specialized.StringCollection();
                    sc.AddRange(paths);
                    Clipboard.SetFileDropList(sc);
                }
                countLabel.Text = L.T("Đã sao chép ") + (paths.Length == 1 ? Path.GetFileName(paths[0]) : paths.Length + L.T(" mục")) + L.T(" vào clipboard");
            }
            catch (Exception ex) { countLabel.Text = L.T("Không sao chép được: ") + ex.Message; }
        }

        void DeleteSelected()
        {
            var paths = SelectedPaths();
            if (paths.Length == 0) return;
            string what = paths.Length == 1 ? "\"" + Path.GetFileName(paths[0]) + "\"" : paths.Length + L.T(" mục");
            if (MessageBox.Show(this, L.T("Chuyển ") + what + L.T(" vào Thùng rác?"), "MiniSnap", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK) return;
            foreach (var p in paths)
            {
                try
                {
                    Microsoft.VisualBasic.FileIO.FileSystem.DeleteFile(p, Microsoft.VisualBasic.FileIO.UIOption.OnlyErrorDialogs,
                        Microsoft.VisualBasic.FileIO.RecycleOption.SendToRecycleBin);
                }
                catch (Exception ex)
                {
                    MessageBox.Show(this, L.T("Không xoá được ") + Path.GetFileName(p) + ":\n" + ex.Message, "MiniSnap", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
            Populate();
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (search.Focused) return base.ProcessCmdKey(ref msg, keyData);
            switch (keyData)
            {
                case Keys.Delete: DeleteSelected(); return true;
                case Keys.Control | Keys.C: CopySelected(); return true;
                case Keys.Control | Keys.A:
                    list.BeginUpdate();
                    foreach (ListViewItem i in list.Items) i.Selected = true;
                    list.EndUpdate();
                    return true;
                case Keys.F5: Populate(); return true;
                case Keys.Control | Keys.F: search.Focus(); return true;
            }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            generation++;
            foreach (var w in watchers) w.Dispose();
            refreshTimer.Dispose();
            base.OnFormClosed(e);
        }
    }
}
