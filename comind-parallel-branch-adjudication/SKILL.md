---
name: comind-parallel-branch-adjudication
description: 裁定 comind 里「同一批工作落在两条互不相交的提交链上」（多会话并行作业、临时索引 + commit-tree 落库、分支重做、pull --rebase 撞已推送的同名 amend 提交所致）该以哪条为准，并安全落地到本地 ref。当发现同名同主题但 sha 不同的提交、「日志说已推送但 git 查不到」、或 rebase 中途一片 UU 时使用。含只读量化判据（哪条更完整）、merge-tree 试算净增量的 rebase 撞车配方、保锚点、update-ref 重指、以及「是否真已推送」的实测法。末节另覆盖「同一工作树被多会话并发写」与「checkout 后索引是假的」两类现场处置。
agent_created: true
---

# comind：平行链裁定与安全落地

## 触发
- `git log --all --oneline --grep="#<issue>"` 里出现**同名同主题、sha 不同**的提交（如 `b81c9bb` 与 `53949ac` 都是「#104 下架」）
- 日志/记忆说「已推送」，但 `git merge-base --is-ancestor <sha> <远端 tip>` 返回 false
- 多会话（agent / IDE 窗口）同仓作业后，ref 或工作树对不上
- `git status` 里冒出**不是自己写的**改动（同一 working tree 被并发编辑）⇒ 直接跳到文末「支线」一节
- **`pull --rebase` 中途停下、多个文件 `UU`** ⇒ 先读文末「支线二」再决定解法

## 第 0.5 步：rebase 冲突先判「是否撞已存在的同名提交」
**rebase 撞车与真代码冲突要分开。** 判据（三条全中即确诊）：
```bash
cat .git/rebase-merge/head-name .git/rebase-merge/onto .git/rebase-merge/orig-head
git log --oneline <onto> | grep "<主题关键词>"        # onto 链上是否已有同名同主题提交
git rev-parse --short <stopped-sha>^                  # 被重放提交的父
```
确诊后**不要逐 hunk 解冲突** —— 那是手工重做已存在的工作，且 onto 在那提交之后还叠了新提交时必错。
正解见文末「支线二」。

## 第 0 步（铁律）：先判「是否真已推送」
**永远不信日志措辞。** 唯一硬证据：
```bash
git ls-remote <remote> refs/heads/<branch>          # 远端 tip
git cat-file -e <远端 sha>:<标志性文件>               # 该文件在此 sha 的树里存在？（exit 0 = 在）
git merge-base --is-ancestor <sha> <远端 tip>        # true ⇒ 该提交已在此链上
```
标志性文件 = 该功能独有、不易碰巧存在的路径（本次用 `src/composables/useUndoHistory.ts`、`src/utils/undo-chord.ts`、`src/components/BlockList.undo-redo.test.ts`）。
**陷阱**：`--is-ancestor` 是按 sha 判的；平行链上「内容等价但 sha 不同」的提交一律返回 false，所以它只能证「已推送」，**不能**证「未推送」。

## 第 1 步：建链图
对每个候选提交查父提交，找出两条链的分叉点：
```bash
git rev-parse --short <sha>^          # 父
git log --oneline --graph -10 <tip>   # 线性段
```
本次分叉点 = 远端 `main` 的 tip（`be395b8`），两条链各自 7–9 个提交。

## 第 2 步：量化完整性（只读，决定「以哪条为准」）
1. `git diff --stat <B> <A>` → 看净行数方向（本次 14 文件 / +168/−1201 ⇒ A 净少 1033 行）。
2. **逐文件行数并排**才是决定性的：
```bash
for f in <标志性文件列表>; do b=$(git show <B>:$f | wc -l); a=$(git show <A>:$f | wc -l); printf "%-46s %6s %6s\n" "$f" "$b" "$a"; done
```
经验：更完整的版本在**多数**标志性文件上更长，但**要接受个别文件反超**（旧版残留）—— 本次 A 只在 `useUndoHistory.ts` 多 6 行。**不可只看总行数下结论。**
3. 交叉验证文档与类型（落后的那版常「文档说一套、代码做另一套」）：
   - `git diff <B> <A> -- docs/` → 本次 `interaction-spec.md` A 写「待实施」/ B 写「已实现」；ADR-0046 D9 A 写「deep watch」/ B 写「签名归因」
   - `git diff <B> <A> -- src/wasm/types.ts` → 本次 A 缺 `undelete` action
   - 另查功能符号存在性：`git show <sha>:<file> | grep -cE "<symbol>"`（本次 `blockSig|propSig` 两版都有 ⇒ A 的 ADR 落后于自己的代码）

## 第 3 步：**先保锚点**（关键顺序）
```bash
git update-ref refs/heads/chain-a-<sha> <即将被替代的 sha>
```
**必须在重指任何 ref 之前做。** comind 是多会话仓库，被替代的链随时可能消失：本次实测到本地两个分支的 ref **与 reflog 文件同时消失**（干净删除形态，时间窗与另一会话的写操作重合）。

