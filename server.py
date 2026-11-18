# -*- coding: utf-8 -*-
"""
实验室极简网络U盘 (LabDrop) - 核心服务
原生 Python 3 标准库，支持多级目录、拖拽/多选上传文件及整个文件夹、文件夹ZIP打包下载。
"""

import os
import sys
import io
import uuid
import json
import socket
import shutil
import zipfile
import tempfile
import urllib.parse
from email.utils import formatdate
from xml.sax.saxutils import escape as xml_escape
from datetime import datetime
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

class LabDropServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

# 默认端口与默认存储目录
PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORAGE_DIR = os.path.join(BASE_DIR, "uploads")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"storage_dir": DEFAULT_STORAGE_DIR, "port": PORT}

def get_storage_dir():
    # 优先读取环境变量，再读配置文件
    env_dir = os.environ.get("LABDROP_STORAGE_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    cfg = load_config()
    s_dir = cfg.get("storage_dir", DEFAULT_STORAGE_DIR)
    os.makedirs(s_dir, exist_ok=True)
    return os.path.abspath(s_dir)

def get_local_ip():
    """获取本机真实物理局域网 IPv4 地址（排除虚拟网卡与代理网卡）"""
    try:
        ips = [
            info[4][0]
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            if not info[4][0].startswith(('127.', '169.254.', '198.18.'))
        ]
        for ip in ips:
            if ip.startswith(('192.168.', '10.', '172.')):
                return ip
        if ips:
            return ips[0]
    except Exception:
        pass
    return "127.0.0.1"

def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def resolve_safe_path(base_dir, sub_path):
    """安全解析子路径，严格禁止路径穿越离开共享目录"""
    clean_sub = sub_path.replace('\\', '/').strip('/')
    target = os.path.abspath(os.path.join(base_dir, clean_sub))
    base_abs = os.path.abspath(base_dir)
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise ValueError("非法访问：路径越界")
    return target

class LabDropHandler(BaseHTTPRequestHandler):
    timeout = 30

    def log_message(self, format, *args):
        # 避免在 pythonw 无控制台环境下 sys.stderr 为 None 导致写入日志时崩溃！
        if sys.stderr is not None:
            try:
                super().log_message(format, *args)
            except Exception:
                pass

    def send_json(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/webdav" or parsed.path.startswith("/webdav/"):
            self.handle_webdav_get(parsed.path, head_only=True)
        else:
            self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.handle_index()
        elif path == "/guide":
            self.handle_guide()
        elif path == "/download-installer":
            self.handle_download_installer()
        elif path == "/api/info":
            self.handle_info()
        elif path == "/api/files":
            self.handle_list_files(parsed.query)
        elif path == "/api/folder-manifest":
            self.handle_folder_manifest(parsed.query)
        elif path == "/api/mount-script":
            self.handle_mount_script()
        elif path.startswith("/download/"):
            self.handle_download(path[len("/download/"):])
        elif path.startswith("/download-zip/"):
            self.handle_download_zip(path[len("/download-zip/"):])
        elif path == "/webdav" or path.startswith("/webdav/"):
            self.handle_webdav_get(path, head_only=False)
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    # ==================== WebDAV 网络磁盘协议支持 ====================
    def _webdav_target_path(self, req_path):
        sub = req_path[len("/webdav"):] if req_path.startswith("/webdav") else req_path
        sub = urllib.parse.unquote(sub).strip("/")
        return resolve_safe_path(get_storage_dir(), sub)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("DAV", "1, 2")
        self.send_header("MS-Author-Via", "DAV")
        self.send_header("Allow", "OPTIONS, GET, HEAD, POST, PUT, DELETE, PROPFIND, PROPPATCH, MKCOL, COPY, MOVE, LOCK, UNLOCK")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _build_propfind_item(self, href, abs_path):
        st = os.stat(abs_path)
        is_dir = os.path.isdir(abs_path)
        mtime = formatdate(st.st_mtime, usegmt=True)
        if is_dir:
            if not href.endswith("/"):
                href += "/"
            res_type = "<D:collection/>"
            size_xml = ""
        else:
            res_type = ""
            size_xml = f"<D:getcontentlength>{st.st_size}</D:getcontentlength>"
        name = xml_escape(os.path.basename(abs_path) or "webdav")
        return (
            f"<D:response>"
            f"<D:href>{xml_escape(href)}</D:href>"
            f"<D:propstat><D:prop>"
            f"<D:displayname>{name}</D:displayname>"
            f"<D:resourcetype>{res_type}</D:resourcetype>"
            f"{size_xml}"
            f"<D:getlastmodified>{mtime}</D:getlastmodified>"
            f"</D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>"
            f"</D:response>"
        )

    def do_PROPFIND(self):
        parsed = urllib.parse.urlparse(self.path)
        req_path = parsed.path
        # 消耗客户端可选 XML 请求体
        cl = int(self.headers.get("Content-Length", 0))
        if cl > 0:
            self.rfile.read(cl)

        try:
            target = self._webdav_target_path(req_path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not os.path.exists(target):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        depth = self.headers.get("Depth", "1").lower()
        base_href = req_path if req_path.startswith("/webdav") else "/webdav/"
        if os.path.isdir(target) and not base_href.endswith("/"):
            base_href += "/"

        items = [self._build_propfind_item(base_href, target)]
        if os.path.isdir(target) and depth != "0":
            try:
                for entry in os.scandir(target):
                    child_href = base_href + urllib.parse.quote(entry.name)
                    if entry.is_dir():
                        child_href += "/"
                    items.append(self._build_propfind_item(child_href, entry.path))
            except Exception:
                pass

        xml_body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<D:multistatus xmlns:D="DAV:">'
            + "".join(items)
            + "</D:multistatus>"
        ).encode("utf-8")

        self.send_response(207, "Multi-Status")
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(xml_body)))
        self.end_headers()
        self.wfile.write(xml_body)

    def handle_webdav_get(self, req_path, head_only=False):
        try:
            target = self._webdav_target_path(req_path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        if not os.path.exists(target):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        if os.path.isdir(target):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        st = os.stat(target)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(st.st_size))
        self.send_header("Last-Modified", formatdate(st.st_mtime, usegmt=True))
        self.end_headers()
        if head_only:
            return
        with open(target, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            target = self._webdav_target_path(parsed.path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return

        existed = os.path.exists(target)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        cl = int(self.headers.get("Content-Length", 0))
        read_bytes = 0
        with open(target, "wb") as f:
            while read_bytes < cl:
                chunk = self.rfile.read(min(64 * 1024, cl - read_bytes))
                if not chunk:
                    break
                f.write(chunk)
                read_bytes += len(chunk)

        self.send_response(HTTPStatus.NO_CONTENT if existed else HTTPStatus.CREATED)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_MKCOL(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            target = self._webdav_target_path(parsed.path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
            return
        os.makedirs(target, exist_ok=True)
        self.send_response(HTTPStatus.CREATED)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            target = self._webdav_target_path(parsed.path)
            if target == get_storage_dir():
                self.send_error(HTTPStatus.FORBIDDEN, "Cannot delete root")
                return
            if os.path.isdir(target):
                shutil.rmtree(target)
            elif os.path.isfile(target):
                os.remove(target)
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_MOVE(self):
        parsed = urllib.parse.urlparse(self.path)
        dest_hdr = self.headers.get("Destination", "")
        dest_path = urllib.parse.urlparse(dest_hdr).path
        try:
            src = self._webdav_target_path(parsed.path)
            dst = self._webdav_target_path(dest_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            self.send_response(HTTPStatus.CREATED)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_COPY(self):
        parsed = urllib.parse.urlparse(self.path)
        dest_hdr = self.headers.get("Destination", "")
        dest_path = urllib.parse.urlparse(dest_hdr).path
        try:
            src = self._webdav_target_path(parsed.path)
            dst = self._webdav_target_path(dest_path)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            self.send_response(HTTPStatus.CREATED)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_LOCK(self):
        cl = int(self.headers.get("Content-Length", 0))
        if cl > 0:
            self.rfile.read(cl)
        token = "opaquelocktoken:labdrop-lock"
        body = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<D:prop xmlns:D="DAV:"><D:lockdiscovery><D:activelock>'
            '<D:locktype><D:write/></D:locktype><D:lockscope><D:exclusive/></D:lockscope>'
            '<D:depth>0</D:depth><D:timeout>Second-3600</D:timeout>'
            f'<D:locktoken><D:href>{token}</D:href></D:locktoken>'
            '</D:activelock></D:lockdiscovery></D:prop>'
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Lock-Token", f"<{token}>")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_UNLOCK(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_PROPPATCH(self):
        cl = int(self.headers.get("Content-Length", 0))
        if cl > 0:
            self.rfile.read(cl)
        body = '<?xml version="1.0" encoding="utf-8"?><D:multistatus xmlns:D="DAV:"></D:multistatus>'.encode("utf-8")
        self.send_response(207, "Multi-Status")
        self.send_header("Content-Type", "application/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_mount_script(self):
        """生成一键挂载网络U盘为本地磁盘并直接打开资源管理器的 Windows 脚本"""
        host_hdr = self.headers.get("Host", f"{get_local_ip()}:{PORT}")
        if ":" in host_hdr:
            host_only, port_str = host_hdr.rsplit(":", 1)
        else:
            host_only, port_str = host_hdr, "80"
        unc_path = f"\\\\{host_only}@{port_str}\\DavWWWRoot\\webdav"
        bat = (
            "@echo off\r\n"
            "title Connect LabDrop Disk\r\n"
            "echo Connecting to LabDrop Network Disk...\r\n"
            "net start WebClient >nul 2>&1\r\n"
            f"explorer.exe \"{unc_path}\"\r\n"
            "exit\r\n"
        ).encode("ascii")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", 'attachment; filename="Open_LabDrop_Disk.bat"')
        self.send_header("Content-Length", str(len(bat)))
        self.end_headers()
        self.wfile.write(bat)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            self.handle_upload(parsed.query)
        elif path == "/api/mkdir":
            self.handle_mkdir()
        elif path == "/api/delete":
            self.handle_delete()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def handle_info(self):
        ip = get_local_ip()
        storage_dir = get_storage_dir()
        self.send_json({
            "ip": ip,
            "port": PORT,
            "url": f"http://{ip}:{PORT}",
            "storage_dir": storage_dir
        })

    def handle_list_files(self, query_str):
        params = urllib.parse.parse_qs(query_str)
        req_dir = params.get("dir", [""])[0]
        storage_dir = get_storage_dir()

        try:
            current_abs = resolve_safe_path(storage_dir, req_dir)
        except ValueError:
            self.send_json({"error": "路径无效"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not os.path.exists(current_abs):
            self.send_json({"error": "文件夹不存在"}, status=HTTPStatus.NOT_FOUND)
            return

        # 计算相对路径与面包屑
        rel_current = os.path.relpath(current_abs, storage_dir).replace('\\', '/')
        if rel_current == ".":
            rel_current = ""

        breadcrumbs = [{"name": "U盘根目录", "path": ""}]
        if rel_current:
            parts = rel_current.split('/')
            acc = ""
            for p in parts:
                acc = f"{acc}/{p}" if acc else p
                breadcrumbs.append({"name": p, "path": acc})

        dirs = []
        files = []
        try:
            for entry in os.scandir(current_abs):
                if entry.name.startswith(".uploading_") and entry.name.endswith(".tmp"):
                    continue
                stat = entry.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                rel_path = os.path.relpath(entry.path, storage_dir).replace('\\', '/')
                if entry.is_dir():
                    dirs.append({
                        "name": entry.name,
                        "path": rel_path,
                        "mtime": mtime,
                        "timestamp": stat.st_mtime
                    })
                elif entry.is_file():
                    files.append({
                        "name": entry.name,
                        "path": rel_path,
                        "size": stat.st_size,
                        "size_human": format_size(stat.st_size),
                        "mtime": mtime,
                        "timestamp": stat.st_mtime
                    })
            # 排序：最新优先
            dirs.sort(key=lambda x: x["name"].lower())
            files.sort(key=lambda x: x["timestamp"], reverse=True)
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        self.send_json({
            "current_dir": rel_current,
            "breadcrumbs": breadcrumbs,
            "dirs": dirs,
            "files": files
        })

    def handle_upload(self, query_str):
        params = urllib.parse.parse_qs(query_str)
        # 支持相对多级路径（用于整个文件夹上传）
        rel_path = params.get("relpath", [""])[0]
        if not rel_path:
            rel_path = self.headers.get("X-Relative-Path", "")
        rel_path = urllib.parse.unquote(rel_path).strip()

        if not rel_path:
            # 回退到单个文件名
            raw_name = params.get("filename", [""])[0] or self.headers.get("X-Filename", "")
            rel_path = urllib.parse.unquote(raw_name).strip()

        if not rel_path:
            self.send_json({"error": "缺少文件名或路径"}, status=HTTPStatus.BAD_REQUEST)
            return

        storage_dir = get_storage_dir()
        try:
            target_file = resolve_safe_path(storage_dir, rel_path)
        except ValueError:
            self.send_json({"error": "非法上传路径"}, status=HTTPStatus.FORBIDDEN)
            return

        # 确保父文件夹自动存在
        parent_dir = os.path.dirname(target_file)
        os.makedirs(parent_dir, exist_ok=True)

        # 使用独立临时文件流式写入，避免覆盖/损坏同名正在下载的文件，且不提前暴露半成品
        tmp_file = os.path.join(parent_dir, f".uploading_{uuid.uuid4().hex}.tmp")
        content_len = int(self.headers.get("Content-Length", 0))
        bytes_read = 0
        chunk_size = 64 * 1024
        try:
            with open(tmp_file, "wb") as f:
                while bytes_read < content_len:
                    to_read = min(chunk_size, content_len - bytes_read)
                    chunk = self.rfile.read(to_read)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_read += len(chunk)

            if content_len > 0 and bytes_read < content_len:
                raise IOError("客户端连接提前中断")

            # 原子落位；若目标同名文件正被其他人下载锁定，自动加序号保存不报错
            final_path = target_file
            try:
                os.replace(tmp_file, final_path)
            except PermissionError:
                base_name, ext = os.path.splitext(target_file)
                idx = 1
                while True:
                    cand = f"{base_name}_{idx}{ext}"
                    if not os.path.exists(cand):
                        os.replace(tmp_file, cand)
                        final_path = cand
                        break
                    idx += 1

            final_rel = os.path.relpath(final_path, storage_dir).replace('\\', '/')
            self.send_json({"success": True, "path": final_rel, "size": bytes_read})
        except Exception as e:
            if os.path.exists(tmp_file):
                try: os.remove(tmp_file)
                except Exception: pass
            try:
                self.send_json({"error": f"写入失败: {str(e)}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            except Exception:
                pass

    def handle_mkdir(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(content_len).decode("utf-8"))
            parent_dir = data.get("parent_dir", "").strip()
            folder_name = data.get("name", "").strip()

            if not folder_name or "/" in folder_name or "\\" in folder_name:
                self.send_json({"error": "文件夹名称不合法"}, status=HTTPStatus.BAD_REQUEST)
                return

            storage_dir = get_storage_dir()
            target_path = resolve_safe_path(storage_dir, f"{parent_dir}/{folder_name}")
            os.makedirs(target_path, exist_ok=True)
            self.send_json({"success": True})
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_delete(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(content_len).decode("utf-8"))
            rel_path = data.get("path", "").strip()

            storage_dir = get_storage_dir()
            target = resolve_safe_path(storage_dir, rel_path)

            if target == storage_dir:
                self.send_json({"error": "不能删除根目录"}, status=HTTPStatus.FORBIDDEN)
                return

            if os.path.isdir(target):
                shutil.rmtree(target)
                self.send_json({"success": True})
            elif os.path.isfile(target):
                os.remove(target)
                self.send_json({"success": True})
            else:
                self.send_json({"error": "文件或文件夹不存在"}, status=HTTPStatus.NOT_FOUND)
        except Exception as e:
            self.send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_download(self, raw_rel_path):
        rel_path = urllib.parse.unquote(raw_rel_path)
        storage_dir = get_storage_dir()

        try:
            target = resolve_safe_path(storage_dir, rel_path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "非法路径")
            return

        if not os.path.isfile(target):
            self.send_error(HTTPStatus.NOT_FOUND, "文件不存在")
            return

        filename = os.path.basename(target)
        file_size = os.path.getsize(target)
        encoded_name = urllib.parse.quote(filename)

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{encoded_name}"; filename*=UTF-8\'\'{encoded_name}')
        self.send_header("Content-Length", str(file_size))
        self.end_headers()

        with open(target, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def handle_folder_manifest(self, query_str):
        """递归获取文件夹内所有文件清单与目录列表，支持前端直接下载整个文件夹"""
        params = urllib.parse.parse_qs(query_str)
        req_path = params.get("path", [""])[0]
        storage_dir = get_storage_dir()

        try:
            target = resolve_safe_path(storage_dir, req_path)
        except ValueError:
            self.send_json({"error": "非法路径"}, status=HTTPStatus.FORBIDDEN)
            return

        if not os.path.isdir(target):
            self.send_json({"error": "文件夹不存在"}, status=HTTPStatus.NOT_FOUND)
            return

        folder_name = os.path.basename(target) or "U盘根目录"
        file_list = []
        dir_list = []
        for root, dirs, files in os.walk(target):
            for d in dirs:
                full_d = os.path.join(root, d)
                rel_in_folder = os.path.relpath(full_d, target).replace('\\', '/')
                dir_list.append(rel_in_folder)
            for f in files:
                full_f = os.path.join(root, f)
                rel_in_folder = os.path.relpath(full_f, target).replace('\\', '/')
                rel_from_storage = os.path.relpath(full_f, storage_dir).replace('\\', '/')
                file_list.append({
                    "name": f,
                    "rel_in_folder": rel_in_folder,
                    "download_path": rel_from_storage,
                    "size": os.path.getsize(full_f)
                })

        self.send_json({
            "folder_name": folder_name,
            "dirs": dir_list,
            "files": file_list
        })

    def handle_download_zip(self, raw_rel_path):
        """将整个文件夹流式打包为 zip 供用户一键下载（支持超大文件夹不爆内存）"""
        rel_path = urllib.parse.unquote(raw_rel_path)
        storage_dir = get_storage_dir()

        try:
            target = resolve_safe_path(storage_dir, rel_path)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "非法路径")
            return

        if not os.path.isdir(target):
            self.send_error(HTTPStatus.NOT_FOUND, "文件夹不存在")
            return

        folder_name = os.path.basename(target) or "U盘资料"
        encoded_name = urllib.parse.quote(f"{folder_name}.zip")

        # 常见已压缩格式跳过二次压缩，打包速度提升 5~10 倍
        no_compress_ext = {'.zip', '.rar', '.7z', '.gz', '.bz2', '.xz', '.mp4', '.mkv', '.avi', '.mov', '.jpg', '.jpeg', '.png', '.webp', '.pdf', '.exe', '.msi'}
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(prefix="labdrop_", suffix=".zip")
            os.close(fd)
            with zipfile.ZipFile(tmp_path, mode="w", allowZip64=True) as zf:
                prefix_dir = os.path.basename(target) if target != storage_dir else ""
                for root, dirs, files in os.walk(target):
                    rel_root = os.path.relpath(root, target).replace('\\', '/')
                    # 保留空目录
                    if not dirs and not files:
                        if rel_root == '.':
                            if prefix_dir:
                                zf.writestr(prefix_dir + '/', b'')
                        else:
                            arc_dir = f"{prefix_dir}/{rel_root}/" if prefix_dir else f"{rel_root}/"
                            zf.writestr(arc_dir, b'')
                    for f in files:
                        if f.startswith(".uploading_") and f.endswith(".tmp"):
                            continue
                        full_p = os.path.join(root, f)
                        rel_f = os.path.relpath(full_p, target).replace('\\', '/')
                        arcname = f"{prefix_dir}/{rel_f}" if prefix_dir else rel_f
                        ext = os.path.splitext(f)[1].lower()
                        comp = zipfile.ZIP_STORED if ext in no_compress_ext else zipfile.ZIP_DEFLATED
                        zf.write(full_p, arcname, compress_type=comp)

            zip_size = os.path.getsize(tmp_path)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="{encoded_name}"; filename*=UTF-8\'\'{encoded_name}')
            self.send_header("Content-Length", str(zip_size))
            self.end_headers()

            with open(tmp_path, "rb") as f:
                while True:
                    chunk = f.read(64 * 1024)
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    def handle_index(self):
        html = get_html_page()
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_guide(self):
        """在线打开精美版使用说明书（电脑/手机/iPad 浏览器直看）"""
        body = get_guide_html().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_download_installer(self):
        """流式下载 LabDrop-Setup.exe 安装包（自动探测 dist 目录及上级目录，支持无限自传播）"""
        candidates = [
            os.path.join(BASE_DIR, "dist", "LabDrop-Setup.exe"),
            os.path.join(BASE_DIR, "LabDrop-Setup.exe"),
            os.path.join(os.path.dirname(BASE_DIR), "LabDrop-Setup.exe"),
        ]
        installer_path = None
        for c in candidates:
            if os.path.isfile(c):
                installer_path = c
                break

        if not installer_path:
            self.send_error(HTTPStatus.NOT_FOUND, "未找到安装包 LabDrop-Setup.exe")
            return

        file_size = os.path.getsize(installer_path)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", 'attachment; filename="LabDrop-Setup.exe"')
        self.send_header("Content-Length", str(file_size))
        self.end_headers()

        with open(installer_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

def get_guide_html():
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>⚡ LabDrop 实验室网络U盘 · 使用说明书</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: "Microsoft YaHei UI", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7fa; color: #1e293b; line-height: 1.75; padding: 28px 16px;
    }
    .doc {
      max-width: 780px; margin: 0 auto; background: #fff; border-radius: 16px;
      padding: 36px 40px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.06); border: 1px solid #e5e9f0;
    }
    .hero { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; padding-bottom: 22px; border-bottom: 1px solid #f1f5f9; margin-bottom: 24px; }
    .hero-left { display: flex; align-items: center; gap: 14px; }
    .logo {
      width: 48px; height: 48px; border-radius: 12px; flex-shrink: 0;
      background: linear-gradient(180deg, #fde047 0%, #f59e0b 100%);
      display: flex; align-items: center; justify-content: center; font-size: 26px; color: #fff;
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.28);
    }
    .hero h1 { font-size: 22px; color: #0f172a; }
    .hero p { font-size: 13px; color: #64748b; margin-top: 2px; }
    .top-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn {
      display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px;
      font-size: 13px; font-weight: 600; text-decoration: none; cursor: pointer; border: none; transition: 0.2s;
    }
    .btn-primary { background: #2563eb; color: #fff; }
    .btn-primary:hover { background: #1d4ed8; }
    .btn-secondary { background: #f1f5f9; color: #334155; }
    .btn-secondary:hover { background: #e2e8f0; }
    h2 { font-size: 17px; color: #0f172a; margin: 26px 0 10px; }
    h3 { font-size: 14.5px; color: #1e293b; margin: 14px 0 6px; }
    p, li { font-size: 14px; color: #334155; }
    ul, ol { padding-left: 20px; margin: 8px 0 12px; }
    li { margin-bottom: 6px; }
    code {
      background: #f1f5f9; color: #2563eb; padding: 2px 6px; border-radius: 5px;
      font-family: Consolas, monospace; font-size: 13px;
    }
    .tip {
      background: #eff6ff; border-left: 4px solid #2563eb; padding: 12px 16px;
      border-radius: 0 8px 8px 0; margin: 12px 0; font-size: 13.5px; color: #1e3a8a;
    }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin: 12px 0; }
    .mini-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }
    .mini-card strong { display: block; color: #0f172a; margin-bottom: 4px; font-size: 14px; }
    .mini-card span { font-size: 13px; color: #64748b; }
    .faq-item { background: #f8fafc; border-radius: 10px; padding: 14px 18px; margin-bottom: 10px; border: 1px solid #edf2f7; }
    .faq-q { font-weight: 700; color: #0f172a; margin-bottom: 4px; font-size: 14px; }
    .faq-a { font-size: 13.5px; color: #475569; }
    @media (max-width: 600px) { .doc { padding: 22px 18px; } }
  </style>
</head>
<body>
  <div class="doc">
    <div class="hero">
      <div class="hero-left">
        <div class="logo">⚡</div>
        <div>
          <h1>LabDrop 实验室网络U盘 · 使用说明书</h1>
          <p>把任意一台 Windows 电脑变成共享“网络U盘”，免插拔、免登录</p>
        </div>
      </div>
      <div class="top-actions">
        <a class="btn btn-secondary" href="https://github.com/AindyZhang/LabDrop" target="_blank">⭐ GitHub</a>
        <a class="btn btn-primary" href="/download-installer" download="LabDrop-Setup.exe">⬇ 下载安装软件</a>
        <a class="btn btn-secondary" href="/">← 返回 U 盘</a>
      </div>
    </div>

    <h2>一、如何把自己的电脑变成“网络U盘”？（仅需 3 步）</h2>
    <div class="tip">
      <strong>零环境门槛：</strong>安装包已自带全部运行环境，目标电脑<strong>不需要安装 Python</strong>，也<strong>不需要管理员权限</strong>，直接双击即可安装。
    </div>

    <h3>第 1 步：一键安装</h3>
    <ol>
      <li>点击本页面上方 <strong>【⬇ 下载安装软件】</strong> 获取 <code>LabDrop-Setup.exe</code> 并双击运行；</li>
      <li>保持默认安装位置（或点“更改”自选目录），点击 <strong>【立即安装】</strong>；</li>
      <li>等待约 3 秒进度条走完，点击 <strong>【完成】</strong>，桌面会自动生成 <strong>黄色闪电图标「实验室网络U盘」</strong>。</li>
    </ol>

    <h3>第 2 步：选择 U 盘文件夹并启动</h3>
    <ol>
      <li>双击桌面 <strong>黄色闪电图标</strong> 打开管理控制中心；</li>
      <li>点击 <strong>【更改目录】</strong>，选择电脑里要当作“U盘”的任意文件夹；</li>
      <li>点击蓝色主按钮 <strong>【启动网络U盘服务】</strong>，右上角状态变为绿色 <strong>● 运行中</strong> 即启动成功。</li>
    </ol>

    <h3>第 3 步：把网址发给同学或自己手机</h3>
    <ul>
      <li><strong>实验室 / 同一 Wi-Fi 下（推荐）</strong>：点击“局域网访问”旁的 <strong>【复制】</strong>，把 <code>http://192.168.x.x:8000</code> 发到群里。内网千兆直传，几百 MB 大文件几秒传完！</li>
      <li><strong>校外 / 手机流量访问</strong>：打开界面里的 <strong>“公网访问”滑动开关</strong>，等 2~3 秒生成公网地址，复制发给对方即可。平时仅内网用时可关闭公网开关，更安全。</li>
    </ul>

    <h2>二、大家拿到网址后怎么用？（电脑 / 手机 / iPad 通用）</h2>
    <div class="card-grid">
      <div class="mini-card">
        <strong>📤 上传文件 / 整个文件夹</strong>
        <span>把单个文件或整个多层文件夹拖进网页虚线框，自动原样保留目录结构，支持中断一键重试。</span>
      </div>
      <div class="mini-card">
        <strong>📦 打包下载整个文件夹</strong>
        <span>点击文件夹旁的 <code>下载 (.zip)</code>，自动保留外层文件夹与全部子目录，解压不散落。</span>
      </div>
      <div class="mini-card">
        <strong>💻 像真 U 盘一样免压缩拷贝</strong>
        <span>点击绿色按钮 <code>像真U盘一样打开</code>，直接弹出 Windows 文件夹窗口，Ctrl+C/V 拷贝整文件夹！</span>
      </div>
    </div>

    <h2>三、日常使用贴心特性</h2>
    <ul>
      <li><strong>关闭管理窗口不影响服务</strong>：启动后可以直接关闭控制中心窗口，服务器在后台无黑框持续运行；随时重开桌面图标即可管理或停止。</li>
      <li><strong>多台电脑 = 多个独立 U 盘</strong>：同一局域网下每台电脑装上后自动拥有各自独立的网址和文件夹，互不冲突。</li>
      <li><strong>支持多人同时读写</strong>：多人可同时上传、下载，同一人也可一边上传一边下载别的文件，互不中断。</li>
    </ul>

    <h2>四、常见问题速查</h2>
    <div class="faq-item">
      <div class="faq-q">Q1：为什么公网下载几百 MB 大文件比较慢？</div>
      <div class="faq-a">免费公网通道需经海外中转，适合人在校外应急传文档/PPT/照片；同 Wi-Fi 下传大文件请务必使用 <strong>局域网网址</strong>（<code>http://192.168.x.x:8000</code>），速度极快。</div>
    </div>
    <div class="faq-item">
      <div class="faq-q">Q2：怎么彻底卸载本软件？</div>
      <div class="faq-a">打开 Windows <strong>设置 → 应用 → 安装的应用</strong>，找到「LabDrop 实验室网络U盘」直接卸载即可（不会删掉你共享文件夹里的个人文件）。</div>
    </div>
  </div>
</body>
</html>
'''

def get_html_page():
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>⚡ 实验室网络U盘 (LabDrop)</title>
  <style>
    :root {
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --radius: 12px;
      --danger: #ef4444;
      --success: #10b981;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px 16px;
    }
    .container { max-width: 920px; margin: 0 auto; }
    header {
      display: flex; justify-content: space-between; align-items: center;
      flex-wrap: wrap; gap: 16px; margin-bottom: 20px;
      background: var(--card-bg); padding: 20px 24px; border-radius: var(--radius);
      box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid var(--border);
    }
    .brand h1 { font-size: 22px; font-weight: 700; color: #1e293b; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .gh-badge {
      display: inline-flex; align-items: center; gap: 5px;
      background: #1e293b; color: #fff; font-size: 12px; font-weight: 600;
      padding: 4px 10px; border-radius: 20px; text-decoration: none;
      transition: all 0.2s; line-height: 1.2;
    }
    .gh-badge:hover { background: #0f172a; transform: translateY(-1px); }
    .gh-badge svg { width: 14px; height: 14px; fill: currentColor; }
    .brand p { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
    .ip-box {
      display: flex; align-items: center; gap: 8px;
      background: #eff6ff; border: 1px solid #bfdbfe;
      padding: 8px 14px; border-radius: 8px; font-size: 14px;
    }
    .ip-box code { font-weight: 600; color: var(--primary); font-family: Consolas, monospace; }
    .btn {
      display: inline-flex; align-items: center; justify-content: center;
      padding: 6px 12px; font-size: 13px; font-weight: 500; border-radius: 6px;
      cursor: pointer; border: none; transition: all 0.2s; text-decoration: none;
    }
    .btn-primary { background: var(--primary); color: #fff; }
    .btn-primary:hover { background: var(--primary-hover); }
    .btn-secondary { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
    .btn-secondary:hover { background: #e2e8f0; }
    .btn-danger { background: #fee2e2; color: var(--danger); }
    .btn-danger:hover { background: #fecaca; }

    /* 拖拽上传与按钮组合区 */
    .dropzone {
      background: var(--card-bg); border: 2px dashed #93c5fd; border-radius: var(--radius);
      padding: 30px 20px; text-align: center; transition: all 0.2s; margin-bottom: 20px;
    }
    .dropzone.dragover { border-color: var(--primary); background: #f0f7ff; transform: translateY(-1px); }
    .dropzone-icon { font-size: 40px; margin-bottom: 6px; }
    .dropzone h3 { font-size: 16px; font-weight: 600; margin-bottom: 6px; }
    .dropzone p { font-size: 13px; color: var(--text-muted); margin-bottom: 14px; }
    .upload-btns { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; }
    .upload-btns .btn { padding: 8px 18px; font-size: 14px; font-weight: 600; }
    #fileInput, #folderInput { display: none; }

    /* 上传进度条列表 */
    .progress-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
    .progress-item {
      background: var(--card-bg); border: 1px solid var(--border);
      padding: 10px 14px; border-radius: 8px; font-size: 13px;
    }
    .progress-bar-bg { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-top: 6px; }
    .progress-bar-fill { height: 100%; background: var(--primary); width: 0%; transition: width 0.15s ease-out; }

    /* 文件管理卡片与面包屑 */
    .files-card {
      background: var(--card-bg); border-radius: var(--radius);
      border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.05); overflow: hidden;
    }
    .breadcrumb-bar {
      background: #f8fafc; border-bottom: 1px solid var(--border);
      padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
    }
    .breadcrumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 14px; }
    .crumb-item { color: var(--primary); cursor: pointer; text-decoration: none; font-weight: 500; }
    .crumb-item:hover { text-decoration: underline; }
    .crumb-sep { color: #94a3b8; font-size: 12px; }
    .crumb-current { color: var(--text); font-weight: 600; }

    .files-toolbar {
      padding: 12px 20px; border-bottom: 1px solid var(--border);
      display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
    }
    .search-input {
      padding: 6px 12px; font-size: 13px; border: 1px solid var(--border);
      border-radius: 6px; outline: none; min-width: 180px;
    }
    .search-input:focus { border-color: var(--primary); }

    .file-table { width: 100%; border-collapse: collapse; font-size: 14px; }
    .file-table th {
      text-align: left; padding: 10px 16px; background: #f8fafc;
      color: var(--text-muted); font-weight: 600; font-size: 12px; border-bottom: 1px solid var(--border);
    }
    .file-table td { padding: 12px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    .file-table tr:hover { background: #fafafa; }
    .row-folder { cursor: pointer; background: #fcfdfd; }
    .row-folder:hover { background: #f0f7ff !important; }
    .name-cell { display: flex; align-items: center; gap: 10px; word-break: break-all; }
    .item-icon { font-size: 20px; flex-shrink: 0; }
    .folder-link { color: var(--text); font-weight: 600; text-decoration: none; }
    .folder-link:hover { color: var(--primary); }
    .actions-cell { text-align: right; white-space: nowrap; }
    .actions-cell .btn { margin-left: 6px; }
    .empty-state { padding: 48px 20px; text-align: center; color: var(--text-muted); font-size: 14px; }

    /* 本地磁盘挂载弹窗 */
    .modal-mask {
      display: none; position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(3px); z-index: 999; align-items: center; justify-content: center; padding: 16px;
    }
    .modal-mask.show { display: flex; }
    .modal-box {
      background: #fff; border-radius: 14px; max-width: 500px; width: 100%;
      padding: 24px; box-shadow: 0 20px 40px rgba(0,0,0,0.15); border: 1px solid var(--border);
    }
    .modal-box h3 { font-size: 17px; color: #0f172a; margin-bottom: 8px; }
    .modal-box p { font-size: 13px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.6; }
    .unc-row {
      display: flex; gap: 8px; align-items: center; background: #f8fafc;
      border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; margin-bottom: 16px;
    }
    .unc-row code { flex: 1; font-family: Consolas, monospace; font-size: 13px; color: #0f172a; word-break: break-all; }
    .modal-actions { display: flex; gap: 10px; justify-content: flex-end; flex-wrap: wrap; }

    /* 底部传播与软件下载条 */
    .promo-bar {
      margin-top: 20px; background: var(--card-bg); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 14px 20px;
      display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.03);
    }
    .promo-text { font-size: 13px; color: var(--text-muted); display: flex; align-items: center; gap: 8px; }
    .promo-text strong { color: #1e293b; }
    .promo-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <h1>
          <span>⚡ 实验室网络U盘 (LabDrop)</span>
          <a class="gh-badge" href="https://github.com/AindyZhang/LabDrop" target="_blank" title="访问开源项目 GitHub 主页，欢迎点个 Star ⭐">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path></svg>
            <span>GitHub</span>
          </a>
        </h1>
        <p>支持多级目录、拖拽/多选上传文件及整个文件夹 · 100% 本地存储</p>
      </div>
      <div class="ip-box">
        <span>当前访问网址：</span>
        <code id="serverUrl">加载中...</code>
        <button class="btn btn-secondary" onclick="copyUrl(this)">复制</button>
      </div>
    </header>

    <!-- 拖拽上传与按钮 -->
    <div class="dropzone" id="dropzone">
      <div class="dropzone-icon">📁</div>
      <h3>拖拽任意 文件 或 整个文件夹 到此上传</h3>
      <p>自动保持多层文件夹目录结构，原汁原味同步到 U 盘</p>
      <div class="upload-btns">
        <button class="btn btn-primary" onclick="document.getElementById('fileInput').click()">📄 选择文件上传</button>
        <button class="btn btn-primary" style="background:#0284c7;" onclick="document.getElementById('folderInput').click()">📂 选择整个文件夹上传</button>
        <button class="btn btn-secondary" onclick="createNewFolder()">➕ 新建文件夹</button>
      </div>
      <input type="file" id="fileInput" multiple>
      <input type="file" id="folderInput" webkitdirectory directory multiple>
    </div>

    <!-- 上传中进度列表 -->
    <div class="progress-list" id="progressList"></div>

    <!-- 文件列表与层级卡片 -->
    <div class="files-card">
      <!-- 面包屑导航 -->
      <div class="breadcrumb-bar">
        <div class="breadcrumbs" id="breadcrumbs">
          <span class="crumb-current">🏠 U盘根目录</span>
        </div>
        <button class="btn btn-secondary" onclick="loadFiles(currentDir)">🔄 刷新列表</button>
      </div>

      <!-- 工具栏 -->
      <div class="files-toolbar">
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
          <span style="font-weight:600; font-size:14px;" id="itemCount">0 项</span>
          <a id="zipCurrentBtn" class="btn btn-secondary" style="padding:5px 11px; font-size:12px;" href="/download-zip/" target="dlFrame" title="将当前目录整体打包为 .zip 下载">📦 打包下载当前目录</a>
          <button class="btn btn-primary" style="padding:5px 12px; font-size:12px; background:#0f766e;" onclick="launchNativeDisk(currentDir)" title="以 Windows 真实文件夹窗口打开，直接复制整个文件夹">💻 像真U盘一样打开</button>
        </div>
        <div>
          <input type="text" id="searchInput" class="search-input" placeholder="在当前目录下搜索..." oninput="renderTable()">
        </div>
      </div>

      <!-- 文件与文件夹表格 -->
      <div style="overflow-x:auto;">
        <table class="file-table" id="fileTable">
          <thead>
            <tr>
              <th>名称</th>
              <th style="width: 100px;">大小</th>
              <th style="width: 165px;">修改时间</th>
              <th style="width: 185px; text-align: right;">操作</th>
            </tr>
          </thead>
          <tbody id="fileListBody"></tbody>
        </table>
        <div class="empty-state" id="emptyState" style="display:none;">
          当前目录下空空如也，把文件或文件夹拖上来吧！
        </div>
      </div>
    </div>

    <!-- 底部传播与软件获取栏 -->
    <div class="promo-bar">
      <div class="promo-text">
        <span style="font-size:18px;">⚡</span>
        <span><strong>100% 本地存储 · 不上传任何隐私</strong> — 也想在自己电脑搭一个？</span>
      </div>
      <div class="promo-actions">
        <a class="btn btn-secondary" href="https://github.com/AindyZhang/LabDrop" target="_blank">⭐ GitHub / 检查新版</a>
        <a class="btn btn-secondary" href="/guide" target="_blank">📖 使用说明书</a>
        <a class="btn btn-primary" href="/download-installer" target="dlFrame" download="LabDrop-Setup.exe">⬇ 下载管理软件 (Setup.exe)</a>
      </div>
    </div>
  </div>

  <!-- 像真U盘一样打开（本地磁盘挂载弹窗） -->
  <div class="modal-mask" id="diskModal" onclick="if(event.target===this) closeDiskModal()">
    <div class="modal-box">
      <h3>💻 像真 U 盘一样直接打开（免压缩拷贝文件夹）</h3>
      <p>想直接像操作实体 U 盘那样 <strong>Ctrl+C / Ctrl+V 复制整个文件夹</strong>（不用下载压缩包、不用解压）？按以下任一方法即可在 Windows 文件资源管理器中直接打开：</p>
      <p style="margin-bottom:6px; color:#0f172a; font-weight:600;">方法一（最简单）：一键打开脚本</p>
      <p style="margin-bottom:12px;">点击下方蓝色按钮下载 <code>Open_LabDrop_Disk.bat</code>，双击运行即可自动弹出 U 盘文件夹窗口。</p>
      <p style="margin-bottom:6px; color:#0f172a; font-weight:600;">方法二（免下载）：直接粘到“此电脑”地址栏按回车</p>
      <div class="unc-row">
        <code id="uncPathText">\\\\192.168.1.102@8000\\DavWWWRoot\\webdav</code>
        <button class="btn btn-secondary" onclick="copyUncPath(this)">复制</button>
      </div>
      <div class="modal-actions">
        <button class="btn btn-secondary" onclick="closeDiskModal()">关闭</button>
        <a class="btn btn-primary" href="/api/mount-script" download="Open_LabDrop_Disk.bat">⬇ 下载一键打开脚本</a>
      </div>
    </div>
  </div>

  <!-- 隐藏下载框架：防止 iPad/iPhone Safari 等浏览器点击下载时触发主窗口导航从而中断正在进行的上传 -->
  <iframe name="dlFrame" style="display:none; width:0; height:0; border:0;"></iframe>

  <script>
    let currentDir = "";
    let dirData = { dirs: [], files: [], breadcrumbs: [] };

    // 获取服务器信息与当前地址
    async function loadInfo() {
      try {
        const host = window.location.hostname;
        if (host !== '127.0.0.1' && host !== 'localhost' && !host.startsWith('192.168.')) {
          document.getElementById('serverUrl').innerText = window.location.origin;
        } else {
          const res = await fetch('/api/info');
          const data = await res.json();
          document.getElementById('serverUrl').innerText = data.url;
        }
      } catch (e) {
        document.getElementById('serverUrl').innerText = window.location.origin;
      }
    }

    function launchNativeDisk(dirPath = "") {
      const host = window.location.hostname || '127.0.0.1';
      const port = window.location.port || '80';
      const protoUrl = `labdrop://open?host=${encodeURIComponent(host)}&port=${encodeURIComponent(port)}&dir=${encodeURIComponent(dirPath || '')}`;

      // 智能检测：尝试直接唤起本地协议；若 1.2 秒内浏览器未失焦（说明本机未安装客户端），自动弹出免安装指引
      let launched = false;
      const onBlur = () => { launched = true; };
      const onVis = () => { if (document.hidden) launched = true; };
      window.addEventListener('blur', onBlur);
      document.addEventListener('visibilitychange', onVis);

      window.location.href = protoUrl;

      setTimeout(() => {
        window.removeEventListener('blur', onBlur);
        document.removeEventListener('visibilitychange', onVis);
        if (!launched) {
          openDiskModal(dirPath);
        }
      }, 1200);
    }

    function openDiskModal(dirPath = "") {
      const BS = String.fromCharCode(92);
      const host = window.location.hostname || '127.0.0.1';
      const port = window.location.port || '80';
      let unc = BS + BS + host + '@' + port + BS + 'DavWWWRoot' + BS + 'webdav';
      if (dirPath) {
        const cleanParts = dirPath.split('/').filter(Boolean);
        if (cleanParts.length > 0) {
          unc += BS + cleanParts.join(BS);
        }
      }
      document.getElementById('uncPathText').innerText = unc;
      document.getElementById('diskModal').classList.add('show');
    }

    function closeDiskModal() {
      document.getElementById('diskModal').classList.remove('show');
    }

    function copyTextSafe(txt, btn) {
      const done = () => {
        if (btn) {
          const old = btn.innerText;
          btn.innerText = '已复制 ✔';
          btn.style.color = '#059669';
          setTimeout(() => {
            btn.innerText = old;
            btn.style.color = '';
          }, 1500);
        }
      };

      const fallbackCopy = () => {
        const ta = document.createElement('textarea');
        ta.value = txt;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
          document.execCommand('copy');
          done();
        } catch (e) {
          prompt('请按 Ctrl+C 复制：', txt);
        }
        document.body.removeChild(ta);
      };

      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(txt).then(done).catch(fallbackCopy);
      } else {
        fallbackCopy();
      }
    }

    function copyUncPath(btn) {
      const txt = document.getElementById('uncPathText').innerText;
      copyTextSafe(txt, btn);
    }

    function copyUrl(btn) {
      const url = document.getElementById('serverUrl').innerText;
      copyTextSafe(url, btn);
    }

    function getFileIcon(name) {
      const ext = name.split('.').pop().toLowerCase();
      if (['pdf'].includes(ext)) return '📕';
      if (['doc', 'docx'].includes(ext)) return '📘';
      if (['xls', 'xlsx', 'csv'].includes(ext)) return '📊';
      if (['ppt', 'pptx'].includes(ext)) return '📙';
      if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) return '📦';
      if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)) return '🖼️';
      if (['mp4', 'mov', 'avi', 'mkv'].includes(ext)) return '🎬';
      if (['py', 'c', 'cpp', 'java', 'js', 'html', 'css', 'json', 'sh'].includes(ext)) return '💻';
      return '📄';
    }

    // 加载指定目录下的内容
    async function loadFiles(dir = "") {
      currentDir = dir;
      const zipBtn = document.getElementById('zipCurrentBtn');
      if (zipBtn) {
        zipBtn.href = '/download-zip/' + encodeURIComponent(dir);
      }
      try {
        const res = await fetch('/api/files?dir=' + encodeURIComponent(dir));
        const data = await res.json();
        dirData = data;
        renderBreadcrumbs(data.breadcrumbs);
        renderTable();
      } catch (err) {
        console.error('加载失败:', err);
      }
    }

    // 渲染面包屑导航
    function renderBreadcrumbs(crumbs) {
      const box = document.getElementById('breadcrumbs');
      if (!crumbs || crumbs.length === 0) {
        box.innerHTML = '<span class="crumb-current">🏠 U盘根目录</span>';
        return;
      }
      box.innerHTML = crumbs.map((c, i) => {
        const isLast = (i === crumbs.length - 1);
        if (isLast) {
          return `<span class="crumb-current">${escapeHtml(c.name)}</span>`;
        } else {
          return `<a class="crumb-item" onclick="loadFiles(decodeURIComponent('${encodeURIComponent(c.path)}'))">${escapeHtml(c.name)}</a><span class="crumb-sep">/</span>`;
        }
      }).join('');
    }

    // 渲染表格
    function renderTable() {
      const tbody = document.getElementById('fileListBody');
      const empty = document.getElementById('emptyState');
      const itemCount = document.getElementById('itemCount');
      const keyword = document.getElementById('searchInput').value.trim().toLowerCase();

      const dirs = (dirData.dirs || []).filter(d => d.name.toLowerCase().includes(keyword));
      const files = (dirData.files || []).filter(f => f.name.toLowerCase().includes(keyword));

      itemCount.innerText = `${dirs.length + files.length} 项 (${dirs.length} 个文件夹, ${files.length} 个文件)`;

      if (dirs.length === 0 && files.length === 0) {
        tbody.innerHTML = '';
        empty.style.display = 'block';
        return;
      }

      empty.style.display = 'none';
      let html = '';

      // 渲染文件夹行（极简清爽：打包下载完整文件夹 + 删除）
      dirs.forEach(d => {
        const encPath = encodeURIComponent(d.path);
        html += `
          <tr class="row-folder">
            <td onclick="loadFiles(decodeURIComponent('${encPath}'))">
              <div class="name-cell">
                <span class="item-icon">📁</span>
                <span class="folder-link"><strong>${escapeHtml(d.name)}</strong></span>
              </div>
            </td>
            <td style="color:var(--text-muted);">-</td>
            <td style="color:var(--text-muted);">${d.mtime}</td>
            <td class="actions-cell">
              <a class="btn btn-primary" href="/download-zip/${encPath}" target="dlFrame" title="下载整个文件夹（含完整目录结构 .zip）">下载 (.zip)</a>
              <button class="btn btn-danger" onclick="deleteItem(decodeURIComponent('${encPath}'), true)">删除</button>
            </td>
          </tr>
        `;
      });

      // 渲染文件行
      files.forEach(f => {
        const encPath = encodeURIComponent(f.path);
        html += `
          <tr>
            <td>
              <div class="name-cell">
                <span class="item-icon">${getFileIcon(f.name)}</span>
                <span>${escapeHtml(f.name)}</span>
              </div>
            </td>
            <td style="color:var(--text-muted);">${f.size_human}</td>
            <td style="color:var(--text-muted);">${f.mtime}</td>
            <td class="actions-cell">
              <a class="btn btn-primary" href="/download/${encPath}" target="dlFrame" download>下载</a>
              <button class="btn btn-danger" onclick="deleteItem(decodeURIComponent('${encPath}'), false)">删除</button>
            </td>
          </tr>
        `;
      });

      tbody.innerHTML = html;
    }

    // 整个文件夹“直接下载”（智能双模式：支持目录直写则直接落盘为完整多级文件夹，否则逐个直接下载原文件）
    async function directDownloadFolder(folderPath, folderName) {
      let manifest;
      try {
        const res = await fetch('/api/folder-manifest?path=' + encodeURIComponent(folderPath));
        manifest = await res.json();
        if (manifest.error) {
          alert('读取文件夹失败：' + manifest.error);
          return;
        }
      } catch (e) {
        alert('获取文件夹清单失败');
        return;
      }

      const files = manifest.files || [];
      const dirs = manifest.dirs || [];
      if (files.length === 0 && dirs.length === 0) {
        alert('该文件夹是空的，没有可下载的内容。');
        return;
      }

      const list = document.getElementById('progressList');
      const item = document.createElement('div');
      item.className = 'progress-item';
      item.innerHTML = `
        <div style="display:flex; justify-content:space-between;">
          <span>⬇ 正在直接下载文件夹: <strong>${escapeHtml(folderName || 'U盘资料')}</strong></span>
          <span class="status-text">准备中...</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
      `;

      const statusText = item.querySelector('.status-text');
      const barFill = item.querySelector('.progress-bar-fill');

      // 模式一：现代浏览器安全上下文，直接选择本地目录原样写入完整多级文件夹（免解压！）
      if (window.showDirectoryPicker) {
        try {
          const pickedRoot = await window.showDirectoryPicker({ mode: 'readwrite' });
          list.appendChild(item);
          const targetRoot = await pickedRoot.getDirectoryHandle(folderName || 'U盘资料', { create: true });

          // 先建立全部子目录（包含空目录）
          for (const d of dirs) {
            let cur = targetRoot;
            for (const part of d.split('/')) {
              if (part) cur = await cur.getDirectoryHandle(part, { create: true });
            }
          }

          // 逐个流式写入文件
          for (let i = 0; i < files.length; i++) {
            const f = files[i];
            const pct = Math.round(((i) / Math.max(1, files.length)) * 100);
            statusText.innerText = `正在写入 (${i + 1}/${files.length}): ${f.name}`;
            barFill.style.width = `${pct}%`;

            const parts = f.rel_in_folder.split('/');
            const fname = parts.pop();
            let cur = targetRoot;
            for (const part of parts) {
              if (part) cur = await cur.getDirectoryHandle(part, { create: true });
            }

            const fileHandle = await cur.getFileHandle(fname, { create: true });
            const writable = await fileHandle.createWritable();
            const resp = await fetch('/download/' + encodeURIComponent(f.download_path));
            if (resp.body && resp.body.pipeTo) {
              await resp.body.pipeTo(writable);
            } else {
              const blob = await resp.blob();
              await writable.write(blob);
              await writable.close();
            }
          }

          statusText.innerText = `✅ 整个文件夹已直接保存到本地 (${files.length} 个文件)`;
          statusText.style.color = 'var(--success)';
          barFill.style.width = '100%';
          barFill.style.background = 'var(--success)';
          setTimeout(() => item.remove(), 4000);
          return;
        } catch (err) {
          if (err && err.name === 'AbortError') return; // 用户取消了选择
          item.remove();
          console.warn('目录直写回退为逐文件直下:', err);
        }
      }

      // 模式二：纯 HTTP 局域网/公网环境，不打包 zip，依次直接下载每个原文件
      if (files.length === 0) {
        alert('该目录下只有空文件夹，如需保留空目录结构请点击“打包下载”。');
        return;
      }
      if (files.length > 10) {
        const ok = confirm(`该文件夹内共有 ${files.length} 个文件。\\n点击【确定】直接逐个下载原文件（浏览器可能会提示“允许下载多个文件”）；\\n点击【取消】可改用旁边的“打包下载(.zip)”一键下载。`);
        if (!ok) return;
      }

      list.appendChild(item);
      for (let i = 0; i < files.length; i++) {
        const f = files[i];
        const pct = Math.round(((i + 1) / files.length) * 100);
        statusText.innerText = `正在直接下载 (${i + 1}/${files.length}): ${f.name}`;
        barFill.style.width = `${pct}%`;

        const a = document.createElement('a');
        a.href = '/download/' + encodeURIComponent(f.download_path);
        a.download = f.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // 适当间隔避免浏览器吞掉连续下载请求
        if (i < files.length - 1) {
          await new Promise(r => setTimeout(r, 380));
        }
      }

      statusText.innerText = `✅ 已全部触发直接下载 (${files.length} 个文件)`;
      statusText.style.color = 'var(--success)';
      barFill.style.background = 'var(--success)';
      setTimeout(() => item.remove(), 4000);
    }

    function escapeHtml(str) {
      return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }

    // 新建文件夹
    async function createNewFolder() {
      const name = prompt("请输入新文件夹名称：");
      if (!name || !name.trim()) return;
      try {
        const res = await fetch('/api/mkdir', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_dir: currentDir, name: name.trim() })
        });
        const data = await res.json();
        if (data.success) {
          loadFiles(currentDir);
        } else {
          alert('创建失败: ' + (data.error || '未知错误'));
        }
      } catch (err) {
        alert('请求失败');
      }
    }

    // 删除项目
    async function deleteItem(path, isDir) {
      const typeStr = isDir ? '文件夹及其内部所有内容' : '文件';
      if (!confirm(`确定要彻底删除该${typeStr}吗？\\n路径：${path}`)) return;
      try {
        const res = await fetch('/api/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path })
        });
        const data = await res.json();
        if (data.success) {
          loadFiles(currentDir);
        } else {
          alert('删除失败: ' + (data.error || '未知错误'));
        }
      } catch (err) {
        alert('请求失败');
      }
    }

    // 上传单个文件对象（支持上传中取消、失败/断网后一键重试或取消移除）
    function uploadFileObject(file, relPath) {
      const list = document.getElementById('progressList');
      const item = document.createElement('div');
      item.className = 'progress-item';
      item.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
          <span class="file-label" style="word-break:break-all;">⏳ 正在上传: <strong>${escapeHtml(relPath)}</strong></span>
          <div style="display:flex; align-items:center; gap:8px; flex-shrink:0;">
            <span class="status-text" style="font-weight:600;">0%</span>
            <button type="button" class="btn btn-primary btn-retry" style="display:none; padding:3px 10px; font-size:12px;">🔄 重试</button>
            <button type="button" class="btn btn-secondary btn-cancel" style="padding:3px 10px; font-size:12px;">取消</button>
          </div>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar-fill"></div></div>
      `;
      list.appendChild(item);

      const fileLabel = item.querySelector('.file-label');
      const statusText = item.querySelector('.status-text');
      const barFill = item.querySelector('.progress-bar-fill');
      const btnRetry = item.querySelector('.btn-retry');
      const btnCancel = item.querySelector('.btn-cancel');

      let currentXhr = null;
      let isFinished = false;

      function showFailed(reason) {
        statusText.innerText = reason;
        statusText.style.color = 'var(--danger)';
        barFill.style.background = 'var(--danger)';
        btnRetry.style.display = 'inline-flex';
        btnCancel.style.display = 'inline-flex';
        btnCancel.innerText = '✕ 取消';
      }

      function startUpload() {
        isFinished = false;
        fileLabel.innerHTML = `⏳ 正在上传: <strong>${escapeHtml(relPath)}</strong>`;
        statusText.innerText = '0%';
        statusText.style.color = 'var(--text-muted)';
        barFill.style.width = '0%';
        barFill.style.background = 'var(--primary)';
        btnRetry.style.display = 'none';
        btnCancel.style.display = 'inline-flex';
        btnCancel.innerText = '取消';

        const xhr = new XMLHttpRequest();
        currentXhr = xhr;
        xhr.open('POST', '/api/upload?relpath=' + encodeURIComponent(relPath));
        xhr.setRequestHeader('X-Relative-Path', encodeURIComponent(relPath));

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            statusText.innerText = `${percent}%`;
            barFill.style.width = `${percent}%`;
          }
        };

        xhr.onload = () => {
          if (xhr.status === 200) {
            isFinished = true;
            currentXhr = null;
            statusText.innerText = '✅ 上传完成';
            statusText.style.color = 'var(--success)';
            barFill.style.width = '100%';
            barFill.style.background = 'var(--success)';
            btnRetry.style.display = 'none';
            btnCancel.style.display = 'none';
            setTimeout(() => item.remove(), 2500);
            loadFiles(currentDir);
          } else {
            currentXhr = null;
            showFailed('❌ 上传失败');
          }
        };

        xhr.onerror = () => {
          currentXhr = null;
          showFailed('❌ 网络中断');
        };

        xhr.onabort = () => {
          currentXhr = null;
        };

        xhr.send(file);
      }

      btnRetry.onclick = () => {
        startUpload();
      };

      btnCancel.onclick = () => {
        if (currentXhr && !isFinished) {
          currentXhr.abort();
          currentXhr = null;
        }
        item.remove();
      };

      startUpload();
    }

    // 处理文件输入（普通多文件）
    document.getElementById('fileInput').addEventListener('change', (e) => {
      const files = e.target.files;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const rel = currentDir ? `${currentDir}/${file.name}` : file.name;
        uploadFileObject(file, rel);
      }
      e.target.value = '';
    });

    // 处理文件夹选择（webkitdirectory）
    document.getElementById('folderInput').addEventListener('change', (e) => {
      const files = e.target.files;
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        // file.webkitRelativePath 包含了文件夹的内部结构，如 folder/sub/a.txt
        const folderRel = file.webkitRelativePath || file.name;
        const finalRel = currentDir ? `${currentDir}/${folderRel}` : folderRel;
        uploadFileObject(file, finalRel);
      }
      e.target.value = '';
    });

    // 处理拖拽（递归解析文件夹与文件）
    const dropzone = document.getElementById('dropzone');

    ['dragenter', 'dragover'].forEach(name => {
      dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(name => {
      dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', async (e) => {
      const items = e.dataTransfer.items;
      if (!items) return;

      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.kind === 'file') {
          const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
          if (entry) {
            traverseFileTree(entry, currentDir);
          } else {
            const file = item.getAsFile();
            const rel = currentDir ? `${currentDir}/${file.name}` : file.name;
            uploadFileObject(file, rel);
          }
        }
      }
    });

    // 递归读取拖拽的文件夹
    function traverseFileTree(item, parentPath) {
      const currentPath = parentPath ? `${parentPath}/${item.name}` : item.name;
      if (item.isFile) {
        item.file(file => {
          uploadFileObject(file, currentPath);
        });
      } else if (item.isDirectory) {
        const dirReader = item.createReader();
        const readEntries = () => {
          dirReader.readEntries(entries => {
            if (entries.length > 0) {
              for (let i = 0; i < entries.length; i++) {
                traverseFileTree(entries[i], currentPath);
              }
              readEntries(); // 持续读取直至读完
            }
          });
        };
        readEntries();
      }
    }

    // 初始化
    loadInfo();
    loadFiles("");
  </script>
</body>
</html>
'''

if __name__ == "__main__":
    ip = get_local_ip()
    s_dir = get_storage_dir()
    print("=" * 60)
    print("🚀 实验室网络U盘 (LabDrop) 核心服务")
    print(f"📁 共享存储文件夹: {s_dir}")
    print(f"🏠 局域网访问地址: http://{ip}:{PORT}")
    print("=" * 60)
    httpd = LabDropServer(('0.0.0.0', PORT), LabDropHandler)
    httpd.serve_forever()
