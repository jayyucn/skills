"""AI 生图 → UI 图标：抠透明底 + 裁留白 + 描边重量归一（形态学膨胀）+ 18px 浅/暗底预览。

纯标准库（zlib + struct），不依赖 PIL —— 本机 managed python / 新建 venv 无网络装不了包。
若 imgmeta env 可用（已装 PIL），随便换成 PIL 更快，但本脚本足以跑通。

用法：改下面 CONFIG，然后
  C:/Users/jay/.workbuddy/binaries/python/envs/imgmeta/Scripts/python.exe png-alpha-dilate.py
（无 imgmeta 就用 managed python：C:/Users/jay/.workbuddy/binaries/python/versions/3.13.12/python.exe）

输出：DST（RGBA 单色墨稿，alpha 已抠+已加粗）；PREVIEW（便于肉眼判重量）。
"""

import os
import struct
import zlib

# ── CONFIG ────────────────────────────────────────────────────────────────
SRC = r'C:\path\to\generated.png'          # 生图产物（多是不透明白底）
DST = r'D:\comind\src\assets\icon.png'     # 落仓位置
PREVIEW = r'C:\Users\jay\AppData\Local\Temp\icon_preview.png'
RATIO = 0.083        # 目标描边占比。lucide = stroke-width 2 / viewBox 24 = 8.33%
PAD_RATIO = 0.08     # 裁切后再留的白边比例（相对字形）
DISPLAY = 18         # 组件里的实际显示尺寸（px），预览按它降采样
ZOOM = 10            # 预览放大倍数
LIGHT_BG = (242, 242, 244)
DARK_BG = (30, 30, 32)
INK_RGB = (0, 0, 0)  # 统一墨色：纯黑 → 暗色模式可整体 invert(1)
# ──────────────────────────────────────────────────────────────────────────