**但本地锚点本身也不牢（2026-09-15 三次实测）**：本环境会**只删「非当前 HEAD」的本地分支**并把 HEAD 收敛回某个固定分支 —— `main`、`fix-undo-restore-props`、`chain-a-ffeb202` 先后消失（`update-ref` 建的也算），而工作区文件、`.workbuddy/` 记忆、对象层（`cat-file -t` 仍可读）不受影响。
⇒ 结论：**本地 `update-ref` 锚点只能覆盖「同一会话内的下一步操作」这个窗口**。要真正保住一条链，锚点必须 **push 到远端**：
```bash
git push <remote> <sha>:refs/heads/chain-a-<sha>
```
同理，**交付不要锚在本地分支上** —— 用远端分支 + PR 承载（本次最终由 PR #112 承载）。

## 第 4 步：落地（白名单最小写）
```bash
git update-ref refs/heads/<target> <胜出链 sha>
```
- 若胜出链是当前分支的祖先 ⇒ 纯 fast-forward；核对 `git rev-list --left-right --count <远端>/<branch>...<target>`（本次 `0 6` = 不落后、领先 6 个）。
- **`update-ref` 不动工作区**：若现盘已是目标版本，不要 checkout 覆盖。

## 第 5 步：HEAD 归位 + 验证
```bash
git checkout <target>        # 同 sha 切换 ⇒ 工作区零变动；单条执行，不 && 拼接
git diff <sha>               # 应为零
git status --short --branch  # 应干净
```

## 陷阱
- **禁** `stash` / `reset --hard` / `checkout .` / `gc` / `prune`（见用户级 git 铁律）。全程只用 `update-ref` + 单条 `checkout`。
- 全程 `dangerouslyDisableSandbox: true`；沙箱内 git 会把**完好**仓库显示成 `not a git repository` / `bad object`，不可据此「恢复」。
- 先确认工作区对应哪条链：`git diff --shortstat <A>` / `<B>` 各跑一次，**零差异的那条就是现盘**（本次现盘 = B，故只需改 ref）。
- 不删被替代的分支（留作锚点），也不把「同名不同 sha」的提交当作重复工作删除 —— 它们可能含文档增量。
- 裁定属**外部可见决策**：落地前把「哪条更完整」的量化结果摆给用户，由他拍板（本次 Jay 裁定「以 B 为准」）。

---

## 支线：**同一工作树被多会话并发写**（不是平行链，是并发编辑）
比平行链更常见、更容易误伤：另一个会话正在同一 `working tree` 里写文件，而你完全不知道。

### 识别（三条独立信号，任一命中就要查）
- `git status --short` 出现**你没写过的**文件（如 `QueryPageFrame.vue`）
- Edit 工具报 `File has been modified since read` —— **这是最硬的信号**，说明你的读与写之间文件被外部改过
- `ls -l --time-style=+%H:%M:%S <文件...>` 的 mtime **集群式落在你本次会话的时间窗内**（本次实测 22:14:48 / 22:14:57 / 22:15:33）

### 归属判定（只读）
```bash
git diff --numstat                                  # 全量改动 + 行数
git show HEAD:<可疑文件> | grep -c '<标志符号>'        # 0 ⇒ 该符号是本轮新增，不是 HEAD 既有
git diff -U0 -- <文件> | grep '^+.*<符号>'           # 确认增行确实来自别人
```
反例陷阱：只比总行数 / 只看 `status` 的 `M` 标记，**判不出「同一个文件里既有我的 hunk 又有他的 hunk」**。必须看 `git diff` 的具体 hunk。

### 划提交边界：共用文件切不开
- 文件分两类：**纯属我的**（可安全 `git add`）vs **两路共用**（同一文件含双方 hunk）。
- 共用文件在**不做 hunk 级暂存**的前提下无法切开；而本环境禁 `stash`、`git add -p` 又是交互命令 ⇒ **实际不可切**。
- 所以：**共用文件留给对方提交**，自己的提交只含「纯属我的」文件。本次共 7 个纯属文件 vs 2 个共用文件（`TagAggregateBody.vue` / `TagAggregatePage.test.ts`）。
- 若这样会让本次切片不完整（调用点留在未提交侧），**先问用户**，别自己拍板「一并提了更完整」。用户明令：拿不准停下来问。
- **绝不 `git add -A`**：那等于替另一路决定提交内容，而它可能立刻继续改同一文件。

