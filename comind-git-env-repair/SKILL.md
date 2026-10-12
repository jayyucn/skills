---
name: comind-git-env-repair
description: 当 comind 仓库（或本机任何仓库）出现「git 看起来坏了」的症状时使用，覆盖五类：① `rev-parse HEAD` 报 unknown revision / `status --short` 全库显示为 `A` / `for-each-ref refs/heads` 少了分支（refs 被重建、HEAD 悬空）；② `status` 报出几百个 M/?? 而用户坚称自己没改这么多（HEAD+index 双双陈旧，不是损坏；含陈旧索引下「commit 会整体回退上游」的致命陷阱与 read-tree 对齐配方）；③ `fatal: missing object <sha> for refs/remotes/...` 且 `git fetch` 报 `bad object`——fetch 自举死锁，用 heal-missing-refs.sh 绕开 ref 补对象；④ `git commit` 后 refs 全没、HEAD 变成字面量 `HEAD`——husky/lint-staged 内部调用 `git stash` 所致，改 `--no-stash` 根治；⑤ 提交报 `invalid object ...for '<path>'`——索引引用了被维护任务回收的对象，`git add` 是 no-op，须 `hash-object -w` 写回，且**本机绝不可跑 gc/repack**。全程不删分支、不动 main、不推送、不删 `.git` 内文件。附 delta_scan.py（逐文件哈希量化真实差异，含 core.quotepath 假报坑）与 heal-missing-refs.sh。
agent_created: true
---

# comind git 环境修复（悬空 HEAD / refs 消失）

## 这个仓库的已知环境缺陷（别再找错方向）

本环境**写不进带斜杠的本地 ref**：`git update-ref refs/heads/feat/undo-redo <sha>` 返回 `RC=0`，
但 `.git/refs/heads/feat/` 目录根本不创建（截至 2026-09-15 已 4 次实证）。
`git branch -m <名> feat/x` / `git checkout` 却会正常写 reflog ⇒ **HEAD 悬在一个盘上不存在的 ref 上 = unborn 分支**。
远端侧不受此限（`refs/remotes/comind/feat/...` 正常存在）。

**index 写入也不跨会话持久**（2026-09-18 实证）：上个会话 `git read-tree <tip>` 明明落了盘、
当时 `status` 也只显示 35 个真实改动；下个会话开工一看 `git diff --cached HEAD` 又是空的、
索引退回旧树、`status` 又报 219 改 —— **索引被还原了**。
⇒ 铁律：**每个 git 写操作后立刻验落盘**（`cat .git/HEAD` / `cat .git/refs/heads/<名>` / `git diff --cached --shortstat`），
开工第一件事也是复核；**永远不要信任「上个会话留下的中间态」**。

**症状三条（互相印证，见到任意两条即可确诊）**
1. `git rev-parse HEAD` → `fatal: ambiguous argument 'HEAD': unknown revision`
2. `git status --short` → 全库 900+ 条显示为 `A`（unborn 之下「一切皆新增」的假象，**不是索引损坏**）
3. `git for-each-ref refs/heads` → 只剩 `main`（或少了本该在的分支）

## 铁律：先救对象，再谈 refs

**对象存活与 ref 指向是两件事。** refs 没了 ≠ 提交丢了。顺序永远是：

```bash
git cat-file -t <sha>      # 对象在不在（commit / tree / blob）
git cat-file -t HEAD       # HEAD 指向的 ref 能不能解析
cat .git/logs/HEAD         # reflog 是唯一还记得「谁动过什么」的地方
cat .git/logs/refs/heads/<名>
```

`.git/logs/refs/heads/*` 里出现 `0000…→<sha>` = 该分支**被新建**；
`Branch: renamed A to B` = 有人跑过 `branch -m`（重命名只改 log，不改盘上 ref 实体 —— 本环境会丢）。
这一层能让「谁把 HEAD 弄悬空的」从猜测变成事实。

