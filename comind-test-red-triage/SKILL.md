---
name: comind-test-red-triage
description: 当面对 comind 的「既存红」议题（某测试文件 N 例失败、issue 说基线就红、怀疑是 locale/环境/顺序依赖）时，把每一例定性为【产品缺陷】【测试夹具缺口】【环境能力缺口】三类之一，各自用只读证据钉死，再决定修产品/修测试/不修。#79 先例。含决定性启发式（看兄弟测试文件对同一受限原语怎么处理）、空桩 vs 忠实桩的判别、真机库只读核查配方（表名大写、mode=ro）、以及 WASM 桩清单。
agent_created: true
---

# comind 测试红三分类（triage 定性）

先例：#79（`Block/index.test.ts` 3 例 + `useRelationshipMenu.test.ts` 2 例，2026-09-14）。
适用：任何「某测试文件若干例失败，issue 里已经猜了几种原因」的议题。

## 何时用

- issue 正文里出现「是否 locale 差异 / 是否用例顺序依赖 / 需要 root-cause 后决定修测试还是修产品」这类**未取证**的猜测。
- 全量 `vitest run` 的既存红（约 22 文件 / 61 例）里有人想认领一批。
- 有人想「先跑一遍看哪些红」就动手改 —— 停，先分类。

## 铁律：一条红例只属于一类，三类混在一个 issue 里必须点出来

| 类别 | 判据 | 处置 |
|---|---|---|
| **产品缺陷** | 被断言的行为与**本仓已声明的口径**冲突（代码注释头 / 类型签名 / 测试里其它 20+ 处的写法） | 修产品，测试不动 |
| **夹具缺口** | 失败堆栈里那个原语在**兄弟测试文件**里已被 mock/spy 掉 | 补夹具，测试断言不动 —— 但先分辨**空桩还是忠实桩**（见下） |
| **环境能力缺口** | 该原语在当前 target（jsdom/WASM）下是**硬编码 throw**，且产品代码注释已标注「web 不可用」 | 先定性，再单独立项；**不要**塞进红例议题 |

## 决定性启发式（最省时的一步）

失败堆栈里找那个「不可用原语」，然后：

```
grep -rn "<原语名>" src/ --include=*.test.ts
```

- 若**别的测试文件都在 spy/mock 它**（例：`BlockList.keyboard-delete.test.ts:88`、
  `BlockList.selection-orchestration.test.ts:238` 都写
  `vi.spyOn(getCoreClient()!, 'extractLinksFromContent').mockResolvedValue([])`），
  那这个文件的红 = **夹具缺口**，不是产品 bug。`Block/index.test.ts` 只是没跟上。
- 若没人 mock 它、且它直连真实实现 → 才可能是产品 bug。

**反例警戒**：不要按「堆栈里有产品文件路径」就判产品 bug —— 堆栈必然既含产品也含测试。

## 空桩 vs 忠实桩（#79 实证，最容易踩的一步）

「照抄兄弟写法」抄到的往往是 **`mockResolvedValue([])` 空桩**。空桩只在该用例**不关心**该原语的输出时成立：

- ✅ 用例断言的是「删除发生了 / 激活了前一块」→ `[]` 足够（`Block/index.test.ts` 删除清理第 3 例）。
- ❌ 用例断言的是**该原语输出的下游后果**（如「跨页反向降级」）→ 空桩会让整条链路空转：
  `targetSet` 为空 → 降级永不发生 → **红从 throw 变成真断言失败**（`expected 'reverse ((required-by))[[P]]'`）。
  此时**不是**产品 bug，是桩给错了。

两条硬规则：

1. **断言依赖该原语的输出 ⇒ 必须给忠实桩**（按 Rust `ContentParseService` 口径实现），
   抄 `useBlockRelationshipCleanup.test.ts:14-49` 的 `extractLinks` 解析器形态。
