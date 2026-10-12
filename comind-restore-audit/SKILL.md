---
name: comind-restore-audit
description: 当 comind 出现「删除后恢复不完整 / 静默无效」类 bug 时使用——撤销·重做、undelete、回收站恢复、页面恢复都算。先量化取证（软删时间戳时序 + version 增量），再按「级联删除 vs 复活不对称」清单逐项排查，定位是前端 op 没发出、双路径（Tauri/WASM）未落地、还是客户端缓存与 DB 真值脱节。含红测试配方与真机复验步骤。触发词：恢复后数据没回来、属性没恢复、撤销后丢数据、软删不复活、undelete 不生效、restore missing fields。
agent_created: true
---

# comind 恢复路径审计（软删 / 复活类 bug）

**症状族**：删了再恢复，块回来了但**某类派生数据没回来**（属性 / link / dateRef / notification）；或恢复了但刷新后又没了；或「按了没反应」。
**不要**一上来读代码猜——先按下面取证，`恢复不完整` 的成因只有三类：**① 前端没发 op ② 发了但该路径不认 ③ 发了但被「无需写」的判定短路**。

## 铁律

1. **级联删除必须对称恢复。** 删块时 `delete_block_cascade_inner`（`crates/comind-core/src/services/block_write.rs:228`）级联了：`BlockVersion → Link → Property → Block`（+ `BlockService::delete` 里的 dateRef / notification）。而 T1 的 `undelete_blocks` **只复活块行**（`undelete_block_subtree_inner` 的 Scope 注写明派生数据不在其范围）。⇒ 每一类派生数据的复活都得有人负责，缺一个就出这类 bug。**先列清单再动手**，别只修被报的那一类。
2. **客户端缓存不是 DB 真值。** `deleteBlocks`（`src/stores/blocks.ts:1251`）只从 reactive 数组移块，**不清 `propertyStore`**；而 Rust 侧已把属性行软删（`PropertyService::delete_by_block_id` → `UPDATE Property SET deleted_at=…`）。任何「缓存 == 目标 ⇒ 无需写」的短路在**复活场景**下都不成立。
3. **复活写回靠 upsert，不是 insert。** `("property","set")` 在 Tauri `commands.rs:1535` 与 WASM `lib.rs:480` 都是 upsert（`property_upsert` 的 `ON CONFLICT(block_id, key) DO UPDATE … is_deleted=0, deleted_at=NULL`）⇒ 同 (block_id, key) 原地复活、id 必须由快照带回（重生成 id 会撞唯一索引）。前端发 `property set` 时别改 id/sort_order。
4. **双路径都要看**：桌面走 `src-tauri/src/commands.rs` 的 batch 分派，浏览器/jsdom 走 `comind-wasm/src/lib.rs`。曾出现「WASM 有该分支、Tauri 只有 create/update/delete → 落 `_ => Ok("Unknown operation…")`（**不报错**）」⇒ 桌面端静默不落库。**加新 op 类型时两条路径各看一眼**。

## 先裁决：这条缺口真的存在吗（**动手前**的前置核查）

「某类派生数据没恢复」的诉求，有时**前提就不成立**。恢复数据的来源可能是**客户端缓存**
（例：`useUndoHistory.propEnvelope` 只读 `propertyStore`，不查 DB）。此时先问一句：
**缓存对本页数据是否完备？** 不完备才需要动 Rust 补兜底；完备则诉求是**伪缺陷**。
（2026-09-15 实况：一条「未加载属性的块复活后仍丢 ⇒ 需让 `undelete_blocks` 顺带复活属性行」的挂账，
按下面清单核查后**注销**，省掉一次 T1 语义改动 + ADR-0046 D10。）

**核查清单**（逐条给落点，别只给结论）—— 问「哪些路径会让某个块**存在却没进缓存**」：