## 修复配方（不删分支、不碰 main、不推送）

```bash
# 1) 建一个【无斜杠】分支承接真实 tip（斜杠名写不进）
git update-ref refs/heads/feat-undo-redo <真实 sha>
ls -la .git/refs/heads/                      # 必须看到文件落盘，否则别往下走

# 2) HEAD 指过去
git symbolic-ref HEAD refs/heads/feat-undo-redo

# 3) 核验三条，全绿才算修好
git rev-parse HEAD                           # = 真实 sha
git status --short | wc -l                    # 期望 0；若不为 0 才需要 git read-tree HEAD
git branch -vv                               # 两个分支都在，当前分支带 *
```

**不要**做这些（用户 2026-09-15 明令，任何理由都不行）：
- 删本地分支（`branch -d/-D`、`update-ref -d`、`push --delete`）、`branch -m` 改名；
- 推 `main` / `master`，或 `--all` / `--mirror` / `--tags`；
- 把 HEAD 指向**含斜杠**的分支名（必然再次 unborn）。

推送一律「显式 sha + 精确 refspec」，且只推工作分支：

```bash
git push comind <sha>:refs/heads/feat/undo-redo     # 远端侧不受本地斜杠限制
```

## 收工前自检（防止把断裂环境留给用户）

动过 refs / HEAD / index 后，**必核三条**：`rev-parse HEAD` 可解析、`status --short` 为空、`branch -vv` 无异常。
发现断裂就修好再走 —— 「下次再说」等于把炸弹交给下一个会话。

---

## 变体：refs 健康但 **HEAD + index 双双陈旧**（status 数字离谱）

**触发**：用户说「commit」，你报「工作区 200+ 个改动」，用户回「**没有改动这么多文件**」。
（2026-09-18 实证：我报 219 改 / 37 新增，真实只有 23 改 / 12 新增。）

**定性（只读，30 秒）**
```bash
git log -1 --format='%ci %s' HEAD     # HEAD 的提交日期
git reflog --date=iso | head          # 条目极少 / 日期晚近 = refs 被重建过
git diff --cached --shortstat         # 空 ⇒ index == HEAD（两票同步地陈旧）
ls .git/refs/heads/                   # 空 + 分支只在 packed-refs = 曾被重建
gh api "repos/<o>/<r>/commits?per_page=8" \
  --jq '.[]|"\(.sha[0:7]) \(.commit.committer.date) \(.commit.message|split("\n")[0])"'
```
远端 tip 明显新于 HEAD ⇒ **工作区是新内容，元数据停在旧提交**：那几百个「改动」里绝大多数
是「上游早已提交、本地索引不认识」的假象。（连 `??` 也是假的：上游新文件在旧索引下就是 untracked。）

**量化真实差异（零写入，最硬的一步）**：不要信 `git status`，逐文件哈希比对
```bash
python delta_scan.py <上游tip-sha>       # 见本技能目录 delta_scan.py
# SAME_AS_UPSTREAM / NEW / DIFFERS / LOCAL_DELETED
```
坑：`git ls-tree` 默认对非 ASCII 路径做 C 风格转义（`"docs/\346\212\200..."`），与磁盘真实文件名
失配 → **假报一堆 LOCAL_DELETED**。必须 `git -c core.quotepath=false ls-tree -r <tip>`。
（脚本内已处理；另注意 `hash-object` 传路径形式才会按 `.gitattributes` 施加 eol 过滤，与仓库存储形态一致。）

⛔ **致命：陈旧索引下直接 `git commit`**
`git commit` 写出的树取自 **index**。index 停在旧提交时，提交出的树会把上游这 N 天的改动
**整体回退**（本例 889 个文件回到 5 天前）—— 推上去就是大面积回退。
`git add <自己的文件>` 也救不了：树的其余部分仍是旧的。
**所以「先把索引对齐」是提交的前置条件，不是洁癖。**

