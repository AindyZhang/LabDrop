# -*- coding: utf-8 -*-
"""
实验室网络U盘后台守护进程 (多线程防死锁 + 独立公网开关 + 纯Python Bore隧道)
"""

import os
import sys
import time
import json
import socket
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "daemon.log")

# 在 pythonw.exe 无控制台环境下安全重定向输出，彻底防止日志写入崩溃
try:
    _log_fp = open(LOG_FILE, "w", encoding="utf-8", buffering=1)
    sys.stdout = _log_fp
    sys.stderr = _log_fp
except Exception:
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

sys.path.insert(0, BASE_DIR)
from server import LabDropServer, LabDropHandler, PORT, get_local_ip, get_storage_dir, CONFIG_FILE
from bore_tunnel import BoreTunnel

RUNTIME_FILE = os.path.join(BASE_DIR, "runtime.json")

def read_json(path, default=None):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {} if default is None else default

def write_runtime(data):
    try:
        with open(RUNTIME_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def is_port_in_use(port=PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', port)) == 0

def clean_old_port():
    try:
        CREATE_NO_WINDOW = 0x08000000
        subprocess.run(
            f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{PORT} ^| findstr LISTENING\') do taskkill /f /pid %a >nul 2>&1',
            shell=True, creationflags=CREATE_NO_WINDOW
        )
        time.sleep(0.5)
    except Exception:
        pass

def get_enable_public():
    cfg = read_json(CONFIG_FILE, {})
    return bool(cfg.get("enable_public", True))

def main():
    local_ip = get_local_ip()
    lan_url = f"http://{local_ip}:{PORT}"
    storage_dir = get_storage_dir()

    runtime_data = {
        "status": "starting",
        "pid": os.getpid(),
        "lan_url": lan_url,
        "public_url": "",
        "public_status": "off",
        "storage_dir": storage_dir,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    write_runtime(runtime_data)
    print(f"[{time.strftime('%H:%M:%S')}] 启动守护进程，共享目录: {storage_dir}", flush=True)

    # 1. 启动本地多线程 Web 核心服务 (毫秒就绪)
    httpd = None
    try:
        httpd = LabDropServer(('0.0.0.0', PORT), LabDropHandler)
    except OSError:
        clean_old_port()
        try:
            httpd = LabDropServer(('0.0.0.0', PORT), LabDropHandler)
        except Exception as e:
            runtime_data["status"] = "error"
            runtime_data["error"] = f"端口 {PORT} 无法绑定: {e}"
            write_runtime(runtime_data)
            print(f"[ERROR] 端口绑定失败: {e}", flush=True)
            return

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    for _ in range(25):
        if is_port_in_use(PORT):
            break
        time.sleep(0.1)

    runtime_data["status"] = "running"
    write_runtime(runtime_data)
    print(f"[{time.strftime('%H:%M:%S')}] 本地 Web 服务就绪: {lan_url}", flush=True)

    # 2. 动态管理公网隧道（随时响应 config.json 中的 enable_public 热开关）
    active_tunnel = None
    tunnel_thread = None

    def start_tunnel():
        nonlocal active_tunnel, tunnel_thread
        if active_tunnel is not None:
            return
        print(f"[{time.strftime('%H:%M:%S')}] 正在开启公网通道 (Bore)...", flush=True)
        runtime_data["public_status"] = "connecting"
        runtime_data["public_url"] = ""
        write_runtime(runtime_data)

        def on_url(url):
            if active_tunnel is not None and not active_tunnel.stop_event.is_set():
                runtime_data["public_status"] = "on"
                runtime_data["public_url"] = url
                write_runtime(runtime_data)
                print(f"[{time.strftime('%H:%M:%S')}] 公网网址就绪: {url}", flush=True)

        active_tunnel = BoreTunnel(local_port=PORT, on_url=on_url)
        tunnel_thread = threading.Thread(target=active_tunnel.run_forever, daemon=True)
        tunnel_thread.start()

    def stop_tunnel():
        nonlocal active_tunnel, tunnel_thread
        if active_tunnel is not None:
            print(f"[{time.strftime('%H:%M:%S')}] 正在关闭公网通道...", flush=True)
            active_tunnel.stop()
            active_tunnel = None
            tunnel_thread = None
        if runtime_data.get("public_status") != "off" or runtime_data.get("public_url"):
            runtime_data["public_status"] = "off"
            runtime_data["public_url"] = ""
            write_runtime(runtime_data)

    # 主监控循环
    try:
        while True:
            # 检查是否要求退出
            cur_rt = read_json(RUNTIME_FILE, {})
            if cur_rt.get("status") == "stopping":
                break

            # 检查公网开关状态（支持运行中随时一键开启/禁止公网）
            want_public = get_enable_public()
            if want_public and active_tunnel is None:
                start_tunnel()
            elif not want_public and active_tunnel is not None:
                stop_tunnel()
            elif not want_public and runtime_data.get("public_status") != "off":
                stop_tunnel()

            time.sleep(0.6)
    except KeyboardInterrupt:
        pass
    finally:
        stop_tunnel()
        try: httpd.shutdown()
        except Exception: pass
        runtime_data["status"] = "stopped"
        runtime_data["public_status"] = "off"
        runtime_data["public_url"] = ""
        write_runtime(runtime_data)
        print(f"[{time.strftime('%H:%M:%S')}] 守护进程已停止。", flush=True)

if __name__ == "__main__":
    main()