### 文档类共用文件：我的段落只能「搭车」
- `docs/`（ADR / `glossary.md` / `CONTEXT.md`）是最常被两路同时改的载体：对方补它的术语表 / ADR 段落，我回写自己的决策段落 —— 同一文件两个 hunk，同样切不开。
- 判定同源：`git diff <file>` 看 hunk 是否落在「我的段落」之外；同文件即判共用。
- 处理（沿用「纯属优先」）：**照常改自己的段落，但该文件不提交**，并在报告里显式写明「我的段落留在工作树，可能被对方下一次提交一并带走」。不要为了让它落库而 `git add` 整个文件。
- 反向也要防：**改之前先 `git diff` 确认要动的那段是不是对方刚写的**（本次要改的 D7 段落即对方所写 ⇒ 只能避让，不能在它上面改写/重排）。
- 边界情形：文件在 `status` 里**干净**（如 `CONTEXT.md`）即判纯属我的 ⇒ 可提交；但并发窗口下它可能在你提交前一瞬变脏 ⇒ **提交前重跑 `git status` 复核**。

### 提交后复验
```bash
git show --stat --oneline HEAD   # 文件清单必须恰为预期（数量 + 路径逐项对上）
git rev-parse HEAD ; git status --short ; git branch -vv   # 三条健康检查
```

### 两个已实证的细节
- `lint-staged` 跑 `eslint --fix` 后会**重新 add**，但只碰本次 staged 的文件 —— 不会把相邻的未暂存改动带进提交（本次提交后另一路的文件仍为 `M`）。
- 并发写入期间**不要跑可能被对方的写打断的长验证**（如 `vue-tsc -b` 与 vitest 并行）：本次在并行窗口里读到过一条**瞬时假错误**（`TS6133: 'candidateFields' is declared but its value is never read`，而模板里明明绑定着它），单跑即消失。**报错与源码自相矛盾时，重跑一次再定性。**

---

## 支线二：**`pull --rebase` 撞已存在的同名提交**（`checkout HEAD -- <file>` 之外的第三条路）

症状：`git status` 一片 `UU`，但 `git merge-base --is-ancestor <被重放提交> <onto>` = **false**，
且 onto 链上有一条**同名同主题**的提交。

### 病根
本地 amend 过某提交，但**旧版已被推到远端**。rebase 会把「父 → amend 版」的**整块内容**重放到
已含该内容的 onto 上 ⇒ 全撞。onto 在那提交之后还叠了新提交时，逐 hunk 解必然解错。

### 配方（顺序不可换，见下方铁律）
```bash
# ① 先锚点（被 rebase 的 tip 随时可能变不可达）
git update-ref refs/heads/anchor-<主题>-<短sha> <被重放sha>

# ② 只读试算「净增量」落在 onto 上是否干净（决定性判据）
git merge-tree --write-tree --merge-base=<远端已有版> <onto> <amend版>
#   exit 0 且输出只有一个 tree sha（无 CONFLICT 行）⇒ 零冲突，可走此路

# ③ 用该 tree 造干净提交（不依赖工作区，故可先做、成果先落对象库）
git commit-tree <tree> -p <onto> -F <msg文件>

# ④ 锚定新提交，再清 rebase
git update-ref refs/heads/anchor-<主题>-new <新sha>
git rebase --skip

# ⑤ 分支指过去 + 同步磁盘（见下方「checkout 后索引是假的」）
git update-ref refs/heads/<branch> <新sha>
git checkout <branch>
git checkout HEAD -- <逐文件>        # 磁盘没跟上时
git read-tree HEAD
```

### 铁律：`checkout` 之后索引是假的
`update-ref` + `checkout <branch>` 可能打印 "M ..." 且索引显示新内容，**而磁盘上仍是旧内容**
（本环境「索引写入跨命令不持久」的又一表现）。
⇒ **判据不能信 `git status`**，必须**直接 grep 磁盘**：
```bash
grep -c '<新命名的符号>' src/composables/useUndoHistory.ts    # 0 ⇒ 磁盘没跟上
git checkout HEAD -- <逐文件>                                  # 白名单，可逐文件救
```
注意 `git diff --stat` 与 `git diff --cached --stat` 此时会给出「互相抵消」的假象（未暂存为空
+ 已暂存是反向增量），**两者同时看才能发现索引与磁盘不同源**。

### 改信封字段名前：先分清同名不同物
同一概念在内存信封与存储格式契约里**可以同名**。改 A 的字段名时 grep 到的 `B.同名字段` 往往
**不是漏改**。判定流程：`git grep '<旧字段名>'` 命中的非测试文件 → 查它的**类型定义来自哪个文件**
→ 若该类型注释写明「snake_case 直通库」/「存储格式」，则**不许跟内存信封一起改名**。
本次实证：`HistoryEntry.fieldValues`（内存）要改名，而
`IdeasSnapshotData.properties`（`utils/ideas-snapshot.ts`，`content_json` 直通库）必须保持原样，
其消费点 `BlockModal.vue` / `IdeasSnapshotPage.vue` 照旧读 `properties`。