**对齐配方（只写 index，一个字节都不碰工作区）**
```bash
git read-tree <上游 tip>              # 绝不能加 -u：-u 会更新工作区，可能删文件
git diff --shortstat                  # 未暂存 == 你自己的真实改动
git ls-files -o --exclude-standard    # 真实新增
```
对齐后 `status` 把「追平上游」显示为**已暂存**（`M `/`A `），自己的改动显示为**未暂存**（` M`/`??`）
—— 这是预期形态，不是故障。

**第二步（可选）：让 HEAD 也指到上游 tip，status 就只剩自己那几十个改动**
```bash
git update-ref refs/heads/<无斜杠新名> <上游 tip>     # 连字符名，落盘后立刻 ls .git/refs/heads/ 验证
git symbolic-ref HEAD refs/heads/<无斜杠新名>         # 逐条执行，不拼 &&；改完 cat .git/HEAD 验证
git read-tree <上游 tip>                              # 关键：HEAD 换了但 index 还是旧树时，status 会假装"要回退上游"
```
**一律新建分支、绝不把 HEAD 指到用户既有分支上**（旧锚点保持不动，用户明令不删分支、不改名）。
这两条写入会动 HEAD ⇒ **先问用户再动**（2026-09-18：用户先选「只对齐索引」，随后明确下令「完成那2条ref写入」才做）。

验收数字用例（2026-09-18 实跑）：`status` = **23 M + 12 ??**（恰好 35 个真实文件，**无 D 条目**）、
未暂存 `23 files changed, 219 insertions(+), 31 deletions(-)`、`git ls-files | wc -l` = **913**（= 890 同上游 + 23）、
12 个新文件逐个 `wc -c` 在盘。数字自洽（原 37 未跟踪 = 25 个上游新文件 + 我的 12）才算成功。

**顺带**：`git log --all` / `for-each-ref` 可能因**坏 ref**（指向缺失对象，如
`refs/remotes/comind/feat-69-…` 报 `bad object`）直接 fatal。别据此判「仓库坏了」——
改用 `gh api` 拿远端事实，并用 `git cat-file -e <sha>` 确认对象是否已在本地（本例 tip 与本地
HEAD 都在，故整条链路零写入就能判完）。**该症状的完整修复见下一节。**

---

## 变体：ref 指向**本地缺失对象** → `git fetch` 自举死锁

**症状**（2026-09-18 实证，用户报的就是这条）
```
fatal: missing object b2d211fb… for refs/remotes/comind/feat-69-wasm-snapshot-trigger
git fetch comind  -> fatal: bad object b2d211fb…
                     error: https://… did not send all necessary objects
                     error: failed to perform geometric repack
git log --all / for-each-ref -> fatal（要解析坏 ref）
git count-objects -v -> warning: no corresponding .pack: …afb77a85….idx
```

**定性（只读，两分钟）**
```bash
# 1) 哪些 ref 指向缺失对象（本例 9 个分支，comind/origin 各一份镜像 = 同一个 GitHub 仓库）
git for-each-ref --format='%(refname) %(objectname)' refs/heads refs/remotes refs/tags \
  | while read ref sha; do git cat-file -e "$sha^{commit}" 2>/dev/null || echo "MISSING $ref $sha"; done
# 2) 远端还有没有这些分支 —— 有 ⇒ 可治，绝不删 ref
git ls-remote comind | grep -E "<分支名>"
```
本例远端**全都在、sha 与本地 ref 一字不差** ⇒ 对象从来没到过本地
（ref 是在某次 refs 重建时凭 `ls-remote` 手工写进 packed-refs 的，见 `.git/packed-refs` 命中行）。
先排除「对象曾被某个 pack 带走」：`git show-index < 不带 .pack 的孤儿 idx > | grep <sha>` —— 本例**不在**其中。

