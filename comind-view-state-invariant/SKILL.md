---
name: comind-view-state-invariant
description: 当 comind 里某个「视图状态」（折叠 / 隐藏 / 展开）存在多份载体且互相不一致、由它派生的 bug 按操作种类成串冒头时，用一个权威 + 一个不变量 + 一个收口一次修完，而不是逐个操作打补丁。含「先数真相」「隐藏用布局移除让几何消费者免费一致」「读取侧派生禁止本地副本」「写入侧收口挂在哪」四个关键判据，以及真机验证清单。
agent_created: true
---

# comind 视图状态不变量收口（折叠 / 隐藏类）

先例：ADR-0045 / PR #102（折叠语义）。适用同类：TOC 展开、隐藏块、任何「持久化标志 + DOM class + 布局后果」三份真相的状态。

## 何时用

- 某个视图状态的 bug **按操作种类成串出现**（删完残留、拖拽残留、缩进不展开、方向键落点错……）→ 这是「多份真相」的指纹。逐个操作打补丁**必然漏**：新增路径就漏，正是本 bug 的成因模式。
- 用户报的症状与代码里读得到的标志不一致。

## 第 0 步：数真相（改之前必做）

**grep 的是「谁在读」，不是「谁在写」。**

```bash
grep -rn "is-collapsed\|format.collapsed" src/ | grep -v test
```

典型三份真相（ADR-0045 实录）：

| 真相 | 载体 | 谁会读 |
|---|---|---|
| 持久化标志 | store `format.collapsed` | store 内部；**DOM 不读** |
| DOM class | 渲染输出 `.is-collapsed` | **无人读**（另一处读的是 `.block-bullet.collapsed`，第三个名字） |
| 布局后果 | `_block.scss` 只用 `max-height` 裁剪 | **几何消费者看不见** |

判据：只要「读的人 ≠ 写的人」就是本类 bug。三份里若有「没人读」的那份，别去修它 —— 删掉或让它派生。

## 配方（四条决策）

**① 唯一权威 + 读写都直连，禁止本地副本**（血例，只有真机能暴露）

读取侧必须是 `computed({ get: 读权威, set: 写权威 })`。**本地 `ref` + 挂载时拷贝 + 单向同步 = 硬 bug**：把权威写进 store 后容器类名与 `display` 纹丝不动，写入侧任何修复都**到不了屏幕**。单测发现不了（测试直接调 store），必须真机验。

**② 不变量 + 读取侧派生，而不是「每个操作后复位」**

- 不变量例：**无子节点 ⇒ 不折叠**。
- 读取侧唯一判定 = 派生值 `collapsed = flag && hasChildren`。
- 存量 stale 数据**免迁移**，读取侧派生即自愈。

⚠️ **只做读取侧兜底修不掉症状**（我在此翻过车）：0 子节点时 UI 正常，子节点一出现 stale 标志立刻复活并藏住新子节点。必须配 ④ 的写入侧。

**③ 隐藏优先用布局移除，而非视觉裁剪**

```scss
&.is-collapsed:not(.is-animating) { display: none; }
```

`display:none` 后**所有几何消费者零改动自动一致**（`Range.getClientRects()`、`elementFromPoint` 都看不到没有布局的东西）。
反之 `max-height:0; overflow:hidden` 留下「有矩形、无可见像素」的幽灵行 —— 选中态高亮照画（幽灵高亮）。

- 动画期用既有 `isAnimating` 兜时序；**常量必须与 SCSS 过渡时长一致**（`COLLAPSE_ANIMATION_DURATION` ↔ `$transition-collapse = 300ms`），否则 `display:none` 提前削掉动画尾巴。
- 展开方向天然安全：`is-collapsed` 先摘除，`display` 恢复后再跑过渡。

**④ 单一收口，签名带「双向」参数**

```ts
function reconcileCollapse(emptiedParentIds: Iterable<string>, gainedParentIds: Iterable<string> = []) {
  // emptied 且无子 → 复位 false；gained 且有子 → 复位 false
}
```

- 参数是**两个方向的父块 id 集合**，不是「操作类型」。将来新增操作只要报「谁被掏空 / 谁被填上」。
- 挂点 = **写点**，不是读点。comind 现有 4 处：`deleteBlocks`、`indent`、`outdent`、`mergeBlockInto`。
  **`deleteBlocks` 必须挂**：它是唯一删除收口，任何删除都可能掏空某个**存活**父块（含被「保留一个顶层块」闸门保留下来的那块）。
- 拖拽路径单独走：`useBlockTree.syncTreeToStore` 加可选 `affected: { gained: Set, emptied: Set }` 累加器（在 `parentId` 变更处记录），`@end` 后由 `BlockList.vue` / `BlockModal.vue` 调 `reconcileCollapse`。

## 连带要改的（容易漏）

- **导航落点**：`findNextBlockInTreeOrder` 这类遍历不感知折叠 → 方向键落到隐藏块。需要 visible-aware 镜像（有子且未折叠 → 首子；否则下一兄弟；再向上找父的兄弟）。
- **结构落入折叠块**：Tab 缩进 / 拖拽 nest / Backspace 合并落进折叠父块时顺手展开，与「落点 = 可见结果」一致。
- **有意不改的口径要写进 ADR**：选区**成员资格**仍含隐藏块、TOC/Backlinks 不尊重折叠（它们列「文档里有什么」）—— 明确记录防回改。

## 验证

**单测**：用例打在派生值上（`flag=true` + 0 子 → 读作未折叠；`flag=true` + 有子 → 读作折叠）。
⚠️ mock 写状态时**必须穿透响应式代理**（`store.blocks.find(b => b.id === id)` 再改）。直接改裸对象 → `computed` 不失效 → 「值变了但读出来是旧的」假失败。

**真机**（`tauri-mcp`，用法见 `tauri-mcp-p3gleg`）：临时页 → 验 → **永久删除**。

| 验什么 | 怎么验 |
|---|---|
| 隐藏手段 | 折叠后 `display` / 高度；展开后 `display` |
| 写入侧复位**到屏幕** | 直接往 store 写 `format.collapsed`，看**容器类名**是否跟着变（验 ① 的本地副本） |
| stale 自愈 | 折叠父块删光子节点 → 看 flag 是否复位 → 再建子节点看是否可见 |
| 几何一致 | 选区跨折叠块 → 数高亮矩形条数 = 可见行数；隐藏子节点盒应为 **0×0** |

**真机也测不了的**：`press_key` 不冒泡到 document、合成按键不触发 TipTap 原生行为 → 方向键 / Backspace 类只能单测，**在 ADR 与 PR 里如实标注「未真机验证」**，别含糊过去。

## 收尾

- 文档：新增 `docs/adr/00XX-*.md`（三份真相表 + 前提核查 + 本质需求 + Decision 逐条 + 裁定表 + 真机验证表 + Open questions），`CONTEXT.md` glossary 加词条。
- 门禁：`vue-tsc -b`；受影响套件 `npx vitest run <files>`；余红必须**取证**为既存基线（用户级 MEMORY 的只读基线判定法），**别用 `git stash`**。
- 提交：连字符分支名 + `git commit -m "..." -- <paths>`；真机临时页务必删干净。
