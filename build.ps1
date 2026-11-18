# LabDrop 一键构建脚本 (Windows)
# 自动下载官方 Python 3.12 嵌入式运行时，编译 LabDropManager.exe 并打包单文件 LabDrop-Setup.exe

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$BuildDir = Join-Path $Root "build"
$DistDir = Join-Path $Root "dist"
$PyEmbedDir = Join-Path $BuildDir "runtime-py"
$StageDir = Join-Path $BuildDir "payload"
$Csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"

if (-not (Test-Path $Csc)) {
    throw "未找到 .NET Framework 4.x 编译器: $Csc"
}

New-Item -ItemType Directory -Force -Path $BuildDir, $DistDir | Out-Null

# 1. 如无 app.ico 则生成
$IcoPath = Join-Path $Root "app.ico"
if (-not (Test-Path $IcoPath)) {
    Write-Host "[1/4] 生成 app.ico..."
    python (Join-Path $Root "make_icon.py")
}

# 2. 准备嵌入式 Python 3.12 运行时（目标机零依赖）
if (-not (Test-Path (Join-Path $PyEmbedDir "pythonw.exe"))) {
    Write-Host "[2/4] 下载 Python 3.12.8 嵌入式运行环境..."
    New-Item -ItemType Directory -Force -Path $PyEmbedDir | Out-Null
    $pyZip = Join-Path $BuildDir "python-embed.zip"
    curl.exe -L -s -o $pyZip https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip
    Expand-Archive -Path $pyZip -DestinationPath $PyEmbedDir -Force
    Remove-Item $pyZip -Force
}

# 3. 编译原生桌面管理软件 LabDropManager.exe
Write-Host "[3/4] 编译 LabDropManager.exe..."
$ManagerExe = Join-Path $BuildDir "LabDropManager.exe"
& $Csc /nologo /target:winexe /optimize+ /win32icon:$IcoPath /out:$ManagerExe `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll `
    (Join-Path $Root "LabDropManager.cs")

# 4. 打包单文件安装程序 LabDrop-Setup.exe
Write-Host "[4/4] 打包 LabDrop-Setup.exe..."
if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "uploads") | Out-Null
Copy-Item $ManagerExe $StageDir
foreach ($f in @("app.ico", "server.py", "daemon.py", "bore_tunnel.py")) {
    Copy-Item (Join-Path $Root $f) $StageDir
}
Copy-Item $PyEmbedDir (Join-Path $StageDir "runtime-py") -Recurse

$PayloadZip = Join-Path $BuildDir "payload.zip"
if (Test-Path $PayloadZip) { Remove-Item $PayloadZip -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($StageDir, $PayloadZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

$SetupExe = Join-Path $DistDir "LabDrop-Setup.exe"
& $Csc /nologo /target:winexe /optimize+ /win32icon:$IcoPath /resource:"$PayloadZip,payload.zip" /out:$SetupExe `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:Microsoft.CSharp.dll `
    (Join-Path $Root "LabDropSetup.cs")

$sizeMB = [math]::Round((Get-Item $SetupExe).Length / 1MB, 2)
Write-Host "✅ 构建成功！输出安装包: $SetupExe ($sizeMB MB)"