2. **一条产品路径可能依赖多个桩**。#79 的降级路径同时依赖 `extractLinksFromContent`
   （`client.ts:839`）与 `applyRelationshipTypeToBlockContent`（`:843`，经 `useRelationshipSync.ts:33-38`
   薄包装打到**同一适配器**，所以 spy 适配器方法即可拦截两个）。先读产品函数体，把该路径碰到的
   原语列全再下手。

**判别口诀**：补完夹具仍红 ⇒ 先怀疑桩给错了（空桩抹掉了断言依赖的输入），**不要**急着升格成产品 bug。

## 假红三型（先排除，再谈定性）

「我刚跑出一例从没见过的红」≠ 我改坏了。三型假红，各有确定性判据：

| 型 | 现象 | 判据 / 修法 |
|---|---|---|
| **hookTimeout** | `Error: Hook timed out in 10000ms` 落在 `beforeEach` 行（不是断言行），**单跑该文件却全绿** | 该文件逐例 `vi.resetModules()` + `await import(...)` 重建了重页面模块图（TableView/查询引擎/CodeMirror）。全量并发下第一例的 import 可越 10s。修法：**文件级静态 import + 顶层 `vi.mock`**（先例 `TaskHub.test.ts`），去掉逐例 `resetModules`+`doMock` |
| **未处理 rejection 计数** | `Errors N errors`，用例全绿但 N 比基线多 | 页面级 mount 打开抽屉/浮层会连带挂载 `Page` → 拉块/属性/触发自动保存 → mock client 缺方法。桩齐 `getBlocksByPage` / `getProperties` / `saveBlockTree` 即归零（返回 `[]` / `[{}]` 够用） |
| **跨文件竞态** | 只在全量里红、单跑绿，且**单跑复现不出** | 隔离副本内确定性复现才算真（见「陷阱」）。禁拿一次全量结果下结论 |
| **负载型 test timeout** | `Error: Test timed out in 5000ms`（注意不是 Hook），**单跑该文件全绿** | 重负载用例（如 `useUndoHistory` 的「>1000 块 / 32MB 预算」= 建上千棵块树）在全量并发下越 5s。修法：给该例 `it(..., { timeout: 20000 })`，**不要**据此认为产品有缺陷（2026-09-22 实证） |
| **动画清理时序漂移** | 断言失败（**不是**超时），断言内容是「动画/闪烁元素应被清空」类（`expect(flashLefts()).toEqual([])`）却残留 1 个；**同一用例的前置断言已过**（功能正常），只有「清理已发生」这一条漂；**单跑该文件全绿** | 测试拿**墙钟**等一个动画窗口且余量极小：`BlockList.undo-redo.test.ts:1155` 的 `flashSettled()` = `setTimeout(FLASH_MS + 50)` 即 650ms，去等 BlockList 的 600ms 清理定时器。全量并发下 jsdom 定时器回调被挤到窗口外。属**夹具缺口**。修法：改成**轮询** `await vi.waitFor(() => expect(flashLefts()).toEqual([]))`，或 `vi.useFakeTimers()` + `advanceTimersByTime`；单纯加大余量只治标（2026-09-22 实证：两次全量均复现、单跑 39/39 绿） |

**只读 A/B 反证「这红是不是我引入的」**（**禁 stash**，2026-09-22 实证）：把自己的改动文件
`cp` 到**仓库外**备份 → 用 `git show HEAD:<file> > <file>` 换回上游版本 → 单跑该测试文件 →
无论结果如何都 `cp` 备份覆盖复原 → 删备份。红照旧 = 既存红。配套第二证据：`git diff` 自己的
改动行落在哪个函数，与失败用例的 `describe > it` 名比对，无交集即基线。

## 取证顺序（全部只读，禁 stash）

