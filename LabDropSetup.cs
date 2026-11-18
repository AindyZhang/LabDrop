using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace LabDropSetup
{
    static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        static void Main()
        {
            if (Environment.OSVersion.Version.Major >= 6)
                SetProcessDPIAware();
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SetupForm());
        }
    }

    public class RoundedBox : Panel
    {
        public int CornerRadius { get; set; }
        public Color FillColor { get; set; }
        public Color BorderColor { get; set; }

        public RoundedBox()
        {
            CornerRadius = 12;
            FillColor = Color.White;
            BorderColor = Color.FromArgb(229, 233, 240);
            DoubleBuffered = true;
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = MakePath(rect, CornerRadius))
            using (SolidBrush br = new SolidBrush(FillColor))
            using (Pen pen = new Pen(BorderColor, 1f))
            {
                e.Graphics.FillPath(br, path);
                if (BorderColor != Color.Transparent)
                    e.Graphics.DrawPath(pen, path);
            }
            base.OnPaint(e);
        }

        public static GraphicsPath MakePath(Rectangle r, int rad)
        {
            GraphicsPath p = new GraphicsPath();
            int d = rad * 2;
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }
    }

    public class FlatRoundedBtn : Control
    {
        public int CornerRadius { get; set; }
        public Color NormalBg { get; set; }
        public Color HoverBg { get; set; }
        public Color TextColor { get; set; }
        private bool hover = false;

        public FlatRoundedBtn()
        {
            CornerRadius = 9;
            NormalBg = Color.FromArgb(37, 99, 235);
            HoverBg = Color.FromArgb(29, 78, 216);
            TextColor = Color.White;
            Cursor = Cursors.Hand;
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;
        }

        protected override void OnMouseEnter(EventArgs e) { hover = true; Invalidate(); base.OnMouseEnter(e); }
        protected override void OnMouseLeave(EventArgs e) { hover = false; Invalidate(); base.OnMouseLeave(e); }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Color bg = !Enabled ? Color.FromArgb(203, 213, 225) : (hover ? HoverBg : NormalBg);
            Rectangle rect = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath path = RoundedBox.MakePath(rect, CornerRadius))
            using (SolidBrush br = new SolidBrush(bg))
                e.Graphics.FillPath(br, path);

            TextRenderer.DrawText(
                e.Graphics, Text, Font, new Rectangle(0, 0, Width, Height),
                Enabled ? TextColor : Color.White,
                TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter | TextFormatFlags.SingleLine
            );
        }
    }

    public class SmoothProgressBar : Control
    {
        private int val = 0;
        public int Value { get { return val; } set { val = Math.Max(0, Math.Min(100, value)); Invalidate(); } }

        public SmoothProgressBar()
        {
            DoubleBuffered = true;
            SetStyle(ControlStyles.SupportsTransparentBackColor | ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint, true);
            BackColor = Color.Transparent;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle track = new Rectangle(0, 0, Width - 1, Height - 1);
            using (GraphicsPath tp = RoundedBox.MakePath(track, Height / 2))
            using (SolidBrush tb = new SolidBrush(Color.FromArgb(226, 232, 240)))
                e.Graphics.FillPath(tb, tp);

            if (val > 0)
            {
                int fillW = Math.Max(Height, (int)(Width * val / 100.0));
                Rectangle fill = new Rectangle(0, 0, Math.Min(Width - 1, fillW), Height - 1);
                Color barColor = val >= 100 ? Color.FromArgb(16, 185, 129) : Color.FromArgb(37, 99, 235);
                using (GraphicsPath fp = RoundedBox.MakePath(fill, Height / 2))
                using (SolidBrush fb = new SolidBrush(barColor))
                    e.Graphics.FillPath(fb, fp);
            }
        }
    }

    public class SetupForm : Form
    {
        private Label lblPath, lblProgress;
        private string targetInstallDir, installedExePath = "";
        private FlatRoundedBtn btnBrowse, btnInstall;
        private CheckBox chkDesktop, chkStartMenu, chkLaunch;
        private SmoothProgressBar progressBar;
        private bool isInstalling = false, isFinished = false;

        public SetupForm()
        {
            targetInstallDir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "LabDrop"
            );
            InitializeUi();
        }

        private static void DrawYellowLightningLogo(Graphics g, int size)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Rectangle rect = new Rectangle(1, 1, size - 2, size - 2);
            using (GraphicsPath path = RoundedBox.MakePath(rect, Math.Max(4, size / 4)))
            using (LinearGradientBrush bg = new LinearGradientBrush(
                rect, Color.FromArgb(254, 224, 71), Color.FromArgb(245, 158, 11), LinearGradientMode.Vertical))
                g.FillPath(bg, path);

            float s = size;
            PointF[] bolt = new PointF[] {
                new PointF(0.56f * s, 0.14f * s),
                new PointF(0.24f * s, 0.54f * s),
                new PointF(0.49f * s, 0.54f * s),
                new PointF(0.42f * s, 0.86f * s),
                new PointF(0.76f * s, 0.44f * s),
                new PointF(0.51f * s, 0.44f * s)
            };
            using (SolidBrush wb = new SolidBrush(Color.White))
                g.FillPolygon(wb, bolt);
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
                return Icon.FromHandle(bmp.GetHicon());
            }
        }

        private void InitializeUi()
        {
            this.Text = "安装 LabDrop · 实验室网络U盘";
            this.ClientSize = new Size(468, 392);
            this.FormBorderStyle = FormBorderStyle.FixedSingle;
            this.MaximizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.BackColor = Color.FromArgb(245, 247, 250);
            this.Font = new Font("Microsoft YaHei UI", 9f);
            try { this.Icon = CreateVectorAppIcon(); } catch { }

            var pic = new Panel { Location = new Point(24, 24), Size = new Size(48, 48), BackColor = Color.Transparent };
            pic.Paint += (s, pe) => DrawYellowLightningLogo(pe.Graphics, 48);
            this.Controls.Add(pic);

            this.Controls.Add(new Label { Text = "LabDrop 实验室网络U盘", Font = new Font("Microsoft YaHei UI", 14.5f, FontStyle.Bold), ForeColor = Color.FromArgb(17, 24, 39), Location = new Point(84, 22), AutoSize = true });
            this.Controls.Add(new Label { Text = "免装 Python · 零依赖 · 一键部署至本机", Font = new Font("Microsoft YaHei UI", 8.5f), ForeColor = Color.FromArgb(107, 114, 128), Location = new Point(86, 51), AutoSize = true });

            var card = new RoundedBox { Location = new Point(24, 92), Size = new Size(420, 178) };
            this.Controls.Add(card);
            card.Controls.Add(new Label { Text = "安装位置", Font = new Font("Microsoft YaHei UI", 9f, FontStyle.Bold), ForeColor = Color.FromArgb(31, 41, 55), Location = new Point(18, 16), AutoSize = true });

            var pathPill = new RoundedBox { Location = new Point(18, 42), Size = new Size(314, 36), CornerRadius = 8, FillColor = Color.FromArgb(248, 250, 252), BorderColor = Color.FromArgb(241, 245, 249) };
            card.Controls.Add(pathPill);
            lblPath = new Label { Text = targetInstallDir, Font = new Font("Consolas", 9f), ForeColor = Color.FromArgb(71, 85, 105), Location = new Point(10, 0), Size = new Size(294, 36), TextAlign = ContentAlignment.MiddleLeft, AutoEllipsis = true };
            pathPill.Controls.Add(lblPath);

            btnBrowse = new FlatRoundedBtn { Text = "更改", CornerRadius = 8, Location = new Point(340, 42), Size = new Size(62, 36), NormalBg = Color.FromArgb(241, 245, 249), HoverBg = Color.FromArgb(226, 232, 240), TextColor = Color.FromArgb(51, 65, 85) };
            btnBrowse.Click += BtnBrowse_Click;
            card.Controls.Add(btnBrowse);

            chkDesktop = new CheckBox { Text = "创建桌面快捷方式（黄色闪电图标）", Checked = true, Location = new Point(20, 92), AutoSize = true, ForeColor = Color.FromArgb(55, 65, 81) };
            chkStartMenu = new CheckBox { Text = "添加到开始菜单", Checked = true, Location = new Point(20, 118), AutoSize = true, ForeColor = Color.FromArgb(55, 65, 81) };
            chkLaunch = new CheckBox { Text = "安装完成后立即打开软件", Checked = true, Location = new Point(20, 144), AutoSize = true, ForeColor = Color.FromArgb(55, 65, 81) };
            card.Controls.Add(chkDesktop);
            card.Controls.Add(chkStartMenu);
            card.Controls.Add(chkLaunch);

            lblProgress = new Label { Text = "准备就绪，点击下方按钮即可快速安装", Font = new Font("Microsoft YaHei UI", 8.5f), ForeColor = Color.FromArgb(107, 114, 128), Location = new Point(26, 286), Size = new Size(416, 18) };
            this.Controls.Add(lblProgress);
            progressBar = new SmoothProgressBar { Location = new Point(24, 308), Size = new Size(420, 8) };
            this.Controls.Add(progressBar);

            btnInstall = new FlatRoundedBtn { Text = "立即安装", CornerRadius = 10, Font = new Font("Microsoft YaHei UI", 10.5f, FontStyle.Bold), Location = new Point(24, 330), Size = new Size(420, 44) };
            btnInstall.Click += BtnInstall_Click;
            this.Controls.Add(btnInstall);
        }

        private void BtnBrowse_Click(object sender, EventArgs e)
        {
            using (var dlg = new FolderBrowserDialog { Description = "选择安装位置：", SelectedPath = targetInstallDir })
            {
                if (dlg.ShowDialog() == DialogResult.OK && !string.IsNullOrWhiteSpace(dlg.SelectedPath))
                {
                    string selected = dlg.SelectedPath;
                    if (!selected.EndsWith("LabDrop", StringComparison.OrdinalIgnoreCase))
                        selected = Path.Combine(selected, "LabDrop");
                    targetInstallDir = selected;
                    lblPath.Text = targetInstallDir;
                }
            }
        }

        private void BtnInstall_Click(object sender, EventArgs e)
        {
            if (isFinished)
            {
                if (chkLaunch.Checked && File.Exists(installedExePath))
                {
                    try { Process.Start(installedExePath); } catch { }
                }
                this.Close();
                return;
            }
            if (isInstalling) return;
            isInstalling = true;
            btnInstall.Enabled = false;
            btnInstall.Text = "正在安装...";
            btnBrowse.Enabled = false;
            bool d = chkDesktop.Checked, s = chkStartMenu.Checked;
            string dir = targetInstallDir;
            ThreadPool.QueueUserWorkItem(_ => DoInstall(dir, d, s));
        }

        private void UpdateProgress(int pct, string txt)
        {
            if (!this.IsDisposed)
                this.BeginInvoke((Action)(() => { progressBar.Value = pct; lblProgress.Text = txt; }));
        }

        private void RunHiddenCmd(string cmd)
        {
            try
            {
                var psi = new ProcessStartInfo("cmd.exe", "/c " + cmd) { CreateNoWindow = true, UseShellExecute = false, WindowStyle = ProcessWindowStyle.Hidden };
                var p = Process.Start(psi);
                if (p != null) p.WaitForExit(3000);
            }
            catch { }
        }

        private void CreateShortcut(string lnkPath, string targetExe, string workDir, string iconPath, string desc)
        {
            dynamic shell = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
            dynamic sc = shell.CreateShortcut(lnkPath);
            sc.TargetPath = targetExe;
            sc.WorkingDirectory = workDir;
            sc.IconLocation = iconPath + ", 0";
            sc.Description = desc;
            sc.Save();
        }

        private void DoInstall(string targetDir, bool makeDesktop, bool makeStartMenu)
        {
            try
            {
                UpdateProgress(6, "正在准备安装环境...");
                RunHiddenCmd("taskkill /f /im LabDropManager.exe >nul 2>&1");
                RunHiddenCmd("for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %a >nul 2>&1");
                Thread.Sleep(300);
                Directory.CreateDirectory(targetDir);

                UpdateProgress(15, "正在解压核心程序与内置运行环境...");
                using (Stream resStream = Assembly.GetExecutingAssembly().GetManifestResourceStream("payload.zip"))
                using (var archive = new ZipArchive(resStream, ZipArchiveMode.Read))
                {
                    int total = archive.Entries.Count, count = 0;
                    foreach (var entry in archive.Entries)
                    {
                        count++;
                        string destPath = Path.Combine(targetDir, entry.FullName);
                        string destDir = Path.GetDirectoryName(destPath);
                        if (!string.IsNullOrEmpty(destDir) && !Directory.Exists(destDir))
                            Directory.CreateDirectory(destDir);
                        if (!string.IsNullOrEmpty(entry.Name))
                            entry.ExtractToFile(destPath, true);
                        UpdateProgress(15 + (int)(count * 72.0 / Math.Max(1, total)), "正在安装：" + entry.Name);
                    }
                }

                UpdateProgress(89, "正在配置网页自传播安装包...");
                try
                {
                    string distDir = Path.Combine(targetDir, "dist");
                    Directory.CreateDirectory(distDir);
                    string selfCopy = Path.Combine(distDir, "LabDrop-Setup.exe");
                    if (!string.Equals(Path.GetFullPath(Application.ExecutablePath), Path.GetFullPath(selfCopy), StringComparison.OrdinalIgnoreCase))
                        File.Copy(Application.ExecutablePath, selfCopy, true);
                }
                catch { }

                installedExePath = Path.Combine(targetDir, "LabDropManager.exe");
                string icoPath = Path.Combine(targetDir, "app.ico");

                UpdateProgress(93, "正在注册协议与快捷方式...");
                using (var pKey = Registry.CurrentUser.CreateSubKey(@"Software\Classes\labdrop"))
                {
                    if (pKey != null)
                    {
                        pKey.SetValue("", "URL:LabDrop Network Disk");
                        pKey.SetValue("URL Protocol", "");
                        using (var cKey = pKey.CreateSubKey(@"shell\open\command"))
                            if (cKey != null) cKey.SetValue("", "\"" + installedExePath + "\" \"%1\"");
                    }
                }
                if (makeDesktop)
                    CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "实验室网络U盘.lnk"), installedExePath, targetDir, icoPath, "LabDrop 实验室网络U盘");
                if (makeStartMenu)
                {
                    string sm = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "LabDrop");
                    Directory.CreateDirectory(sm);
                    CreateShortcut(Path.Combine(sm, "实验室网络U盘.lnk"), installedExePath, targetDir, icoPath, "LabDrop 实验室网络U盘");
                }

                UpdateProgress(97, "正在注册卸载项...");
                string uninstallBat = Path.Combine(targetDir, "uninstall.bat");
                File.WriteAllText(uninstallBat,
                    "@echo off\r\nchcp 65001 >nul\r\n" +
                    "taskkill /f /im LabDropManager.exe >nul 2>&1\r\n" +
                    "for /f \"tokens=5\" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1\r\n" +
                    "del /f /q \"%USERPROFILE%\\Desktop\\实验室网络U盘.lnk\" >nul 2>&1\r\n" +
                    "rmdir /s /q \"%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\LabDrop\" >nul 2>&1\r\n" +
                    "reg delete \"HKCU\\Software\\Classes\\labdrop\" /f >nul 2>&1\r\n" +
                    "reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\LabDrop\" /f >nul 2>&1\r\n" +
                    "start /b \"\" cmd /c \"timeout /t 2 >nul & rmdir /s /q \\\"" + targetDir + "\\\"\"\r\nexit\r\n",
                    new UTF8Encoding(false));

                using (var key = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\LabDrop"))
                {
                    if (key != null)
                    {
                        key.SetValue("DisplayName", "LabDrop 实验室网络U盘");
                        key.SetValue("DisplayVersion", "2.7.0");
                        key.SetValue("Publisher", "LabDrop");
                        key.SetValue("DisplayIcon", icoPath);
                        key.SetValue("InstallLocation", targetDir);
                        key.SetValue("UninstallString", "\"" + uninstallBat + "\"");
                        key.SetValue("NoModify", 1, RegistryValueKind.DWord);
                        key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
                    }
                }

                UpdateProgress(100, "安装完成！点击“完成”即可开始使用。");
                this.BeginInvoke((Action)(() => {
                    isInstalling = false;
                    isFinished = true;
                    btnInstall.Text = "完成";
                    btnInstall.NormalBg = Color.FromArgb(16, 185, 129);
                    btnInstall.HoverBg = Color.FromArgb(5, 150, 105);
                    btnInstall.Enabled = true;
                    btnInstall.Invalidate();
                }));
            }
            catch (Exception ex)
            {
                this.BeginInvoke((Action)(() => {
                    isInstalling = false;
                    btnInstall.Enabled = true;
                    btnInstall.Text = "立即安装";
                    btnBrowse.Enabled = true;
                    lblProgress.Text = "安装失败：" + ex.Message;
                    MessageBox.Show("安装失败：\n" + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }));
            }
        }
    }
}
