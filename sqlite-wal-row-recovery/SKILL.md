---
name: sqlite-wal-row-recovery
description: 从 SQLite 主库文件 + WAL 中雕刻（carve）恢复被 DELETE 掉的行。当某个本地应用的数据被硬删（无软删/无备份/无回收站）、但 sqlite 文件与 -wal 还在时使用。按已知主键回溯记录头解析 SQLite record，取每行最新版本。已在 comind（Tauri 应用，workspace/sqlite/comind.db）实战恢复 8 行。
agent_created: true
---

# SQLite WAL 行雕刻恢复

**适用**：某行被 `DELETE`（真删，不是软删标记），没有备份/快照，但 `.db`（可能还有 `-wal`）文件仍在磁盘上。
**原理**：SQLite 删除行只是从 B-tree 叶子页里摘掉 cell，**页字节不会被立刻清零**。旧版本的页仍留在主库文件（未被 checkpoint 覆盖的部分）和 WAL 的历史帧里。按主键字符串定位、回溯解析 record，即可把整行取回。

## 铁律

1. **先停机或至少知道风险**：应用在跑时 WAL 可能被 checkpoint（把 WAL 页刷进主库并覆盖旧页）→ 可雕刻的旧页消失。**先做文件快照**：把 `*.db`、`*.db-wal` 复制到别处再动手。
2. **不要用 SQLite 自己"恢复"**：删掉的行对 `sqlite3` 不存在，`VACUUM`/`REINDEX` 会把旧页真正覆盖掉——**任何写操作都可能让恢复变成不可能**。只读、只复制。
3. **恢复 = 重新 INSERT**，不是修 B-tree。拿到行的列值后用正常 SQL `INSERT` 写回（保留原主键与 pos/parent 等字段），让应用层重新看到它。
4. **取每行最新的那个版本**：同一行可能在多个历史页镜像里出现多份（不同 `updated_at`）。按"每主键取最大 `updated_at`"去重，否则会恢复出过期内容。

## 步骤

1. 拿到库文件路径。Tauri：`manage_ipc invoke get_db_path`，或直接 `ls <appdata>/<app>/workspace*/sqlite/`。
2. 快照 db + wal 副本，记录 `page_size`（文件头 offset 16，2 字节大端；值为 1 表示 65536）。
3. 用下面的脚本，**给出已知的主键值**（把要恢复的行的 id 列出来）。脚本对 db 与 wal 都扫。
4. 核对输出（尤其 `content`、`parent_id`、`pos`、`format`），确认取到的是删除前的最新值。
5. 用 SQL `INSERT` 写回，再让应用刷新（comind 用 `navigate(action='reload')`）。
6. **让用户自己复核**结果，并说明恢复是基于免费页镜像的"尽力而为"，可能拿到稍旧的内容。

## 脚本

`scripts/carve.py`（把 `SRC_DB`/`SRC_WAL`/`PRIMARY_KEYS`/`TABLE_COLUMNS` 改成本次目标）。

```python
import json, re

SRC_DB = r'...\comind.db'
SRC_WAL = r'...\comind.db-wal'
PAGE_ID_COL = 'page_id'          # 用来定位「同属一张表」的列值，通常是外键/租户 id
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

# 扫描：以「某个已知列值」为锚点（这里用 page_id），回溯 record 头
# 也可直接以主键字符串为锚点
rows = {}
for src in (SRC_DB, SRC_WAL):
    try:
        data = open(src, 'rb').read()
    except FileNotFoundError:
        continue
    needle = PAGE_ID_COL_VALUE.encode()          # 改成实际值
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
            if vals[1] != PAGE_ID_COL_VALUE:
                continue
            prev = rows.get(vals[0])
            if prev is None or vals[8] > prev[8]:   # 取 updated_at 最大者
                rows[vals[0]] = vals
            break

out = sorted(rows.values(), key=lambda v: (v[2] or '~', v[3]))
for v in out:
    print(json.dumps(v, ensure_ascii=False))
json.dump(out, open(r'...\recovered.json', 'w'), ensure_ascii=False, indent=1)
```

## 关键点（为什么这么写）

- **record 头回溯**：record 首字节是「头长度」varint，其后是各列 serial type。主键是第一列，所以**主键值的起始 offset == record 起始 offset + 头长度**。反过来从主键串位置往前试 1..200 字节，找到满足 `rs + varint(data,rs) == 主键位置` 的那个 `rs` 即是记录头——比解析整页 B-tree 简单得多，且天然跨页/跨 WAL 帧工作。
- **列数/类型不写死**：完全由 record 自带头驱动，列数变化（改过 schema）不会导致错位，只会让 `parse_record` 返回列数不同的结果，再用 `len(vals) >= N` 过滤。
- **STRING 索引用**：`ser_len` 是 SQLite serial type 的解码规则（0=NULL，1..6=整型宽度，7=float，8/9=0/1 常量，≥12 偶数=BLOB、奇数=TEXT，长度 `(st-12)//2` 或 `(st-13)//2`）。
- **锚点选择**：主键本身或任意"恢复目标共有、且不在别处频繁出现"的长字符串（UUID/外键）最好。用短字符串当锚点会命中太多噪声。
- **db 与 wal 都要扫**：最新版本可能在任一文件里。WAL 帧头 24 字节 + 页内容，直接整文件字节扫描即可，无需按帧解析。

## 太晚了的补救

如果 WAL 已被 checkpoint 且主库文件也被反复覆写（旧页已被回收再用），雕刻基本会失败。此时退路：
1. 找应用自己的历史/版本表（comind 是 `BlockVersion`）、FTS 索引表（`SearchIndex_content` 常残留已删行文本）——只能救内容，救不了结构。
2. 让用户从截图/记忆里人工重建。
3. **事后补软删**：把删除改成 `deleted_at` 标记（comind 的 `Block.deleted_at` 列已存在，但 `delete_block_cascade` 走的是硬删——这正是本次需要雕刻的原因）。
