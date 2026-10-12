---
name: comind-doc-writeback
description: 在 comind 仓库回写 tracked 文本（ADR / CONTEXT.md 术语表 / docs 规格文档 / CRLF 的 `.ts`·`.rs` 源码）的机械动作安全流程——二进制读写保住原换行符、每处替换断言「命中恰好 1 次」、原子落盘、整段替换用锚点切片、改完核 numstat 与换行符、临时脚本删净。当需要把一轮裁定/决策写进 docs/adr 或其它 tracked Markdown、修改既有 ADR 的多处段落、或对 CRLF 源码做整段/单行替换时使用。
agent_created: true
---

# comind 载体回写（ADR / CONTEXT.md / 规格文档）

先例：ADR-0046 / ADR-0047 的撰写与两轮回写（2026-09-14）。本仓 tracked 的 `.md` 与 `.rs`/`.ts` 多为 **CRLF**，而 `docs/adr/` 与 `.workbuddy/memory/*.md` 实测为 **LF** —— 改错换行符会污染整个文件的 diff。

## 铁律

1. **先核换行符，再动手**：`git ls-files --eol <file>`（tracked）；未跟踪的文件用 Python 数字节（`b.count(b'\r\n')`）。
   **禁用 `grep -c $'\r'`** —— 本环境下它退化成**行数**，曾因此把整文件当一行替换、清空文件后半段。
2. **写多行内容一律走 `.py` 脚本 + 二进制读写**（`open(p,'rb')` / `open(p,'wb')`），不要把含反引号 / `|` / `$` 的 markdown 塞进 bash 命令行（反引号会被当命令替换执行，`a > b` 形状的片段会被当重定向、在你当前目录创建垃圾文件）。
3. **每处替换断言「命中恰好 1 次」**，且**全部命中才落盘**（脚本先在内存里改完、校验通过再一次性 write）。副作用：某一处 old 串没过时，前面的成功也不会污染文件 —— 这个「原子写」设计已实际救过一次。
4. **多行 old 串禁止凭记忆拼**。先执行 `find()` 并 `print(repr(...))` 打印**真实字节**，照抄结果。臆造一行引用 → 命中 0 次 → 脚本退出（本仓已发生两次）。

## 标准流程

```bash
# 1) 核换行符 + 确认改动面干净
git status --short
git ls-files --eol <file>
# 2) 写脚本（Write 工具写入 .workbuddy/tmp-*.py，勿用 heredoc/命令行内联）
# 3) 跑
python .workbuddy/tmp-xxx.py
# 4) 清理 + 复验
rm -f .workbuddy/tmp-xxx.py
git status --short && git diff --numstat -- <dir>
```

脚本骨架：

```python
import sys
P = 'docs/adr/00NN-xxx.md'
b = open(P, 'rb').read()
assert b.count(b'\r\n') == 0, 'expected LF'   # 若是 CRLF 仓文件则反向断言
s = b.decode('utf-8')

def rep(old, new, tag):
    n = s.count(old)
    if n != 1:
        print('FAIL', tag, 'hits=', n); sys.exit(1)
    return s.replace(old, new)

s = rep('...', '...', 'P1')
# ... 其余处
out = s.encode('utf-8')
open(P, 'wb').write(out)
print('OK bytes', len(out), 'crlf', out.count(b'\r\n'), 'lines', out.count(b'\n'))
```

## 复验（缺一不可）

- 打印**落盘后的** bytes / crlf / lines 三个数并核对：换行符计数必须**保持改动前的值**（LF 文件仍为 `crlf 0`）。
- `git diff --numstat -- <file>`：**只做单行、old/new 均不含换行字符的替换时，应恰为 `1 1`**；若等于整文件行数 = 该文件被翻成另一种换行符，立刻还原重做。
- `git status --short`：改动文件应恰为你预期的那些；出现 `??` 的意外新文件（反引号事故的垃圾文件）立即删。

## 同法适用于源码（不只文档）：逐文件核换行符

2026-09-14 #104 实证：**同一仓库内两种换行符混存** —— `src/composables/useRightSidebar.ts` 是 CRLF，而 `src/App.vue` / `src/stores/blocks.ts` 是 LF。别按「本仓是 CRLF」一刀切，**逐文件核**；改错就是把整文件 diff 翻成另一种换行符。

