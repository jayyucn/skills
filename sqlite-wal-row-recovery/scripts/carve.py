import json, re

SRC_DB = r'C:\Users\jay\AppData\Roaming\com.comind.app\workspace-dev\sqlite\comind.db'
SRC_WAL = r'C:\Users\jay\AppData\Roaming\com.comind.app\workspace-dev\sqlite\comind.db-wal'
PAGE_ID = '70fd44244effd08e2ea922cb41c6bbc8'
UUID_RE = re.compile(rb'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def varint(buf, off):
    v = 0
    for i in range(9):
        if off + i >= len(buf):
            return None, 0
        b = buf[off + i]
        if i == 8:
            return (v << 8) | b, 9
        v = (v << 7) | (b & 0x7F)
        if not (b & 0x80):
            return v, i + 1
    return v, 9


def ser_len(st):
    if st in (0, 8, 9, 10, 11):
        return 0
    if st <= 6:
        return [0, 1, 2, 3, 4, 6, 8][st]
    if st == 7:
        return 8
    return (st - 12) // 2 if st % 2 == 0 else (st - 13) // 2


def parse_record(data, rs):
    hlen, hl = varint(data, rs)
    if hlen is None or not (2 < hlen < 200) or rs + hlen > len(data):
        return None
    hdr = data[rs:rs + hlen]
    sts, o = [], hl
    while o < hlen:
        st, n = varint(hdr, o)
        if st is None:
            return None
        sts.append(st)
        o += n
    if o != hlen:
        return None
    vals, vo = [], rs + hlen
    for st in sts:
        L = ser_len(st)
        raw = data[vo:vo + L]
        if len(raw) < L:
            return None
        vo += L
        if st == 0:
            vals.append(None)
        elif st >= 13 and st % 2 == 1:
            try:
                vals.append(raw.decode('utf-8'))
            except UnicodeDecodeError:
                return None
        else:
            vals.append(int.from_bytes(raw, 'big') if L else 0)
    return vals


rows = {}
for src in (SRC_DB, SRC_WAL):
    data = open(src, 'rb').read()
    needle = PAGE_ID.encode()
    pos = 0
    while True:
        p = data.find(needle, pos)
        if p < 0:
            break
        pos = p + 1
        for back in range(0, 200):
            rs = p - back
            if rs < 0:
                break
            vals = parse_record(data, rs)
            if not vals or len(vals) < 11:
                continue
            if not (isinstance(vals[0], str) and UUID_RE.match(vals[0].encode())):
                continue
            if vals[1] != PAGE_ID or not isinstance(vals[3], int):
                continue
            key = vals[0]
            prev = rows.get(key)
            if prev is None or vals[8] > prev[8]:
                rows[key] = vals
            break
    print(src.split('.')[-1], 'cumulative rows:', len(rows))

out = sorted(rows.values(), key=lambda v: (v[2] or '~', v[3]))
print('total', len(out))
for v in out:
    print(json.dumps(v, ensure_ascii=False))
json.dump(out, open(r'D:\comind\.workbuddy\tmp\recovered.json', 'w'), ensure_ascii=False, indent=1)