| 问句 | 查法 | 本例答案（2026-09-15） |
|---|---|---|
| 缓存何时写入？无条件吗？ | grep 加载函数的**调用点**；看是否 `onMounted` 无条件、空值是否也写键 | `useBlockPropertySync.ts:19`（唯一使用点 `Block/index.vue:82`）；`property.ts:85` 空数组也写键 ✓ |
| 有懒渲染 / 虚拟滚动吗？ | 看渲染处是否裸 `v-for` | `BlockDraggableList.vue:104` 全量渲染 ⇒ 每个块都挂载 ✓ |
| 折叠 / 隐藏会卸载组件吗？ | 看折叠实现：`v-if` 卸载 vs `display: none` | `useBlockCollapse.ts:8` = `display: none`（ADR-0045 D1）⇒ 不卸载 ✓ |
| 缓存会被驱逐 / 清空吗？ | grep 驱逐函数（如 `clearBlockCache`）的**调用点**（定义不算） | 生产**零调用**（仅定义 + 测试）✓ |
| 操作入口都在「已加载」表面内吗？ | 列出触发该操作的所有 UI 入口，逐个判断该表面下数据是否已加载 | 删块仅 `BlockList.vue:253/705`（后者 id 还限定本页）；TaskHub 无删块 ✓ |

**真机观测收口**（把推理变成观测，一次 `execute_js`）：数「页面块集合」与「缓存键集合」的差集 ——
`bs.getBlocksByPage(pageId).filter(b => !ps.propertiesByBlock.has(b.id))`，为空即完备。

**裁决后无论结论如何，都把前提钉成可执行哨兵**（否则下一个接手的人会重蹈「以为是 bug」）：
两侧各一条 —— ① 前提侧「页面块集合 ⊆ 缓存键集合」（防未来引入懒渲染）；② 数据源侧「信封覆盖缓存中
所有有值的块」（防过滤收窄）。**并做牙齿验证**（临时禁用加载 / 收窄过滤，看它变红，再还原）。


## 取证 A：DB 时间戳时序（最硬，5 分钟）

只读拷贝库再查（**别**对运行中的库直接开连接；三个文件一起拷，WAL 才完整）：

```
库位置（dev）：C:\Users\jay\AppData\Roaming\com.comind.app\workspace-dev\sqlite\comind.db{,-wal,-shm}
```

```python
import sqlite3, datetime
con = sqlite3.connect("<拷贝目录>/comind.db"); con.row_factory = sqlite3.Row
BID = "<块 id>"
for r in con.execute("SELECT id,content,deleted_at,version,updated_at FROM Block WHERE id=?", (BID,)):
    print(dict(r))
for r in con.execute("SELECT id,key,value,is_deleted,deleted_at,version FROM Property WHERE block_id=?", (BID,)):
    print(dict(r))
```

**判读**：
- `Property.deleted_at` **早于** `Block.updated_at`（复活时刻）且**未被清空** ⇒ 恢复批次根本没碰属性行（前端 op 缺失 / 被短路）。**这就是冒烟枪**。
- `Property.version` 只由 `property_update` / 两类 delete 递增，**upsert 的 DO UPDATE 不动 version** ⇒ **version 增量 = 级联删除次数**；`version>0 且 deleted_at IS NULL` = 删过又被 upsert 复活（正常修复后的指纹）。属性 create 的初值是 **0**。
- 覆盖面：「属性软删 **而** 所属块存活」的联表查询一把捞出所有历史遗留：
  `SELECT p.*, b.content FROM Property p JOIN Block b ON b.id=p.block_id WHERE p.deleted_at IS NOT NULL AND b.deleted_at IS NULL`

## 取证 B：红测试定位「op 缺失」（jsdom）

在 `src/composables/useUndoRestore.test.ts` 里**用生产路径造现场**（`await blockStore.deleteBlocks([id])` 而不是手工把缓存清空——手工清空会把 bug 一起清掉，测试假绿）：

