"""零写入：逐个文件比对「工作树 vs 远端 main tip」，得出真实提交清单。

分类：
  SAME_AS_UPSTREAM  工作树内容与上游同 blob（本地显示为 M/?? 只是索引陈旧造成的假象）
  NEW               上游没有这个文件（真·新增）
  DIFFERS           上游有，但工作树内容不同（真·改动）
  LOCAL_DELETED     上游有，工作树没有（真·删除）
"""
import os
import subprocess

REPO = "D:/comind"
TIP = "450d458"  # 远端 main tip


def git(*args: str, stdin: str | None = None) -> str:
    # -c core.quotepath=false：否则 ls-tree 会把非 ASCII 路径做 C 风格转义
    # （"docs/\346\212\200..."），与磁盘上的真实文件名失配 → 假报 LOCAL_DELETED。
    r = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=REPO,
                       capture_output=True, text=True,
                       input=stdin if stdin is not None else None)
    if r.returncode != 0 and not (args and args[0] in ("rev-parse",)):
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout


# 1) 上游整棵树：path -> blob sha
upstream: dict[str, str] = {}
for line in git("ls-tree", "-r", TIP).splitlines():
    meta, path = line.split("\t", 1)
    upstream[path] = meta.split()[2]

# 2) 本地未跟踪文件（索引视图之外的）
untracked = [p for p in git("ls-files", "-o", "--exclude-standard").splitlines() if p]

# 3) 候选集 = 上游全量 ∪ 本地未跟踪（+ 索引中相对上游有差异的，已含在上游全量里）
candidates = sorted(set(upstream) | set(untracked))

# 4) 工作树哈希：一次批量（注意传 path 形式 → 会按 .gitattributes 施加 eol 过滤，与仓库存储形态一致）
existing = [p for p in candidates if os.path.isfile(os.path.join(REPO, p))]
out = git("hash-object", "--stdin-paths", stdin="\n".join(existing) + "\n")
worktree = dict(zip(existing, out.split()))

rows: list[tuple[str, str]] = []
for p in candidates:
    wh = worktree.get(p)
    up = upstream.get(p)
    if wh is None:
        status = "LOCAL_DELETED" if up else "SKIP"
    elif up is None:
        status = "NEW"
    elif wh == up:
        status = "SAME_AS_UPSTREAM"
    else:
        status = "DIFFERS"
    rows.append((status, p))

counts: dict[str, int] = {}
for s, _ in rows:
    counts[s] = counts.get(s, 0) + 1
print("=== 分类计数 ===")
for k in sorted(counts):
    print(f"{counts[k]:5d}  {k}")

for want in ("NEW", "DIFFERS", "LOCAL_DELETED"):
    print(f"\n=== {want} ===")
    for s, p in rows:
        if s == want:
            print("  " + p)
