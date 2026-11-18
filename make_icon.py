# -*- coding: utf-8 -*-
"""生成高清多尺寸黄色闪电 App 图标 (app.ico)"""
import os
import struct
import zlib
import math

def make_png(width, height, rgba_bytes):
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(rgba_bytes[y * stride : (y + 1) * stride])

    ihdr = struct.pack("!IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")

def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    p1x, p1y = poly[0]
    for i in range(1, n + 1):
        p2x, p2y = poly[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

def render_icon(size):
    # 使用 2x2 超采样抗锯齿
    buf = bytearray(size * size * 4)
    # 经典闪电多边形坐标 (归一化 0~1)
    bolt = [
        (0.56, 0.14),
        (0.24, 0.54),
        (0.49, 0.54),
        (0.42, 0.86),
        (0.76, 0.44),
        (0.51, 0.44),
    ]
    # 轻微偏移的闪电阴影
    bolt_shadow = [(px + 0.02, py + 0.03) for px, py in bolt]

    margin = 0.06
    radius = 0.22

    def sd_rounded_rect(u, v):
        # 圆角矩形有向距离函数
        cx, cy = abs(u - 0.5), abs(v - 0.5)
        bx, by = 0.5 - margin - radius, 0.5 - margin - radius
        dx = max(cx - bx, 0.0)
        dy = max(cy - by, 0.0)
        return math.hypot(dx, dy) + min(max(cx - bx, cy - by), 0.0) - radius

    sub_offsets = [0.25, 0.75]

    for y in range(size):
        for x in range(size):
            r_acc = g_acc = b_acc = a_acc = 0.0
            for sy in sub_offsets:
                for sx in sub_offsets:
                    u = (x + sx) / size
                    v = (y + sy) / size
                    d = sd_rounded_rect(u, v)
                    if d <= 0:
                        # 温暖明快的金黄色垂直渐变 (#FDE047 -> #F59E0B)
                        t = max(0.0, min(1.0, (v - margin) / (1.0 - 2 * margin)))
                        br = 254 + (245 - 254) * t
                        bg = 224 + (158 - 224) * t
                        bb = 71 + (11 - 71) * t
                        ba = 255.0

                        # 细微内描边高光
                        if d > -0.025:
                            br = br * 0.92 + 255 * 0.08
                            bg = bg * 0.92 + 240 * 0.08
                            bb = bb * 0.92 + 150 * 0.08

                        # 绘制闪电阴影与亮白闪电主体
                        if point_in_poly(u, v, bolt):
                            br, bg, bb = 255.0, 255.0, 255.0
                        elif point_in_poly(u, v, bolt_shadow):
                            br, bg, bb = br * 0.78, bg * 0.72, bb * 0.55

                        r_acc += br
                        g_acc += bg
                        b_acc += bb
                        a_acc += ba
            idx = (y * size + x) * 4
            if a_acc > 0:
                buf[idx] = int(r_acc / (a_acc / 255.0))
                buf[idx + 1] = int(g_acc / (a_acc / 255.0))
                buf[idx + 2] = int(b_acc / (a_acc / 255.0))
                buf[idx + 3] = int(a_acc / 4.0)
            else:
                buf[idx] = buf[idx + 1] = buf[idx + 2] = buf[idx + 3] = 0
    return make_png(size, size, buf)

def build_ico(out_path):
    sizes = [256, 64, 48, 32, 16]
    pngs = [render_icon(s) for s in sizes]

    header = struct.pack("<HHH", 0, 1, len(sizes))
    entries = bytearray()
    offset = 6 + 16 * len(sizes)
    for s, png in zip(sizes, pngs):
        w = 0 if s == 256 else s
        h = 0 if s == 256 else s
        entries.extend(struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset))
        offset += len(png)

    with open(out_path, "wb") as f:
        f.write(header)
        f.write(entries)
        for png in pngs:
            f.write(png)
    print(f"Generated ICO: {out_path} ({os.path.getsize(out_path)} bytes)")

if __name__ == "__main__":
    build_ico(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico"))