```ts
ps.propertiesByBlock = new Map([[id, [makeProp('p1', id, 'project', 'CoMind')]]])
await bs.deleteBlocks([id])               // 生产删除路径：store 移块，缓存不动
expect(ps.propertiesByBlock.get(id)).toHaveLength(1)   // 把「缓存仍在」钉成前提
await restoreEntry('p1', entry([...blocks], { [id]: [prop] }))
const batches = hoisted.client.executeBatch.mock.calls.map(c => c[0])
const restoreOps = batches.find(ops => ops.some(o => o.action === 'undelete'))!   // ← 见下
expect(restoreOps.find(o => o.entity === 'property' && o.action === 'set')).toMatchObject({...})
```

- **批次定位坑**：`deleteBlocks` 的落库在 `setTimeout(…, 0)` 里，是**另一个批次**，`mock.calls[0]` 不一定是恢复批次 ⇒ 用 op 特征（`undelete`）筛选，别用下标。
- **取快照的坑**：`redo() ?? undo()` 会把游标留在旧快照上，后续「栈长没变」类断言随之失真 ⇒ `undo()` 取值 + `redo()` 复位。

## 排查清单（逐项打勾，别跳）

1. 前端**有没有**发这一类的 op？（红测试 / 真机 `execute_batch` 载荷）
2. op 发出后，**该路径认不认**？（Tauri `commands.rs` 的 match 分支；不认时返回 `Ok("Unknown operation…")` 不报错）
3. 判定是否被**相等短路**吞掉？（`alignProps` 比对的是**缓存**，见铁律 2）
4. 恢复后 **UI 从哪读**？（`PropertyDisplay` 读 propertyStore；但块组件重挂载会 `loadBlockProperties` 从 DB 重读 ⇒ DB 没复活时视觉立即丢）
5. **刷新后**是否还在？（store 乐观值 vs DB 真值 —— 只验 UI 会漏掉「乐观写掩盖未落库」）

## 已知陷阱

- **恢复必须给「复活块」无条件重发全部属性 set**（`useUndoRestore.reviveProps`）。走 `alignProps` 的相等判定会得出「无需写」。
- **快照信封（`useUndoHistory.cloneProperty`）禁含服务端时间戳**：`createdAt/updatedAt` 会让「复活块重挂载 → `loadBlockProperties` 重读 DB」后的同一状态**签名漂移** ⇒ `pushSnapshot` 推入伪快照并**截断 redo 尾**（实机症状：删块 → Ctrl+Z 后 ~500ms 起 Ctrl+Shift+Z 变 null）。归零后签名稳定。（`captureEntry` 与 `propSig` 必须共用同一 `propEnvelope`——两处各自维护字段清单必然漂移。）
- **快照属性只来自 propertyStore**：客户端从未加载过属性的块（理论上）复活后仍丢 —— 彻底解需 Rust `undelete_blocks` 顺带复活属性行，**动 T1 语义须先过 ADR-0046 D10**，勿顺手改。
- **真机上别用裸路径 `import('/src/…')` 读 app 的模块级状态**：HMR 后 app 图里是 `?t=` 实例，裸路径另起一份（`hasStack` 假 false）⇒ 读数与行为矛盾时先怀疑模块重复。见技能 `tauri-mcp-p3gleg` 的「三条踩过的坑」第 3 条。

## 收尾（必做）

1. 红 → 修 → 绿，再做一次**回退该行的交叉验证**（确认测试真的钉住了这个缺陷，而不是本来就绿）。
2. 门禁：目标套件全绿 + `vue-tsc -b` 0 错 + 改动文件 eslint 0 + 全量 `vitest run` 与既存基线（约 19–20 文件 / 54–56 例红，会漂移）逐项比对，**失败清单里不得出现改动的套件**。
3. 真机复验走**用户真实操作链**（setProperty → delete → Ctrl+Z；再 redo → undo 反向一遍），三处对齐：store / DOM（`.block-properties`）/ DB 行。破坏性调用前先 `selection.clearSelection()`，并优先在 scratch 页上做。
4. 落记忆：`.workbuddy/memory/YYYY-MM-DD.md` 记过程，`MEMORY.md` 只留「光靠日志搜不到」的结论。
