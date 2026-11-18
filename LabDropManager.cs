using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace LabDropManager
{
    static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        private static void RegisterProtocol()
        {
            try
            {
                string exePath = Application.ExecutablePath;
                using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Classes\labdrop"))
                {
                    if (key != null)
                    {
                        key.SetValue("", "URL:LabDrop Network Disk");
                        key.SetValue("URL Protocol", "");
                        using (var cmdKey = key.CreateSubKey(@"shell\open\command"))
                        {
                            if (cmdKey != null)
                                cmdKey.SetValue("", "\"" + exePath + "\" \"%1\"");
                        }
                    }
                }
            }
            catch { }
        }

        private static string GetQueryParam(string query, string name)
        {
            if (string.IsNullOrEmpty(query)) return "";
            if (query.StartsWith("?")) query = query.Substring(1);
            foreach (string part in query.Split('&'))
            {
                int idx = part.IndexOf('=');
                if (idx > 0)
                {
                    string k = Uri.UnescapeDataString(part.Substring(0, idx));
                    if (string.Equals(k, name, StringComparison.OrdinalIgnoreCase))
                        return Uri.UnescapeDataString(part.Substring(idx + 1));
                }
            }
            return "";
        }

        private static void HandleProtocolUri(string rawUri)
        {
            try
            {
                Uri uri = new Uri(rawUri);
                string host = GetQueryParam(uri.Query, "host");
                string port = GetQueryParam(uri.Query, "port");
                string dir = GetQueryParam(uri.Query, "dir");

                if (string.IsNullOrWhiteSpace(host)) host = "127.0.0.1";
                if (string.IsNullOrWhiteSpace(port)) port = "8000";

                string unc = "\\\\" + host + "@" + port + "\\DavWWWRoot\\webdav";
                if (!string.IsNullOrWhiteSpace(dir))
                {
                    string cleanDir = dir.Replace('/', '\\').Trim('\\');
                    if (!string.IsNullOrEmpty(cleanDir) && !cleanDir.Contains(".."))
                        unc = unc + "\\" + cleanDir;
                }

                // 一步直开 Windows 真实文件夹窗口，无需二次操作
                Process.Start("explorer.exe", "\"" + unc + "\"");
            }
            catch { }
        }

        [STAThread]
        static void Main(string[] args)
        {
            RegisterProtocol();

            if (args != null && args.Length > 0 && args[0].StartsWith("labdrop://", StringComparison.OrdinalIgnoreCase))
            {
                HandleProtocolUri(args[0]);
                return;
            }

            if (Environment.OSVersion.Version.Major >= 6)
                SetProcessDPIAware();

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }

    // 抗锯齿圆角卡片控件
    public class RoundedCard : Panel
    {
        public int CornerRadius { get; set; }
        public Color BorderColor { get; set; }
        public Color FillColor { get; set; }

        public RoundedCard()
        {
            CornerRadius = 12;
            BorderColor = Color.FromArgb(229, 233, 240);
            FillColor = Color.White;
            DoubleBuffered = true;
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = GetRoundedPath(rect, CornerRadius))
            using (SolidBrush brush = new SolidBrush(FillColor))
            using (Pen pen = new Pen(BorderColor, 1f))
            {
                e.Graphics.FillPath(brush, path);
                if (BorderColor != Color.Transparent)
                    e.Graphics.DrawPath(pen, path);
            }
            base.OnPaint(e);
        }

        public static GraphicsPath GetRoundedPath(Rectangle rect, int radius)
        {
            GraphicsPath path = new GraphicsPath();
            int d = radius * 2;
            if (d <= 0)
            {
                path.AddRectangle(rect);
                return path;
            }
            path.AddArc(rect.X, rect.Y, d, d, 180, 90);
            path.AddArc(rect.Right - d, rect.Y, d, d, 270, 90);
            path.AddArc(rect.Right - d, rect.Bottom - d, d, d, 0, 90);
            path.AddArc(rect.X, rect.Bottom - d, d, d, 90, 90);
            path.CloseFigure();
            return path;
        }
    }

    // 抗锯齿现代圆角按钮
    public class ModernButton : Control
    {
        public int CornerRadius { get; set; }
        public Color NormalBg { get; set; }
        public Color HoverBg { get; set; }
        public Color DisabledBg { get; set; }
        public Color TextColor { get; set; }
        public Color DisabledTextColor { get; set; }
        public Color BorderColor { get; set; }

        private bool isHover = false;
        private bool isDown = false;

        public ModernButton()
        {
            CornerRadius = 8;
            NormalBg = Color.FromArgb(37, 99, 235);
            HoverBg = Color.FromArgb(29, 78, 216);
            DisabledBg = Color.FromArgb(241, 245, 249);
            TextColor = Color.White;
            DisabledTextColor = Color.FromArgb(148, 163, 184);
            BorderColor = Color.Transparent;
            Cursor = Cursors.Hand;
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;
        }

        protected override void OnMouseEnter(EventArgs e) { isHover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { isHover = false; isDown = false; Invalidate(); base.OnMouseLeave(e); }
        protected override void OnMouseDown(MouseEventArgs e) { if (e.Button == MouseButtons.Left) { isDown = true; Invalidate(); } base.OnMouseDown(e); }
        protected override void OnMouseUp(MouseEventArgs e) { isDown = false; Invalidate(); base.OnMouseUp(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

            Color bg = !Enabled ? DisabledBg : (isHover ? HoverBg : NormalBg);
            Color fg = !Enabled ? DisabledTextColor : TextColor;
            if (isDown && Enabled)
                bg = ControlPaint.Dark(bg, 0.05f);

            Rectangle rect = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = RoundedCard.GetRoundedPath(rect, CornerRadius))
            using (SolidBrush brush = new SolidBrush(bg))
            {
                e.Graphics.FillPath(brush, path);
                if (BorderColor != Color.Transparent)
                {
                    using (Pen pen = new Pen(BorderColor, 1f))
                        e.Graphics.DrawPath(pen, path);
                }
            }

            TextRenderer.DrawText(
                e.Graphics, Text, Font,
                new Rectangle(0, 0, Width, Height),
                fg,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine
            );
        }
    }

    // 现代胶囊状态徽标
    public class StatusPill : Control
    {
        public Color BgColor { get; set; }
        public Color DotColor { get; set; }
        public Color LabelColor { get; set; }

        public StatusPill()
        {
            BgColor = Color.FromArgb(243, 244, 246);
            DotColor = Color.FromArgb(156, 163, 175);
            LabelColor = Color.FromArgb(107, 114, 128);
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

            Rectangle rect = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = RoundedCard.GetRoundedPath(rect, Height / 2))
            using (SolidBrush bg = new SolidBrush(BgColor))
            {
                e.Graphics.FillPath(bg, path);
            }

            int dotSize = 8;
            int dotY = (Height - dotSize) / 2;
            using (SolidBrush dotBrush = new SolidBrush(DotColor))
            {
                e.Graphics.FillEllipse(dotBrush, 11, dotY, dotSize, dotSize);
            }

            TextRenderer.DrawText(
                e.Graphics, Text, Font,
                new Rectangle(24, 0, Width - 30, Height),
                LabelColor,
                TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine
            );
        }
    }

    // iOS / Win11 现代滑动开关 (Toggle Switch)
    public class ToggleSwitch : Control
    {
        private bool isChecked = true;
        public bool Checked
        {
            get { return isChecked; }
            set { isChecked = value; Invalidate(); }
        }

        public event EventHandler Toggled;

        public ToggleSwitch()
        {
            Size = new Size(44, 24);
            Cursor = Cursors.Hand;
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;
        }

        protected override void OnClick(EventArgs e)
        {
            isChecked = !isChecked;
            Invalidate();
            if (Toggled != null) Toggled(this, EventArgs.Empty);
            base.OnClick(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Color trackColor = isChecked ? Color.FromArgb(16, 185, 129) : Color.FromArgb(203, 213, 225);

            Rectangle track = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = RoundedCard.GetRoundedPath(track, Height / 2))
            using (SolidBrush brush = new SolidBrush(trackColor))
            {
                e.Graphics.FillPath(brush, path);
            }

            int pad = 3;
            int knobSize = Height - pad * 2;
            int knobX = isChecked ? (Width - knobSize - pad - 1) : pad;
            using (SolidBrush knobBrush = new SolidBrush(Color.White))
            {
                e.Graphics.FillEllipse(knobBrush, knobX, pad, knobSize, knobSize);
            }
        }
    }

    public class MainForm : Form
    {
        private readonly string baseDir;
        private readonly string configFile;
        private readonly string runtimeFile;
        private readonly string daemonScript;
        private readonly string defaultStorageDir;
        private const int PORT = 8000;

        private StatusPill statusPill;
        private ModernButton btnMainAction;
        private Label lblDirPath;
        private ModernButton btnChangeDir;
        private ModernButton btnOpenDir;

        private Label lblLanUrl;
        private ModernButton btnCopyLan;
        private ModernButton btnOpenLan;

        private ToggleSwitch togglePublic;
        private Label lblPubState;
        private Label lblPubUrl;
        private ModernButton btnCopyPub;
        private ModernButton btnOpenPub;

        private System.Windows.Forms.Timer statusTimer;

        private string storageDir;
        private bool enablePublic = true;
        private string currentPublicUrl = "";
        private string currentLanUrl = "";
        private bool isRunning = false;
        private bool isStarting = false;
        private bool isStopping = false;
        private DateTime startTimestamp = DateTime.MinValue;

        private readonly JavaScriptSerializer json = new JavaScriptSerializer();

        public MainForm()
        {
            baseDir = AppDomain.CurrentDomain.BaseDirectory;
            configFile = Path.Combine(baseDir, "config.json");
            runtimeFile = Path.Combine(baseDir, "runtime.json");
            daemonScript = Path.Combine(baseDir, "daemon.py");
            defaultStorageDir = Path.Combine(baseDir, "uploads");

            if (!Directory.Exists(defaultStorageDir))
                Directory.CreateDirectory(defaultStorageDir);

            LoadConfig();
            InitializeUi();
            StartPolling();
        }

        private void LoadConfig()
        {
            storageDir = defaultStorageDir;
            enablePublic = true;
            if (File.Exists(configFile))
            {
                try
                {
                    var text = File.ReadAllText(configFile, Encoding.UTF8);
                    var dict = json.Deserialize<Dictionary<string, object>>(text);
                    if (dict != null)
                    {
                        if (dict.ContainsKey("storage_dir") && dict["storage_dir"] != null)
                        {
                            var dir = dict["storage_dir"].ToString();
                            if (!string.IsNullOrWhiteSpace(dir))
                                storageDir = dir;
                        }
                        if (dict.ContainsKey("enable_public") && dict["enable_public"] != null)
                        {
                            bool val;
                            if (bool.TryParse(dict["enable_public"].ToString(), out val))
                                enablePublic = val;
                        }
                    }
                }
                catch { }
            }
        }

        private void SaveConfig()
        {
            try
            {
                var dict = new Dictionary<string, object>();
                dict["storage_dir"] = storageDir;
                dict["port"] = PORT;
                dict["enable_public"] = enablePublic;
                File.WriteAllText(configFile, json.Serialize(dict), Encoding.UTF8);
            }
            catch { }
        }

        private Dictionary<string, object> ReadRuntime()
        {
            if (File.Exists(runtimeFile))
            {
                try
                {
                    var text = File.ReadAllText(runtimeFile, Encoding.UTF8);
                    var dict = json.Deserialize<Dictionary<string, object>>(text);
                    if (dict != null) return dict;
                }
                catch { }
            }
            return new Dictionary<string, object>();
        }

        private string GetStr(Dictionary<string, object> d, string key)
        {
            if (d != null && d.ContainsKey(key) && d[key] != null)
                return d[key].ToString();
            return "";
        }

        private bool IsPortInUse(int port)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var result = client.BeginConnect("127.0.0.1", port, null, null);
                    bool success = result.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(200));
                    if (!success) return false;
                    client.EndConnect(result);
                    return true;
                }
            }
            catch { return false; }
        }

        private string FindPythonwExe()
        {
            string[] candidates = new string[] {
                Path.Combine(baseDir, "runtime-py", "pythonw.exe"),
                Path.Combine(baseDir, "python", "pythonw.exe"),
                @"C:\msys64\ucrt64\bin\pythonw.exe"
            };
            foreach (var c in candidates)
            {
                if (File.Exists(c)) return c;
            }
            return "pythonw.exe";
        }

        private static void DrawYellowLightningLogo(Graphics g, int size)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(1, 1, size - 2, size - 2);
            int radius = Math.Max(4, size / 4);
            using (GraphicsPath path = RoundedCard.GetRoundedPath(rect, radius))
            using (LinearGradientBrush bg = new LinearGradientBrush(
                rect, Color.FromArgb(254, 224, 71), Color.FromArgb(245, 158, 11), LinearGradientMode.Vertical))
            {
                g.FillPath(bg, path);
            }

            float s = size;
            PointF[] bolt = new PointF[] {
                new PointF(0.56f * s, 0.14f * s),
                new PointF(0.24f * s, 0.54f * s),
                new PointF(0.49f * s, 0.54f * s),
                new PointF(0.42f * s, 0.86f * s),
                new PointF(0.76f * s, 0.44f * s),
                new PointF(0.51f * s, 0.44f * s)
            };
            using (SolidBrush whiteBrush = new SolidBrush(Color.White))
            {
                g.FillPolygon(whiteBrush, bolt);
            }
        }

        private static Icon CreateVectorAppIcon()
        {
            using (Bitmap bmp = new Bitmap(32, 32))
            {
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.Transparent);
                    DrawYellowLightningLogo(g, 32);
                }
                IntPtr hIcon = bmp.GetHicon();
                return Icon.FromHandle(hIcon);
            }
        }

        private void InitializeUi()
        {
            this.Text = "LabDrop · 实验室网络U盘";
            this.ClientSize = new Size(468, 526);
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(245, 247, 250);
            this.Font = new Font("Microsoft YaHei UI", 9f);

            try { this.Icon = CreateVectorAppIcon(); } catch { }

            // 1. 顶部极简标题栏 (纯 GDI+ 抗锯齿矢量绘制黄色闪电 Logo，绝无位图解码异常)
            var picIcon = new Panel();
            picIcon.Location = new Point(24, 22);
            picIcon.Size = new Size(40, 40);
            picIcon.BackColor = Color.Transparent;
            picIcon.Paint += (s, pe) => DrawYellowLightningLogo(pe.Graphics, 40);
            this.Controls.Add(picIcon);

            var lblBrand = new Label();
            lblBrand.Text = "LabDrop";
            lblBrand.Font = new Font("Microsoft YaHei UI", 14.5f, FontStyle.Bold);
            lblBrand.ForeColor = Color.FromArgb(17, 24, 39);
            lblBrand.Location = new Point(74, 20);
            lblBrand.AutoSize = true;
            this.Controls.Add(lblBrand);

            var lblSubBrand = new Label();
            lblSubBrand.Text = "实验室共享网络U盘";
            lblSubBrand.Font = new Font("Microsoft YaHei UI", 8.5f);
            lblSubBrand.ForeColor = Color.FromArgb(107, 114, 128);
            lblSubBrand.Location = new Point(75, 45);
            lblSubBrand.AutoSize = true;
            this.Controls.Add(lblSubBrand);

            statusPill = new StatusPill();
            statusPill.Location = new Point(342, 28);
            statusPill.Size = new Size(102, 28);
            statusPill.Text = "已停止";
            statusPill.Font = new Font("Microsoft YaHei UI", 8.5f, FontStyle.Bold);
            this.Controls.Add(statusPill);

            // 2. 主控按钮 (单态丝滑切换，极简聚焦)
            btnMainAction = new ModernButton();
            btnMainAction.Location = new Point(24, 80);
            btnMainAction.Size = new Size(420, 46);
            btnMainAction.CornerRadius = 11;
            btnMainAction.Text = "启动网络U盘服务";
            btnMainAction.Font = new Font("Microsoft YaHei UI", 10.5f, FontStyle.Bold);
            btnMainAction.NormalBg = Color.FromArgb(37, 99, 235);
            btnMainAction.HoverBg = Color.FromArgb(29, 78, 216);
            btnMainAction.TextColor = Color.White;
            btnMainAction.Click += BtnMainAction_Click;
            this.Controls.Add(btnMainAction);

            // 3. 卡片一：共享文件夹 (U盘目录)
            var cardDir = new RoundedCard();
            cardDir.Location = new Point(24, 142);
            cardDir.Size = new Size(420, 102);
            this.Controls.Add(cardDir);

            var lblDirHead = new Label();
            lblDirHead.Text = "存储目录";
            lblDirHead.Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold);
            lblDirHead.ForeColor = Color.FromArgb(31, 41, 55);
            lblDirHead.Location = new Point(18, 16);
            lblDirHead.AutoSize = true;
            cardDir.Controls.Add(lblDirHead);

            btnChangeDir = CreateGhostButton("更改目录", new Point(268, 12), new Size(68, 26), Color.FromArgb(37, 99, 235));
            btnChangeDir.Click += BtnChangeDir_Click;
            cardDir.Controls.Add(btnChangeDir);

            btnOpenDir = CreateGhostButton("打开", new Point(344, 12), new Size(58, 26), Color.FromArgb(75, 85, 99));
            btnOpenDir.Click += BtnOpenDir_Click;
            cardDir.Controls.Add(btnOpenDir);

            var dirPill = new RoundedCard();
            dirPill.Location = new Point(18, 48);
            dirPill.Size = new Size(384, 38);
            dirPill.CornerRadius = 8;
            dirPill.FillColor = Color.FromArgb(248, 250, 252);
            dirPill.BorderColor = Color.FromArgb(241, 245, 249);
            cardDir.Controls.Add(dirPill);

            lblDirPath = new Label();
            lblDirPath.Text = storageDir;
            lblDirPath.Font = new Font("Consolas", 9f);
            lblDirPath.ForeColor = Color.FromArgb(71, 85, 105);
            lblDirPath.Location = new Point(12, 0);
            lblDirPath.Size = new Size(360, 38);
            lblDirPath.TextAlign = ContentAlignment.MiddleLeft;
            lblDirPath.AutoEllipsis = true;
            dirPill.Controls.Add(lblDirPath);

            // 4. 卡片二：访问地址与公网开关
            var cardNet = new RoundedCard();
            cardNet.Location = new Point(24, 258);
            cardNet.Size = new Size(420, 224);
            this.Controls.Add(cardNet);

            // 4.1 局域网行
            var lblLanHead = new Label();
            lblLanHead.Text = "局域网访问";
            lblLanHead.Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold);
            lblLanHead.ForeColor = Color.FromArgb(31, 41, 55);
            lblLanHead.Location = new Point(18, 18);
            lblLanHead.AutoSize = true;
            cardNet.Controls.Add(lblLanHead);

            var lblLanTag = new Label();
            lblLanTag.Text = "同 Wi-Fi 高速直传";
            lblLanTag.Font = new Font("Microsoft YaHei UI", 8f);
            lblLanTag.ForeColor = Color.FromArgb(16, 185, 129);
            lblLanTag.Location = new Point(102, 20);
            lblLanTag.AutoSize = true;
            cardNet.Controls.Add(lblLanTag);

            var lanPill = new RoundedCard();
            lanPill.Location = new Point(18, 48);
            lanPill.Size = new Size(272, 38);
            lanPill.CornerRadius = 8;
            lanPill.FillColor = Color.FromArgb(248, 250, 252);
            lanPill.BorderColor = Color.FromArgb(241, 245, 249);
            cardNet.Controls.Add(lanPill);

            lblLanUrl = new Label();
            lblLanUrl.Text = "服务未启动";
            lblLanUrl.Font = new Font("Consolas", 9.5f);
            lblLanUrl.ForeColor = Color.FromArgb(156, 163, 175);
            lblLanUrl.Location = new Point(12, 0);
            lblLanUrl.Size = new Size(248, 38);
            lblLanUrl.TextAlign = ContentAlignment.MiddleLeft;
            lblLanUrl.AutoEllipsis = true;
            lanPill.Controls.Add(lblLanUrl);

            btnCopyLan = CreateSoftButton("复制", new Point(298, 48), new Size(48, 38));
            btnCopyLan.Click += (s, e) => CopyWithFeedback(currentLanUrl, btnCopyLan);
            cardNet.Controls.Add(btnCopyLan);

            btnOpenLan = CreateSoftButton("打开", new Point(352, 48), new Size(50, 38));
            btnOpenLan.Click += (s, e) => OpenUrl(currentLanUrl);
            cardNet.Controls.Add(btnOpenLan);

            // 极细柔和分割线
            var sep = new Panel();
            sep.Location = new Point(18, 104);
            sep.Size = new Size(384, 1);
            sep.BackColor = Color.FromArgb(241, 245, 249);
            cardNet.Controls.Add(sep);

            // 4.2 公网行 + 现代滑动开关 ToggleSwitch
            var lblPubHead = new Label();
            lblPubHead.Text = "公网访问";
            lblPubHead.Font = new Font("Microsoft YaHei UI", 9.5f, FontStyle.Bold);
            lblPubHead.ForeColor = Color.FromArgb(31, 41, 55);
            lblPubHead.Location = new Point(18, 122);
            lblPubHead.AutoSize = true;
            cardNet.Controls.Add(lblPubHead);

            lblPubState = new Label();
            lblPubState.Text = enablePublic ? "已开启" : "已禁止";
            lblPubState.Font = new Font("Microsoft YaHei UI", 8.5f);
            lblPubState.ForeColor = enablePublic ? Color.FromArgb(16, 185, 129) : Color.FromArgb(156, 163, 175);
            lblPubState.Location = new Point(304, 124);
            lblPubState.Size = new Size(48, 20);
            lblPubState.TextAlign = ContentAlignment.MiddleRight;
            cardNet.Controls.Add(lblPubState);

            togglePublic = new ToggleSwitch();
            togglePublic.Location = new Point(358, 121);
            togglePublic.Checked = enablePublic;
            togglePublic.Toggled += TogglePublic_Toggled;
            cardNet.Controls.Add(togglePublic);

            var pubPill = new RoundedCard();
            pubPill.Location = new Point(18, 158);
            pubPill.Size = new Size(272, 38);
            pubPill.CornerRadius = 8;
            pubPill.FillColor = Color.FromArgb(248, 250, 252);
            pubPill.BorderColor = Color.FromArgb(241, 245, 249);
            cardNet.Controls.Add(pubPill);

            lblPubUrl = new Label();
            lblPubUrl.Text = enablePublic ? "启动服务后自动生成" : "公网访问已禁止";
            lblPubUrl.Font = new Font("Consolas", 9.5f);
            lblPubUrl.ForeColor = Color.FromArgb(156, 163, 175);
            lblPubUrl.Location = new Point(12, 0);
            lblPubUrl.Size = new Size(248, 38);
            lblPubUrl.TextAlign = ContentAlignment.MiddleLeft;
            lblPubUrl.AutoEllipsis = true;
            pubPill.Controls.Add(lblPubUrl);

            btnCopyPub = CreateSoftButton("复制", new Point(298, 158), new Size(48, 38));
            btnCopyPub.Click += (s, e) => CopyWithFeedback(currentPublicUrl, btnCopyPub);
            cardNet.Controls.Add(btnCopyPub);

            btnOpenPub = CreateSoftButton("打开", new Point(352, 158), new Size(50, 38));
            btnOpenPub.Click += (s, e) => OpenUrl(currentPublicUrl);
            cardNet.Controls.Add(btnOpenPub);

            // 5. 底部轻盈一句提示
            var lblFooter = new Label();
            lblFooter.Text = "关闭本窗口后服务仍在后台持续运行 · 随时重开即可管理";
            lblFooter.Font = new Font("Microsoft YaHei UI", 8f);
            lblFooter.ForeColor = Color.FromArgb(148, 163, 184);
            lblFooter.Location = new Point(24, 496);
            lblFooter.Size = new Size(420, 20);
            lblFooter.TextAlign = ContentAlignment.MiddleCenter;
            this.Controls.Add(lblFooter);
        }

        private ModernButton CreateGhostButton(string text, Point loc, Size size, Color textColor)
        {
            var btn = new ModernButton();
            btn.Text = text;
            btn.Location = loc;
            btn.Size = size;
            btn.CornerRadius = 6;
            btn.Font = new Font("Microsoft YaHei UI", 8.5f);
            btn.NormalBg = Color.Transparent;
            btn.HoverBg = Color.FromArgb(241, 245, 249);
            btn.DisabledBg = Color.Transparent;
            btn.TextColor = textColor;
            btn.DisabledTextColor = Color.FromArgb(180, 188, 200);
            return btn;
        }

        private ModernButton CreateSoftButton(string text, Point loc, Size size)
        {
            var btn = new ModernButton();
            btn.Text = text;
            btn.Location = loc;
            btn.Size = size;
            btn.CornerRadius = 8;
            btn.Font = new Font("Microsoft YaHei UI", 8.5f);
            btn.NormalBg = Color.FromArgb(241, 245, 249);
            btn.HoverBg = Color.FromArgb(226, 232, 240);
            btn.DisabledBg = Color.FromArgb(248, 250, 252);
            btn.TextColor = Color.FromArgb(51, 65, 85);
            btn.DisabledTextColor = Color.FromArgb(203, 213, 225);
            return btn;
        }

        private void TogglePublic_Toggled(object sender, EventArgs e)
        {
            enablePublic = togglePublic.Checked;
            SaveConfig();
            lblPubState.Text = enablePublic ? "已开启" : "已禁止";
            lblPubState.ForeColor = enablePublic ? Color.FromArgb(16, 185, 129) : Color.FromArgb(156, 163, 175);

            if (!enablePublic)
            {
                currentPublicUrl = "";
                lblPubUrl.Text = "公网访问已禁止";
                lblPubUrl.ForeColor = Color.FromArgb(156, 163, 175);
                btnCopyPub.Enabled = false;
                btnOpenPub.Enabled = false;
            }
            else if (isRunning)
            {
                lblPubUrl.Text = "正在连接公网通道...";
                lblPubUrl.ForeColor = Color.FromArgb(217, 119, 6);
            }
            RefreshStatus();
        }

        private void CopyWithFeedback(string text, ModernButton btn)
        {
            if (string.IsNullOrWhiteSpace(text)) return;
            try
            {
                Clipboard.SetText(text);
                string old = btn.Text;
                btn.Text = "已复制";
                btn.TextColor = Color.FromArgb(16, 185, 129);
                btn.Invalidate();
                var t = new System.Windows.Forms.Timer();
                t.Interval = 1200;
                t.Tick += (s, e) => {
                    btn.Text = old;
                    btn.TextColor = Color.FromArgb(51, 65, 85);
                    btn.Invalidate();
                    t.Stop();
                    t.Dispose();
                };
                t.Start();
            }
            catch { }
        }

        private void OpenUrl(string url)
        {
            if (string.IsNullOrWhiteSpace(url)) return;
            try { Process.Start(url); } catch { }
        }

        private void BtnChangeDir_Click(object sender, EventArgs e)
        {
            using (var dlg = new FolderBrowserDialog())
            {
                dlg.Description = "选择要共享为“网络U盘”的本地文件夹：";
                dlg.SelectedPath = storageDir;
                if (dlg.ShowDialog() == DialogResult.OK && !string.IsNullOrWhiteSpace(dlg.SelectedPath))
                {
                    storageDir = dlg.SelectedPath;
                    lblDirPath.Text = storageDir;
                    SaveConfig();
                }
            }
        }

        private void BtnOpenDir_Click(object sender, EventArgs e)
        {
            if (!Directory.Exists(storageDir)) Directory.CreateDirectory(storageDir);
            try { Process.Start("explorer.exe", storageDir); } catch { }
        }

        private void RunHiddenCmd(string args)
        {
            try
            {
                var psi = new ProcessStartInfo("cmd.exe", "/c " + args);
                psi.CreateNoWindow = true;
                psi.UseShellExecute = false;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                var p = Process.Start(psi);
                if (p != null) p.WaitForExit(3000);
            }
            catch { }
        }

        private void BtnMainAction_Click(object sender, EventArgs e)
        {
            if (isStarting || isStopping) return;

            if (isRunning)
                StopServer();
            else
                StartServer();
        }

        private void StartServer()
        {
            isStarting = true;
            startTimestamp = DateTime.Now;
            SetPill("启动中...", Color.FromArgb(254, 243, 199), Color.FromArgb(245, 158, 11), Color.FromArgb(180, 83, 9));
            btnMainAction.Enabled = false;
            btnMainAction.Text = "正在启动服务...";
            btnMainAction.Invalidate();
            btnChangeDir.Enabled = false;

            SaveConfig();

            ThreadPool.QueueUserWorkItem(_ => {
                if (IsPortInUse(PORT))
                {
                    RunHiddenCmd("for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :" + PORT + " ^| findstr LISTENING') do taskkill /f /pid %a >nul 2>&1");
                    Thread.Sleep(400);
                }

                try
                {
                    string pyw = FindPythonwExe();
                    var psi = new ProcessStartInfo(pyw, "\"" + daemonScript + "\"");
                    psi.WorkingDirectory = baseDir;
                    psi.CreateNoWindow = true;
                    psi.UseShellExecute = false;
                    psi.EnvironmentVariables["LABDROP_STORAGE_DIR"] = storageDir;
                    Process.Start(psi);
                }
                catch (Exception ex)
                {
                    this.BeginInvoke((Action)(() => {
                        isStarting = false;
                        MessageBox.Show("启动失败：" + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    }));
                }
            });
        }

        private void StopServer()
        {
            isStopping = true;
            SetPill("停止中...", Color.FromArgb(254, 226, 226), Color.FromArgb(239, 68, 68), Color.FromArgb(185, 28, 28));
            btnMainAction.Enabled = false;
            btnMainAction.Text = "正在停止...";
            btnMainAction.Invalidate();

            ThreadPool.QueueUserWorkItem(_ => {
                try
                {
                    var rt = ReadRuntime();
                    rt["status"] = "stopping";
                    File.WriteAllText(runtimeFile, json.Serialize(rt), Encoding.UTF8);
                }
                catch { }
                Thread.Sleep(400);
                RunHiddenCmd("taskkill /f /im cloudflared.exe >nul 2>&1");
                RunHiddenCmd("for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :" + PORT + " ^| findstr LISTENING') do taskkill /f /pid %a >nul 2>&1");
                try
                {
                    var rt = ReadRuntime();
                    rt["status"] = "stopped";
                    rt["public_status"] = "off";
                    rt["public_url"] = "";
                    File.WriteAllText(runtimeFile, json.Serialize(rt), Encoding.UTF8);
                }
                catch { }
                isStopping = false;
            });
        }

        private void SetPill(string text, Color bg, Color dot, Color fg)
        {
            statusPill.Text = text;
            statusPill.BgColor = bg;
            statusPill.DotColor = dot;
            statusPill.LabelColor = fg;
            statusPill.Invalidate();
        }

        private void StartPolling()
        {
            statusTimer = new System.Windows.Forms.Timer();
            statusTimer.Interval = 700;
            statusTimer.Tick += (s, e) => RefreshStatus();
            statusTimer.Start();
            RefreshStatus();
        }

        private void RefreshStatus()
        {
            if (isStopping) return;

            var rt = ReadRuntime();
            string status = GetStr(rt, "status");
            string pubStatus = GetStr(rt, "public_status");
            string pub = GetStr(rt, "public_url");
            string lan = GetStr(rt, "lan_url");
            bool alive = IsPortInUse(PORT);

            if (alive && status == "running")
            {
                isStarting = false;
                isRunning = true;
                currentLanUrl = lan;

                SetPill("运行中", Color.FromArgb(236, 253, 245), Color.FromArgb(16, 185, 129), Color.FromArgb(5, 150, 105));

                btnMainAction.Enabled = true;
                btnMainAction.Text = "停止服务";
                btnMainAction.NormalBg = Color.FromArgb(254, 242, 242);
                btnMainAction.HoverBg = Color.FromArgb(254, 226, 226);
                btnMainAction.TextColor = Color.FromArgb(220, 38, 38);
                btnMainAction.BorderColor = Color.FromArgb(254, 202, 202);
                btnMainAction.Invalidate();

                btnChangeDir.Enabled = false;

                lblLanUrl.Text = lan;
                lblLanUrl.ForeColor = Color.FromArgb(17, 24, 39);
                btnCopyLan.Enabled = true;
                btnOpenLan.Enabled = true;

                if (!enablePublic)
                {
                    currentPublicUrl = "";
                    lblPubUrl.Text = "公网访问已禁止";
                    lblPubUrl.ForeColor = Color.FromArgb(156, 163, 175);
                    btnCopyPub.Enabled = false;
                    btnOpenPub.Enabled = false;
                }
                else if (pubStatus == "on" && !string.IsNullOrEmpty(pub))
                {
                    currentPublicUrl = pub;
                    lblPubUrl.Text = pub;
                    lblPubUrl.ForeColor = Color.FromArgb(37, 99, 235);
                    btnCopyPub.Enabled = true;
                    btnOpenPub.Enabled = true;
                }
                else
                {
                    currentPublicUrl = "";
                    lblPubUrl.Text = "正在连接公网通道...";
                    lblPubUrl.ForeColor = Color.FromArgb(217, 119, 6);
                    btnCopyPub.Enabled = false;
                    btnOpenPub.Enabled = false;
                }
            }
            else if (isStarting)
            {
                if ((DateTime.Now - startTimestamp).TotalSeconds > 15)
                {
                    isStarting = false;
                    MessageBox.Show("启动超时，请重试。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }
            }
            else
            {
                isStarting = false;
                isRunning = false;
                currentPublicUrl = "";
                currentLanUrl = "";

                SetPill("已停止", Color.FromArgb(243, 244, 246), Color.FromArgb(156, 163, 175), Color.FromArgb(107, 114, 128));

                btnMainAction.Enabled = true;
                btnMainAction.Text = "启动网络U盘服务";
                btnMainAction.NormalBg = Color.FromArgb(37, 99, 235);
                btnMainAction.HoverBg = Color.FromArgb(29, 78, 216);
                btnMainAction.TextColor = Color.White;
                btnMainAction.BorderColor = Color.Transparent;
                btnMainAction.Invalidate();

                btnChangeDir.Enabled = true;

                lblLanUrl.Text = "服务未启动";
                lblLanUrl.ForeColor = Color.FromArgb(156, 163, 175);
                btnCopyLan.Enabled = false;
                btnOpenLan.Enabled = false;

                lblPubUrl.Text = enablePublic ? "启动服务后自动生成" : "公网访问已禁止";
                lblPubUrl.ForeColor = Color.FromArgb(156, 163, 175);
                btnCopyPub.Enabled = false;
                btnOpenPub.Enabled = false;
            }
        }
    }
}
