---
name: comind-cross-layer-seam
description: 在 comind 仓库给数据层原语接入上层 composable 的「收口」（如删除入口接入 cleanupAfterDelete 关系清理），并用 jsdom 单测证明接线真的生效。当要给现有 store 原语补一条新调用路径、或让新入口与既有入口同源（同一收口）时使用。
agent_created: true
---

# comind 跨层接缝：参数注入接 composable 收口，并证明它

## 何时用

- 新增了一个「删除 / 写入入口」，但它绕过了既有收口（先例：#95 文本选区删除绕过 `cleanupAfterDelete`）。
- 需要让数据层（`src/stores/*`）触发上层编排（`src/composables/*`）的逻辑。

## 硬约束（决定做法）

`src/stores/*` **不能 import** `src/composables/*`（分层方向）。所以「store 触发 composable 逻辑」只有一条路：**参数注入**。

## 配方（最小改动的形状）

**1. 数据层加一个必填参数 = 副作用出口**

```ts
async function deleteTextRange(
  pageId: string,
  range: TextRange,
  deleteMiddleBlocks: (ids: string[]) => Promise<unknown>   // 必填，不给默认值
)
```

- **不要给默认值**。默认值 = 「新调用点忘记传 → 静默退回裸删、绕过收口」的 bug 形态潜伏在默认路径上 —— 而那正是本类缺口（#100）的病因。必填迫使每个调用点显式决定。
- 代价：既有测试要适配。用 helper 模式化单行替换即可（`store.deleteTextRange(pageId, {` → `deleteRange(store, pageId, {`，helper 内部补 `store.deleteBlocks`），不动任何断言。
- 参数名用 `deleteXxxBlocks`（动词短语），不要用 `deleteXxx` —— 后者读作「删除中间」这一动作，实为「中间块的删除出口回调」。
- 返回类型用 `Promise<unknown>` 而非 `Promise<void>` —— 否则 composable 返回的 `Promise<CleanupResult>` 不能直接传入，编排层被迫包一层 async 箭头。
- 别拆 plan/apply 来重塑接缝（那会动数据层既有语义与全部测试）。

**2. 编排层注入收口**（`src/composables/*`）

```ts
const blocksBeforeDelete = [...blockStore.blocks]   // 收口若需要前态，必须先取
await blockStore.deleteTextRange(pageId, range, ids =>
  relationshipCleanup.cleanupAfterDelete(pageId, ids, blocksBeforeDelete)
)
```

**3. 先确认收口的语义边界，再决定纳入哪些 id**

`cleanupAfterDelete` 的存活检查是「**前态快照 − 被删 id**」，隐含「被删块内容全部消失」。若新入口产生「块内部分内容存亡」（如端点裁剪 + 合并），**只有整块消失的那一集合**能安全纳入 —— 计入「部分存亡」的块会**假降级**（误摘仍存活的关系；反向则是漏降级）。这类缺口如实留 issue，别硬接。

**措辞要精确（我在此栽过）**：裁剪 + 合并路径下，**尾端点其实是被整块删除的**（内容并入生存块），头端点则存活但内容被裁。所以排除端点的理由**不是**「端点块没消失」，而是「**端点块的内容只有一部分存活**，不满足『该 id 的整块内容全部消失』这一前提」。注释与 issue 按这个说法写，否则评审一眼就能看出与代码矛盾。

## 如何证明接线生效（不要 mock collaborator）

找**只在新路径上被调用的协作原语**，spy 它并断言调用参数：

```ts
// cleanupAfterDelete 第 1 步会遍历被删块内容 → getCoreClient().extractLinksFromContent
expect(extractLinksSpy).toHaveBeenCalledWith(mid.content)     // 收口确实被走到
expect(extractLinksSpy).not.toHaveBeenCalledWith(a.content)   // 端点未被纳入（= 语义边界）
```

- 未接线时该原语**完全不会被调用** → 这就是区分接线与否的静默差异。
- 不要整块 `vi.mock('../composables/useBlockRelationshipCleanup')`（内联 collaborator，且把被验证的逻辑替换掉了）。该 composable 每次调用返回**新**对象，所以从外部也 spy 不到它的实例方法 —— 只能走「协作原语」这条路。
- jsdom 下 `WasmClientAdapter.extractLinksFromContent` 是硬编码 throw（既存环境局限）→ 必须 `vi.spyOn(getCoreClient()!, 'extractLinksFromContent').mockResolvedValue([])`，否则该路径整体 reject。