1. **逐条跑红例**，读断言原文（`node node_modules/vitest/vitest.mjs run <file>`；注意本仓 vitest 版本已移除 `--reporter=basic`）。
   先数清「这个文件几例红」「另有哪些文件被同一缺陷波及」—— #79 就是靠这一步发现 `useRelationshipMenu.test.ts`
   另有两例同源红，issue 里完全没提。

   ⛔ **别用 `npm run test | grep FAIL` 去取清单**（2026-10-11 实证）：FAIL 行带 ANSI 前缀、再加 `tail` 截断，
   `grep -E "^ FAIL"` 返回 **0 行**——白等一轮 2.7 分钟还拿不到文件名。要机器可读的完整清单就走 JSON 报告：

   ```bash
   cd "D:/comind" && npx vitest run --reporter=json --outputFile=.workbuddy/vitest-report.json
   node -e "
   const r=require('./.workbuddy/vitest-report.json');
   for (const t of r.testResults) {
     const f=(t.assertionResults||[]).filter(a=>a.status==='failed');
     if (f.length) console.log('## '+t.name.replace(/^.*[\\\\/]src[\\\\/]/,'src/'), '=>', f.map(a=>a.fullName).join(' | '));
   }"
   ```
   （JSON 报告落在 `.workbuddy/`（不提交）——**用完删掉**。全量单次约 2.8–3 分钟。）
2. **失败堆栈 → 文件:行**，回到源码读上下文（不要只读报错那行）。
3. **兄弟测试文件比对**（上面的启发式）。
4. **口径核对**：把「产品该输出什么」在**类型签名 / 接口注释 / 其它测试**三处交叉验证。
   多数「产品 bug」之所以是 bug，正是因为**只有这一个实现点是异类**，其余 20+ 处都写着另一种口径。
5. **真机库只读核查**（只在需要判断「纸面约定 vs 既成事实」「有无历史脏数据」时做）：
   ```python
   # 路径：%APPDATA%/com.comind.app/workspace-dev/sqlite/comind.db
   # 坑1：表名首字母大写 —— Block / Page / Link / RelationshipType，不是 blocks
   # 坑2：必须 mode=ro，否则会碰 WAL
   con = sqlite3.connect('file:C:/Users/jay/AppData/Roaming/com.comind.app/workspace-dev/sqlite/comind.db?mode=ro', uri=True)
   ```
   #79 靠这一步钉死：「存储态单一 type」是既成事实（29 块含 `((`，label 态 **0**），因此无需迁移。

## 已知事实速查

- **WASM 适配器桩共 18 处**（`src/wasm/client.ts`）：`saved filters` / `screens` / `tabs`（502–568）11 处；
  **内容解析族 7 处（827–851）**：`parse_date_input`、`normalize_journal_title`、`is_today_title`、
  `extract_links_from_content`、`apply_relationship_type_to_block_content`、`calculate_next_recurrence`、
  `check_has_typed_link_to_target`。→ 这 7 个缺失使 **web 下关系清理（跨页反向降级）与关系同步整体不可用**
  （`cleanupAfterDelete` / `useRelationshipSync.ts:63,122`）。属 ADR-0021 收敛债（ADR-0021 的方向是
  「wasm 与 Tauri 只差传输层」）。测试里对这 7 个一律 spy。
- **关系存储态铁律**：`((type))` 的 **type 是唯一权威标识**，中文 label 只是展示层映射
  （`utils/relationship-content.ts:1-25` 是这条不变量的唯一载体；Rust `content_parse_service.rs:101-108`
  纯语法解析，不做归一）。`useRelationshipMenu.select()` 的 `onSelect` 契约是 **type**
  （声明即 `(type: string) => void`）；需要显示 label 由调用点自己 `getRelationshipLabel()`。
  decode（进编辑态）在 `Block/index.vue:104`，encode（保存）在 `useBlockEditorLifecycle.ts:98`。
  **任何把 label 写进存储态的路径都是缺陷**。
- 验收门槛（红例议题）：红例文件全绿 + `npx vue-tsc -b` + eslint 按
  `git show HEAD:<file> | npx eslint --stdin --stdin-filename <file> -f json` 对比现盘的 **errorCount/warningCount 增量**（禁 stash）。
