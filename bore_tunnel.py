# -*- coding: utf-8 -*-
"""
纯 Python 标准库实现的 Bore 公网 TCP 隧道客户端 (0 外部二进制 / 0 杀软误报 / 秒出公网地址)
"""

import json
import socket
import threading
import time

CONTROL_HOST = "bore.pub"
CONTROL_PORT = 7835

def _recv_json_frame(sock):
    buf = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            return None
        if chunk == b"\x00":
            break
        buf.extend(chunk)
        if len(buf) > 65536:
            return None
    return json.loads(buf.decode("utf-8"))

def _send_json_frame(sock, obj):
    payload = (json.dumps(obj) + "\x00").encode("utf-8")
    sock.sendall(payload)

def _pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try: src.shutdown(socket.SHUT_RD)
        except Exception: pass
        try: dst.shutdown(socket.SHUT_WR)
        except Exception: pass

def _handle_incoming(conn_id, local_host, local_port):
    remote_sock = None
    local_sock = None
    try:
        remote_sock = socket.create_connection((CONTROL_HOST, CONTROL_PORT), timeout=10)
        remote_sock.settimeout(None)
        _send_json_frame(remote_sock, {"Accept": conn_id})

        local_sock = socket.create_connection((local_host, local_port), timeout=5)
        local_sock.settimeout(None)

        t1 = threading.Thread(target=_pipe, args=(remote_sock, local_sock), daemon=True)
        t2 = threading.Thread(target=_pipe, args=(local_sock, remote_sock), daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except Exception:
        pass
    finally:
        if remote_sock:
            try: remote_sock.close()
            except Exception: pass
        if local_sock:
            try: local_sock.close()
            except Exception: pass

class BoreTunnel:
    def __init__(self, local_port=8000, local_host="127.0.0.1", on_url=None):
        self.local_host = local_host
        self.local_port = local_port
        self.on_url = on_url
        self.stop_event = threading.Event()
        self.control_sock = None
        self.public_url = ""

    def stop(self):
        self.stop_event.set()
        if self.control_sock:
            try: self.control_sock.close()
            except Exception: pass

    def run_once(self):
        sock = socket.create_connection((CONTROL_HOST, CONTROL_PORT), timeout=10)
        self.control_sock = sock
        sock.settimeout(15)
        _send_json_frame(sock, {"Hello": 0})
        resp = _recv_json_frame(sock)
        if not isinstance(resp, dict) or "Hello" not in resp:
            raise RuntimeError(f"Bore handshake failed: {resp}")

        remote_port = resp["Hello"]
        self.public_url = f"http://{CONTROL_HOST}:{remote_port}"
        if self.on_url:
            self.on_url(self.public_url)

        # 心跳和连接分派循环
        sock.settimeout(45)
        while not self.stop_event.is_set():
            try:
                msg = _recv_json_frame(sock)
            except socket.timeout:
                continue
            if msg is None:
                break
            if isinstance(msg, dict) and "Connection" in msg:
                conn_id = msg["Connection"]
                threading.Thread(
                    target=_handle_incoming,
                    args=(conn_id, self.local_host, self.local_port),
                    daemon=True
                ).start()
            elif msg == "Heartbeat":
                pass

    def run_forever(self):
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:
                print(f"[BORE] 隧道连接中断: {e}", flush=True)
            finally:
                if self.control_sock:
                    try: self.control_sock.close()
                    except Exception: pass
                    self.control_sock = None
            if not self.stop_event.is_set():
                time.sleep(2)