**断言区分力自查（必做）**：写下「某断言证明 X」之前，先问「在**错误实现**下这条断言会红吗」。不会红就是空过 —— 典型的假信号。

实例（同一提交里两条形式对称的否定断言，只有一条是真信号）：

```ts
expect(extractLinksSpy).not.toHaveBeenCalledWith('tail')   // ✅ 有区分力：尾端点若被误纳入被删集，其原内容会被提取
expect(extractLinksSpy).not.toHaveBeenCalledWith('head')   // ❌ 空过：surviving 扫描只在页面标题注册时才跑，本用例没注册 → 永真
```

判断依据来自收口的**分支条件**：`cleanupAfterDelete` 第 1 步（对 `deletedBlockIds` 逐个提取）无条件跑；第 3 步（扫描本页 surviving）只在 `ourPageTitle` 存在时跑。断言必须挂在**无条件**的那条路径上才可靠。

## 变体：给 store 原语加可选参数并接线（写侧基准 ≠ 渲染侧回退）

有些 store 写原语的 transform 基准来自 **store 侧**的兜底，而列表/表格实际渲染用的是**消费方的另一份**兜底。两者不一致时，写出去的是「更空」的那份；渲染层拿到它后**不再回退**，症状是「某列/字段配置被清空」。

实例（2026-09-23，tag 聚合页拖一次列宽 → 表格零列、看着像数据被清空）：

- 写侧 `resolveTableConfig(tab)` = `parse(tab.config) ?? defaultConfig ?? { columns: [] }`；`defaultConfig` 只有 `block`/`page` 命名空间注入，`tag:<id>` **没有** → 基准是空列集。
- 渲染侧 `TagAggregateBody.tableConfig` = `parse(tab.config) ?? tagTableDefault`（列模板由 tag 字段异步派生，store 无从得知）。
- `tab.config` 按设计落空串 ⇒ `columns.map(...)` 在空数组上跑一遍 → 把 `{"columns":[]}` **落库**；此后 `parse` 返回非 null → 渲染层永远不再回退 ⇒ 零列，且**刷新不恢复**。
- 让症状更隐蔽的一行：`props.config?.columns ?? [{ key: 'content' }]` —— **`[] ?? x` 是 `[]`**（空数组不是 nullish）。

改法（最小）：给 `patchActiveTabConfig` / `patchAllTabConfigs` 加**可选 `base`**，回退链变为 `parse → defaultConfig → base → 空列集`（`base` 放 `defaultConfig` **之后**，既有命名空间行为逐字不变），消费方**每一处**列操作传 `props.tableConfig`。别改成「让 store 注入消费方默认值」—— tag 页**刻意**不注入 defaultConfig（见 `TagAggregateBody` 顶部注释），那是设计而非遗漏。

**审计问法**：凡「store 兜底 → 写库 → 消费方 parse 回头」的原语，都要问「store 的兜底与消费方渲染用的兜底是不是同一份？不同的话，谁更空？」**读侧要一起查**：同源 computed（如 `activeTabColumns`）也走同一份兜底，往往被面板/工具栏消费 —— 实例里字段面板的「已用字段」就显示为空，而表格渲染着整份模板（修法：消费方 compute 一层 `props.tableConfig?.columns ?? store.activeTabColumns`，表格在场时以渲染的那份为准，非表格视图保留旧行为）。

**第二实例（2026-10-11，块正文复活）**：store 原语（`ensureTaskTagMounted`）以 `block.content` 为拼接基准，但**活动块**的最新正文在编辑器里——`Editor.vue` 的 `onUpdate → debouncedEmitSave` 有 300ms 防抖，store content 滞后。斜杠命令先 `deleteRange` 清命令文本，原语随即拿旧正文拼接 → 刚删的文本复活 + `setContent` 顶回编辑器。修法：目标块为活动块时以 `editorStore.activeEditor.getText()`（与落库 save 同源的序列化）为基准，非活动块维持 store 兜底。**判据扩展**：凡是「读 store 正文做再写入」的原语，都要问「目标块是否正被活动编辑器编辑？防抖窗口内的编辑器正文才是真相」。

### 证明这类型接线生效：mount 外壳 + 函数式 slot 抓 `context`

外壳把动作经 `viewContext` 打包给具名 slot ⇒ 用函数式 slot 直接抓内部动作，断言**传出去的参数**：