- 既存全量红基线约 **22 文件 / 61 例**，红数会漂移 —— 不要按总数判责。
  （2026-09-22 晚快照：vitest `3 failed / 187 passed` 文件、`4 failed / 2667 passed` 例 —— 固定红 3 例 =
  `BlockList.selection-orchestration.test.ts` 1 + `BasePopover.test.ts` 2 + `BlockList.undo-redo.test.ts` 1，
  末一例即上面的「动画清理时序漂移」，全量并发下稳定复现、单跑 39/39 绿。同日更早一次快照为
  `2 failed / 188 passed`、`3 failed / 2663 passed`；
  `Errors` 计数来自 `SlashCommandMenu` 12 + `BlockList.keyboard-delete` 4，均与标签工作无关。
  Rust `cargo test -p comind-core --lib` = **215 passed / 4 failed**，4 红固定为
  `test_build_tree` / `test_chinese_content_char_offsets` / `test_link_to_nonexistent_page_skipped` /
  `sync::engine::tests::test_full_sync_export_empty`。）
- **2026-10-11 快照：全量 12 文件 / 28 例**（同一提交连跑两次得 12 / 11 文件 ⇒ **跑批之间有 ±1 例抖动**，
  仍**不要按总数判责**）。当日红族：`useDateTimePickerPanel.pad` 10 + `.todo` 3、
  Tag 身份 UI 族（`TagAggregatePage` / `TagColorPicker` / `TagDescriptionField` / `TagsLibrary` 4 / `tag-color`）、
  `BasePopover` 2、`StatusIcons` 2、`BlockList.selection-orchestration` 1、
  `useUndoHistory`「>1000 块 / 32MB 预算」1、`TaskHub.slash-midium` 1（并行会话 staged 的用例）。
  同日 `BlockList.task-progress` 13/13、`BlockList.undo-redo` 39/39 **已转绿**（红族会自愈，别照抄旧列表）。
- **改了 Rust 却没重建 wasm** ⇒ JS 侧全量爆一批 `entries.value.map is not a function`（新 op 未编进
  wasm 产物，batch 返回错误 → 读接口拿到 undefined），或 Rust 侧修复**静默不生效**（例：2026-09-22 的
  `effective_field_ids` 同名遮蔽，未重编时同一标签出现两条同名字段）。这是假红，先 `npm run wasm:build` 再复跑。
  ⚠️ **落点是 `crates/pkg/`，不是仓库根 `pkg/`**：脚本 `--out-dir ../pkg` 相对 crate 解析；vite 与 vitest
  的 alias 都是 `@wasm → /crates/pkg`（`src/wasm/wasm-client.ts` 动态 `import('@wasm/comind_wasm')`）。
  根 `pkg/` 是 2026-07-23 的死副本 —— 判断产物新旧请查 `crates/pkg/comind_wasm_bg.wasm` 的 mtime。

## 陷阱

- 并行会话的 vitest 竞态会被误当成根因。**隔离副本内可确定性复现**才算真。
- 报错文本会和根因完全无关（#79 的标题写「关系标签/删除清理」，实际是「select 出参口径」+「夹具缺口」两个不相干缺陷）。
- 只跑「看起来相关」的文件会漏掉同源红（务必先 grep 该缺陷涉及的原语/符号，全仓找同源）。
- 改 `.ts` 前先确认文件的换行符（仓库多为 CRLF，部分为 LF）；**多行替换一律走二进制读写**并断言命中恰好 1 次，事后核 `git diff --numstat`。

## 收口

分类完成后逐类处置，并把**改动面写进结论**。#79 的最终改动面＝`useRelationshipMenu` `+7/-7` +
`Block/index.test.ts` `+55/-1`（**测试断言零改动**；比预估的两行大，因为第 2 例需要忠实桩）。
若结论是「产品 bug」，务必确认「改完有几例红转绿、有没有别处需要跟着改」——
只改一处实现而断言天然转绿（此例：`resolveType` 改名正本清源，3 例红同时转绿），才是最干净的收口。