**为什么 fetch 治不了（关键机制）**：`git fetch` 会**枚举本地全部 ref 当作 have 上报**，
解析到缺失对象就 `fatal: bad object`。`-c fetch.negotiationAlgorithm=noop` 也绕不过
（die 发生在 `mark_complete_and_common_ref`，与协商算法无关）。
⇒ **fetch 永远补不上对象 = 自举死锁**，这个仓库此前所有 fetch 都是坏的。

**解法：绕开 ref，直接往对象库塞 pack**（零 ref 写入、零删除、零 push）
```bash
bash heal-missing-refs.sh "D:/comind" comind "https://x-access-token:$(gh auth token)@github.com/jayyucn/comind.git"
```
脚本见本技能目录 `heal-missing-refs.sh`，四步：① 扫坏 ref；② 在仓库**外**（`outputs/heal-scratch`，
须在 .gitignore 内）建干净裸库、用显式 refspec 只拉这些分支；③ 把 `pack-*.{pack,idx,rev}`
拷进主库 `.git/objects/pack/`；④ 复核。对象一到位坏 ref 自愈，`git log --all` 与维护任务随即恢复
—— 本例重排后 `geometric-repack` 由**失败变成功**，对象库自动收敛成 2 pack + MIDX。

**验收数字（本例）**：`refs=85 missing=0`、`resolved=9/9`、`git log --all` = **1021** 提交、
`git fsck --connectivity-only` exit 0（只剩 dangling blob = 正常垃圾）、`count-objects -v` = 2 packs / 12382 in-pack、
`fetch comind --dry-run` exit 0、**`status` 与 HEAD 一字未变**。
**独立性自证**：把临时库的 pack 改名后主库仍解析 9/9 ⇒ 确认是副本而非硬链接。

**坑**
- `git fetch <url>` 用 URL 参数不会把 token 写进 config；但**临时库没有主库的 credential helper**，
  必须显式内嵌 token（`$(gh auth token)`），否则临时库认证失败。
- 拉 9 个分支在前台会撞 120s 超时，用 `run_in_background`（本例 33s 完成）。
- 孤儿 idx（只剩 `.idx`、`.pack` 缺失）**别急着删**：`.git` 内文件删除须用户点头。它本身惰性，
  但若它是**新近产生**的（见下一节），说明本机 pack 写入在丢文件，属于重大信号，不要当噪音忽略。

---

## 变体：`git stash` 摧毁 refs（husky / lint-staged 的隐形调用）

**症状**：执行 `git commit` 后，钩子报
```
✖ Failed to back up original state!
  > git stash list --format="%h %s"
husky - pre-commit script failed (code 1)
```
随后仓库看起来**坏了**：`rev-parse HEAD` 报 unknown revision、`cat .git/HEAD` 内容是字面量 `HEAD`、
`git status --short` 全库几百条 `A`、`git branch -vv` 空。

**根因**：`lint-staged` 默认 `--stash=true`，跑任务前会用 `git stash` 备份未暂存改动。
本机 `git stash` 是头号禁区（唯一「写 objects + 动 refs + 改 index + 覆盖工作区」的四重复合操作），
**它把 `.git/refs/` 下全部松散 ref 连同 `.git/HEAD` 一起抹掉**。（2026-09-18 实证。）

**先评估损失，再动手**（只读）
```bash
git cat-file -t <原来的 HEAD sha>      # 对象库是否完好（本例两个关键 commit 都活着）
ls -la .git/packed-refs                 # ★ 幸存与否决定恢复难度
cat .git/logs/HEAD | tail               # reflog 是唯一还记得「HEAD 原来指哪」的地方
git ls-files | wc -l                    # 索引是否完好（925 = 上游 913 + 我的 12）
git diff                                # 空 ⇒ 工作区与索引一致，一个字节没丢
```
本例：对象库完好、**packed-refs 幸存**（77 条）、reflog 幸存 ⇒ 只有松散 ref 与 HEAD 需要重建。