- **单行替换**（old/new 都不含换行字符）→ Edit 工具即可，事后核 `numstat` 应为 `1 1`。
- **整段/整个函数替换 → 用锚点切片，不要照抄多行 old 串**（含 CJK 标点、全角括号、em dash 时最易记错，本仓已吃过两次）。锚点切片把「照抄」这一步整个省掉：

```python
ANCHOR_FN = 'export function reconcilePanels('.encode()
ANCHOR_NEXT = 'export function useRightSidebar() {'.encode()
i = b.index(ANCHOR_FN)
j = b.rindex(b'/**', 0, i)              # 连上面的 JSDoc 一起换
k = b.index(ANCHOR_NEXT, i)
assert b'reconcilePanels' in b[j:k] and b[j:k].count(b'export function') == 1
b = b[:j] + NEW_BYTES + b[k:]
```

- 插入内容**必须** `.replace('\n', '\r\n').encode('utf-8')` —— `.py` 脚本里的字面量是 LF，直接插入会把 CRLF 文件污染成混合换行（`.replace` 后仍是 `str`，忘 `.encode` 会报 `can't concat str to bytes`）。
- 复验：`git diff --numstat` 的合理值形如 `27 3`（新增行 + 被替换的旧行），**绝不等于整文件行数**；再 `python -c` 打印落盘后的 LF/CRLF 两数确认相等（CRLF 文件）或 CRLF 为 0（LF 文件）。

## 陷阱

- **`>` 引用行、加粗包裹的整句**最容易被记错；它们出现在 old 串里时，先打印再抄。
- 用 Edit 工具改 **LF** 文件：仅限「单行、old/new 都不含换行字符」的替换；**含换行的替换一律走二进制脚本**。`.workbuddy/` 下文件不提交，无法用 numstat 兜底 → 一律走脚本。
- 新增 tracked 文件（新 ADR）用 Write 落盘即可，但落盘后仍要核一次换行符与字节数。
- 写完后若需引用编号，**同步更新 `.workbuddy/memory/MEMORY.md` 的「ADR 已到 00NN，issue 最大 NNN」一处**（同一份记忆可能被并发会话改动 → 改前重读、改后复验行数）。

## append-only 日志追加（`.workbuddy/memory/YYYY-MM-DD.md`）

日志是**追加**语义，不走替换 —— 但同样必须进二进制脚本，且比替换多两道守卫：

1. **sha 并发守卫**：读盘时记 `sha256(b)[:16]`，脚本内**重新读盘**并断言 sha 未变；不一致就 `ABORT` 退出，重读后重写脚本。（同一份日志会被并行会话同时写，覆盖式落盘会吞掉对方整节。）
2. **防重复追加**：断言待追加的小节标题（如 `## T5 完成：…`）`not in s`，否则退出。
3. **补尾部换行**：`if not s.endswith('\n'): s += '\n'`，再补一个空行，保持节间空行约定。
4. **落盘后四数对照**（未跟踪文件无 numstat 兜底，这四个数就是兜底）：
   `bytes` 增量 ≈ 新增文本长度；`lines` 增量 = 新增行数；`crlf` **保持原值**；`back.startswith(原全文)` 必须为真（**前半段逐字节未变**）。

```python
raw = open(P, 'rb').read()
assert hashlib.sha256(raw).hexdigest()[:16] == EXPECT_SHA, '并发会话改过，ABORT'
text = raw.decode('utf-8')
assert '## T5 完成：' not in text, '已追加过'
if not text.endswith('\n'): text += '\n'
if not text.endswith('\n\n'): text += '\n'
text += section
out = text.encode('utf-8')
open(P + '.tmp', 'wb').write(out); os.replace(P + '.tmp', P)
back = open(P, 'rb').read()
assert back.count(b'\r\n') == crlf and back.startswith(raw)   # 四数对照
```

**长内容用「先 Write 一个 `.py` 再执行」**（本仓铁律）：含反引号 / `|` / `$` 的 markdown 塞进 bash 会触发命令替换与重定向事故。`MEMORY.md` 这类**替换**语义的长期记忆仍走上一节的标准流程（`rep()` 断言命中 1 次 + 原子写）。