def decode_rgba(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'\x89PNG\r\n\x1a\n', 'not a PNG'
    off = 8
    idat = b''
    w = h = bd = ct = None
    while off < len(d):
        ln = struct.unpack('>I', d[off:off + 4])[0]
        typ = d[off + 4:off + 8]
        chunk = d[off + 8:off + 8 + ln]
        off += 12 + ln
        if typ == b'IHDR':
            w, h, bd, ct, comp, flt, inter = struct.unpack('>IIBBBBB', chunk)
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp = ch * (bd // 8)
    stride = w * bpp
    out = bytearray()
    prev = bytearray(stride)
    i = 0
    for _ in range(h):
        f = raw[i]
        i += 1
        line = bytearray(raw[i:i + stride])
        i += stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                line[x] = (line[x] + (a if (pa <= pb and pa <= pc) else (b if pb <= pc else c))) & 255
        out += line
        prev = line
    return w, h, ct, bpp, stride, out


def encode(path, w, h, alpha):
    def chunk(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        base = y * w
        for x in range(w):
            raw += bytes(INK_RGB) + bytes((alpha[base + x],))
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b'')
    open(path, 'wb').write(png)


def dilate(a, w, h, R):
    """可分离最大滤波（方形结构元），描边 +2R。"""
    W, H = w + 2 * R, h + 2 * R
    c = [0] * (W * H)
    for y in range(h):
        s, d = y * w, (y + R) * W + R
        c[d:d + w] = a[s:s + w]
    for y in range(H):
        base = y * W
        row = c[base:base + W]
        for x in range(W):
            lo, hi = max(0, x - R), min(W - 1, x + R)
            c[base + x] = max(row[lo:hi + 1])
    for x in range(W):
        col = c[x::W]
        for y in range(H):
            lo, hi = max(0, y - R), min(H - 1, y + R)
            c[y * W + x] = max(col[lo:hi + 1])
    return c, W, H


w, h, ct, bpp, stride, out = decode_rgba(SRC)
print(f'src {w}x{h} colortype={ct}')


def lum(x, y):
    o = y * stride + x * bpp
    r, g, b = out[o], out[o + 1], out[o + 2]
    return (r * 299 + g * 587 + b * 114) // 1000


# 抠 alpha（按最暗处归一化）+ bbox
TH = 245
minx, miny, maxx, maxy = w, h, -1, -1
lmin = 255
for y in range(h):
    for x in range(w):
        L = lum(x, y)
        lmin = min(lmin, L)
        if L < TH:
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
gw, gh = maxx - minx + 1, maxy - miny + 1
pad = int(max(gw, gh) * PAD_RATIO)
x0, y0 = max(0, minx - pad), max(0, miny - pad)
x1, y1 = min(w - 1, maxx + pad), min(h - 1, maxy + pad)
ow, oh = x1 - x0 + 1, y1 - y0 + 1
side = max(ow, oh)
denom = max(1, 255 - lmin)
alpha = [0] * (side * side)
offx, offy = (side - ow) // 2, (side - oh) // 2
for yy in range(oh):
    for xx in range(ow):
        a = (255 - lum(x0 + xx, y0 + yy)) * 255 // denom
        alpha[(yy + offy) * side + (xx + offx)] = min(255, max(0, a))
print(f'keyed: bbox {gw}x{gh} -> canvas {side}, lmin={lmin}')


def stroke_runs(arr, W, H):
    base = (H // 2) * W
    runs, s = [], None
    for x in range(W):
        if arr[base + x] > 128 and s is None:
            s = x
        elif arr[base + x] <= 128 and s is not None:
            runs.append(x - s)
            s = None
    return runs


runs0 = stroke_runs(alpha, side, side)
scurrent = min(runs0) if runs0 else 0
R = max(0, round((RATIO * side - scurrent) / (2 * (1 - RATIO)))) if scurrent else 12
print(f'stroke before={scurrent}px ({scurrent/side:.1%}) -> dilate R={R}')

dil, W, H = dilate(alpha, side, side, R)
runs1 = stroke_runs(dil, W, H)
print(f'stroke after={min(runs1) if runs1 else "?"}px / canvas {W} = {((min(runs1) if runs1 else 0)/W):.1%} (target {RATIO:.1%})')

os.makedirs(os.path.dirname(DST), exist_ok=True)
encode(DST, W, H, dil)
print('wrote', DST, os.path.getsize(DST), 'bytes')

# 预览：面积平均降到 DISPLAY，再最近邻 ×ZOOM，浅/暗底并排
small = [0.0] * (DISPLAY * DISPLAY)
for dy in range(DISPLAY):
    for dx in range(DISPLAY):
        y0, y1 = dy * H / DISPLAY, (dy + 1) * H / DISPLAY
        x0, x1 = dx * W / DISPLAY, (dx + 1) * W / DISPLAY
        tot, cnt = 0.0, 0
        for iy in range(int(y0), min(H, max(int(y1), int(y0) + 1))):
            for ix in range(int(x0), min(W, max(int(x1), int(x0) + 1))):
                tot += dil[iy * W + ix]
                cnt += 1
        small[dy * DISPLAY + dx] = tot / max(1, cnt)

tile, gap = DISPLAY * ZOOM, 20
TW, TH_, PIX = tile * 2 + gap * 3, tile + gap * 2, bytearray(b'\xf0\xf0\xf0' * ((tile * 2 + gap * 3) * (tile + gap * 2)))
for idx, (bg, invert) in enumerate(((LIGHT_BG, False), (DARK_BG, True))):
    ox, oy = gap + idx * (tile + gap), gap
    for dy in range(DISPLAY):
        for dx in range(DISPLAY):
            a = small[dy * DISPLAY + dx] / 255.0
            ink = 255 if invert else 0
            px = tuple(round(bg[k] * (1 - a) + ink * a) for k in range(3))
            for yy in range(ZOOM):
                base = ((oy + dy * ZOOM + yy) * TW + (ox + dx * ZOOM)) * 3
                for xx in range(ZOOM):
                    PIX[base + xx * 3:base + xx * 3 + 3] = bytes(px)


def encode_rgb(path, w, h, rgb):
    def chunk(t, data):
        return struct.pack('>I', len(data)) + t + data + struct.pack('>I', zlib.crc32(t + data) & 0xffffffff)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += bytes(rgb[y * w * 3:(y + 1) * w * 3])
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


encode_rgb(PREVIEW, TW, TH_, PIX)
print('preview', PREVIEW)