**恢复**（不删分支、不碰 main、不 push）
```bash
mkdir -p .git/refs/heads .git/refs/tags .git/refs/remotes
git update-ref refs/heads/<无斜杠名> <sha> ; ls -la .git/refs/heads/   # 必须看到文件落盘
git symbolic-ref HEAD refs/heads/<无斜杠名> ; cat .git/HEAD            # 必须是 "ref: refs/heads/..."
```
`packed-refs` 里的 ref（`refs/remotes/*`、其它本地分支）**无需重建** —— refs 目录为空也能正常解析。
**代价**：不在 packed-refs 里的松散 ref 会永久丢失。本例 ref 数 85 → 78，缺的 7 个是松散
remote-tracking ref（**remote-tracking 默认不写 reflog ⇒ 无法指认名字**）。**本地分支必须逐个点名核对**。

**根治**：`.husky/pre-commit` 改成 `npx lint-staged --no-stash`（lint-staged ≥10 支持；
本例 v17.5.1）。**钩子是从工作区文件读取的，所以「先改钩子、再提交」在同一条流程里即时生效** ——
先把钩子作为独立提交落地，后续提交就安全了。本仓索引与工作区通常同步（无部分暂存场景），
stash 备份本无必要。

---

## 变体：索引引用了**已被回收的对象** → 提交会写出坏树

**症状**：提交时钩子/命令吐 `error: invalid object 100644 <sha> for '<path>'`；
`git cat-file -t <索引里的 sha>` 报 `could not get object info`。

**为什么极难发现**：`git diff --cached --shortstat` **仍然能算出行数**（本例显示 `+2313/-31`），
看着完全正常；`--name-status` 也只靠 sha 比对就能输出。**只有读 blob 内容的操作才会暴露。**

**提交前必查（一条命令，925 个文件也秒过）**
```bash
git ls-files -s | awk '{print $2}' | git cat-file --batch-check
# 每一行应为 "<sha> blob <size>"；出现 "missing" 即索引引用了缺失对象
```

**⛔ `git add` 修不了它**：文件没变时 `git add` 因 stat 缓存判定「无变化」，**根本不重写对象**
（RC=0，对象依旧缺失）。必须强制写回：
```bash
git hash-object -w -- <path>        # 逐个文件；返回的 sha 应与索引里的 sha 完全一致
```
（sha 不一致 ⇒ 索引里存的不是你当前工作区的内容，别提交，先核对。）

**为什么对象会消失**：自动维护（git 2.55 起默认几何重排，无需任何配置）会回收不可达对象。
本例 **35 个暂存 blob 被整批回收**（它们只在索引里，不属于任何 ref/tree）。

**同一维护动作还会丢 `.pack` 文件**：本例连续两次产出的新 pack 都只剩 `.idx`、`.pack` 不见，
MIDX 仍指向它们 ⇒ `git fsck` 报 `failed to load pack in position 0` + `failed to load pack entry for oid[...]`，
`git count-objects -v` 报 `warning: no corresponding .pack: <...>.idx`。
对象本体还在（loose + 老 pack）所以仍可读，但这是**本机 pack 写入不可靠**的铁证。

⛔⛔ **由此推出一条硬规矩：本机绝不要跑 `git gc` / `git repack`**。
它们会把 loose 对象收进新 pack 并**删掉 loose 副本**，而 pack 写入可能丢 ⇒ **对象真的永久消失**。
**loose 对象是本机唯一可靠的载体，必须保着它们。**

**提交后的自证**（确认这份提交自包含、可推送）
```bash
git ls-tree -r <新提交> | awk '{print $3}' | git cat-file --batch-check | grep -vc ' blob '
# 应为 0；925 个条目全可读才算数
git rev-parse <新提交>:<某个改过的文件>   # 与 git hash-object <该文件> 应完全相等
```
**建议**：若维护动作持续制造孤儿 pack，向用户提议 `git config maintenance.auto false`（+ `gc.auto 0`）
—— 关掉自动重排对本机是保护（loose 对象不被收拢），属配置写入，先问用户。
