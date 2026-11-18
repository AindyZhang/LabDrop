# ⚡ LabDrop

**English** | [简体中文](README_ZH.md)

> Turn any folder on your Windows PC into an instant **LAN & Public Web USB Drive**.  
> Zero setup, no login required, drag-and-drop full folder trees, and one-click native Windows Explorer mounting.

![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-2563eb)
![License](https://img.shields.io/badge/License-MIT-10b981)
![Zero Dependency](https://img.shields.io/badge/Runtime-Standalone%20(~10.6%20MB)-f59e0b)

---

## ✨ Features

* **Clean, Modern Desktop Controller**: Minimalist rounded-card native Windows UI with one-click Start/Stop and **zero console windows**. Closing the manager keeps the server running silently in the background.
* **Any Folder as a Network USB Drive**: Pick any local directory or drive as your shared storage. Multiple PCs on the same LAN each get their own independent URL — just like having multiple USB drives.
* **Full Folder Upload & Download**:
  * Drag and drop **individual files or nested multi-level folders** while preserving the full directory tree, complete with upload progress, cancel, and one-click retry on network drops.
  * Streamed **Folder ZIP Download** (preserves the outer folder structure with low memory footprint via disk spooling and smart store-mode for pre-compressed media).
  * Built-in **WebDAV server** + custom `labdrop://` URL protocol: click **"Open as Local Drive"** on the web page to pop open a native Windows File Explorer window and copy/paste entire folders without zipping.
* **Hot-Swappable Public Access Toggle**: Includes a pure-Python TCP tunnel client (`bore.pub`) with a sleek toggle switch in the controller — turn public internet access ON or OFF anytime without interrupting LAN transfers.
* **Multi-User Concurrency & Simultaneous Up/Down**: Multi-threaded HTTP server (`ThreadingHTTPServer`), atomic temp-file writes to prevent partial reads or file-lock collisions, and hidden-iframe downloads so simultaneous uploads never abort (even on iPad/iPhone Safari).
* **Zero-Dependency Self-Propagating Installer**: `LabDrop-Setup.exe` (~10.6 MB) bundles an embedded Python 3.12 runtime — no Python or admin privileges required on target machines. Visitors can download the installer and user guide directly from the web UI footer.
* **Built-in Update Check**: Automatically checks GitHub Releases (read-only) for new versions and lets users download the latest `LabDrop-Setup.exe` in one click while keeping existing folders and settings intact.

---

## 🔒 Privacy & Local-First Guarantee

* **100% Local Storage**: All files and folders stay strictly on your own hard drive — **nothing is ever uploaded to any cloud storage or third-party database**.
* **Zero Telemetry / Zero Tracking**: LabDrop collects no analytics, no personal info, and no usage logs. The built-in update checker performs a single read-only `GET` request to the public GitHub Releases API to compare version numbers.
* **Full Control Over Exposure**: Keep the **Public Access** switch OFF to confine access strictly to your local LAN/Wi-Fi.

---

## 🚀 Quick Start

1. Download the latest **`LabDrop-Setup.exe`** from the **[Releases](https://github.com/AindyZhang/LabDrop/releases)** page.
2. Run the installer and click **Install** (takes ~3 seconds, creates a yellow lightning desktop shortcut).
3. Launch **LabDrop** from your desktop, pick any folder to share, and click **Start**.
4. Share the **LAN URL** (blazing fast over the same Wi-Fi/Ethernet) or toggle **Public Access** ON to share across the internet.

---

## 🛠️ Build from Source

No third-party Python packages or external build tools required — it compiles cleanly using Windows' built-in `.NET Framework 4.x` (`csc.exe`):

```powershell
.\build.ps1
```

The standalone installer will be generated at `dist\LabDrop-Setup.exe`.

---

## 📂 Project Structure

| File | Description |
| :--- | :--- |
| `server.py` | Multi-threaded HTTP + WebDAV server, responsive web UI, and built-in online guide |
| `daemon.py` | Silent background daemon managing server lifecycle and live public-tunnel toggling |
| `bore_tunnel.py` | Pure-Python standard-library TCP tunnel client for `bore.pub` |
| `LabDropManager.cs` | Native WinForms minimalist control center & `labdrop://` protocol handler |
| `LabDropSetup.cs` | Single-file Windows graphical installer with self-propagation & uninstaller registration |
| `make_icon.py` | Pure-Python generator for the multi-resolution yellow lightning icon (`app.ico`) |
| `build.ps1` | One-click automated Windows build & packaging script |

---

## 📄 License

Released under the [MIT License](LICENSE).