```ts
const captured: { ctx?: ViewCtx } = {}
mount(QueryPageFrame, {
  props: { screenViewKey: KEY /* 独立命名空间 */, tableConfig: TAG_BASE, /* … */ },
  slots: { table: (params) => { captured.ctx = (params as { context: ViewCtx }).context; return h('div') } },
})
captured.ctx.onColumnResize([{ key: 'content', width: 318 }])
// 断言落库 payload 保留 base 的列（而非 columns: []）
```

- 命名空间用**独立 key**（如 `tag:query-page-frame-test`）：`useScreenViewStore` 把 `defineStore` 结果缓存在**模块级 registry**，首次调用的 options（`defaultConfig` 等）会被同名调用继承 ⇒ 要「无 defaultConfig」就必须让本文件第一次调用就不传。
- store 实例可直接注入：同一 pinia 下 `useScreenViewStore(KEY)` 返回同一实例，`store.views = [...]` + `store.currentTabId` 即可伪造激活 tab。

### ⚠️ 坑：宽松 mock client 的 Proxy 会把 `await` 挂死

给 `wasm/client` 写「未知方法一律 async noop」的 Proxy 时，**必须让 `then` 返回 `undefined`**：

```ts
const base: Record<string, unknown> = { updateTab: mockUpdateTab }
return new Proxy(base, { get: (t, k) => (k === 'then' ? undefined : k in t ? t[k] : vi.fn(async () => undefined)) })
```

否则 Proxy 对 `then` 也返回函数 ⇒ promise 把它当 **thenable** 调 `then(resolve, reject)`，而 noop 忽略两个回调 ⇒ 该 promise **永久 pending**，`await getClient()` 静默挂住。症状组合很好认：动作函数被调到、日志停在中间、mock 断言 0 次、**且没有任何 rejection**。本次为此白追 4 轮；定位手段是在生产代码里临时插**分步 `console.log` + try/catch**（比猜快得多，事后务必清干净）。

## 验证与收尾

- `npx vue-tsc -b`；改动文件 `npx eslint`（对照既有错行号，别把基线算自己账）；受影响文件 `npx vitest run <files>`。全量基线**红数会漂移，别写死在这里** —— 以 `.workbuddy/memory/MEMORY.md` 的「既存失败基线（勿追）」条为准，逐位对照，只许通过数上浮；若本次改动引入了新红的嫌疑，用用户级 MEMORY 的「改动行 → 函数名 → 失败用例名」只读法取证（**禁 `git stash`**）。
- 提交：`git commit -m "..." -- <paths>`（pathspec 限定，避免裹挟在途文件）。
- ⚠️ `git commit` 可能被 SIGTERM 截断成**空输出 + exit 1**，但提交**其实已成功** → 先 `git log --oneline -1` + `git status --short` 核实，**不要重跑**。

## 变体：被多个消费方共享的 prop —— 要「加一层」而不是就地收窄

一个 prop 同时喂**视图解析**与**用户可见池**时（comind 实例：`QueryPageFrame` 的 `fields` 既供
`FieldManagerPanel` 算候选、又供 `QueryChipBar` 三个菜单、还供 `BoardView`/`CalendarView` 按 key 取描述符），
页面想只暴露自己语义内的字段时**不要就地过滤这份 prop** —— 给目标消费方新开一个可选 prop
（`candidateFields`，缺省 = 原 prop），页面注入收窄后的那份；原 prop 一个字段都不动。

先 grep 出该 prop 的全部消费点，凡 `fieldOf('status')` / `find((f) => f.key === <字面量>)` 这类
**按 key 取描述符**的地方，缺描述符都是**静默退化**、测试不会红：看板 `groupBy` 取不到 → 退化成单列「全部」；
`fieldOf('content')` 回落首个 text 字段 → 卡片标题取错列；日历 `dateRefKind` 取不到 → 不落格。
再判「用户可见的那份」留谁 —— comind tag 聚合页取「内容 + 来源页 + 该 tag 的有效字段」，
**基础列要留在池内**（删掉后才有加回路径，否则面板再也恢复不了该列）。
回归写法：断言中间层 `findComponent(X).props('candidateFields')`（比 DOM 断言穿过 Teleport 稳），
并把新断言在旧行为下跑一遍确认它真的红（`candidateFields` 缺省回退时结果会与收窄后相同 → 那种用例没有区分力）。
