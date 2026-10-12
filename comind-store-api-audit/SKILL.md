---
name: comind-store-api-audit
description: 当在 comind 给某个 store/composable 新增「与既有 API 同族的读或写入口」（写入口、幂等贴标、派生合并、查询算子），或怀疑某条已宣称完成的 AC（尤其「幂等」「不重复」「就近优先」「确定性」）其实没有生效时使用。四查逐条只读取证：①幂等/去重用的查询 API **作用域**是否与参数语义匹配（page-scoped vs block-scoped，错配会静默返回空集 ⇒ 守卫永不触发）；②返回记录是否**真实持久化**（核心若自生成 id 并忽略入参，本地构造的 id 是假的）；③派生/合并的**定序来源**是显式规则还是隐式适配器返回序（实测 DB 返回最新优先）；④新增字段是否**可选**（否则既有消费方全炸）。附「先证伪」配方（raw* 构造器绕开被测 API 把 bug 打成红再改）与测试钉法（钉 DB 事实，不钉返回值）。
agent_created: true
---

# comind store 读写 API 审计（四查）

先例：2026-09-18 的 `useTagStore`（`applyTag` 幂等**从未生效** + 返回假 id；`effectiveFields` 继承合并顺序与自己的 JSDoc 正好相反）—— 四查全中，四查各自命中一个真缺陷。

## 何时用

- 要新增一个与既有 API **同族**的入口（如 `extendTag` 之于 `applyTag`）——同族最容易把既有缺陷照抄一遍。
- 接手一条「已完成」的 AC，而实现是**手写守卫**（幂等、去重、防环、就近覆盖）：守卫最容易写成永不触发的死代码，且**测试常因巧合而绿**。
- 派生结果依赖「顺序」（就近优先 / 优先级 / 先到先胜 / 后写覆盖）。

## 四查表

| # | 查什么 | 怎么判（只读取证） | 中招后的修法 |
|---|---|---|---|
| 1 | 幂等/去重检查的**查询作用域** | 读那个查询 API 的实现：`getOutlinks(pageId)` 是**按页聚合该页所有块的出链**，传 block id **静默返回 `[]`** ⇒ 守卫恒不触发、幂等永远走新建分支 | 用**方向正确**的查询：判「某 block 是否已挂某关系」→ `getBacklinks(targetPageId)` 反查（且不依赖该 block 是否已加载进 store）；判「某页有哪些出边」→ 才用 `getOutlinks(pageId)` |
| 2 | 返回记录是否**真实持久化** | 读核心 service 的 create：是否**忽略入参 `id` 自生成**（`LinkService::create` 就是，随机 16 字节） | 落库后**回读**（按 source+target+关系类型反查）拿真记录。**不要**本地拼一个（id 不对应任何行，调用方拿它删链接必失败），也不要依赖 `executeBatch` 返回形态（WASM / Tauri 不同） |
| 3 | 派生/合并的**定序来源** | 把规则写成两例：**多级**（层层覆盖）+ **同层并列**（谁胜）。凡直接吃 `getOutlinks` / DB 返回序的，**实测为「最新优先」，不可依赖** | 显式定序：`sort((a,b) => a.created_at - b.created_at \|\| a.target_id.localeCompare(b.target_id))`；合并用「**规范序 + 先到先占**」而不是「反序 + 覆盖」——后者极易写成与注释**相反**的语义（反序先占位者永不被覆盖 = 最远者胜） |
| 4 | 新增字段是否**可选** | 往共享类型（`Group<T>`、`Group` 等）加字段时，先搜全部消费方 | 一律 `?:` 可选；不产该字段时**保持原形状**（如 `specs` 为空时 `return groups` 同一引用）⇒ 既有消费方零改动 |

## 先证伪：raw* 构造器

动生产代码前，用**绕开被测 API** 的本地构造器把输入形状捏到极端，先把 bug 打成红：

```ts
/** 直接建链接，不走 extendTag —— 形状可控是目的 */
async function rawExtend(childPageId: string, parentPageId: string) {
  const client = await initTestCore()
  await client.executeBatch([{ entity: 'link', action: 'create', params: {
    id: `ext_${childPageId}_${parentPageId}`,
    source_block_id: await tagRootBlockId(childPageId),  // 必须 ensurePageBlocks + flushSave，否则读路径看不见
    target_page_id: parentPageId,
    display_text: parentPageId,
    relationship_type: 'extend',
  }}])
}
```

要点：
1. 构造器必须建**真实持久化**的源块（`ensurePageBlocks` + `flushSave`）——读路径走 DB，未 flush 的块看不见。
2. 形状（多级 / 多父 / 二元环 / 三元环 / 空集）由**用例**控制，不靠被测 API 造。
3. **先跑一遍确认红**，再改生产代码。红了才知道根因；直接改容易改错地方（本次两处根因都与「以为是顺序问题、其实是初始化顺序」无关，是靠红例的 message 定位的）。
4. 红例消息本身是证据：「期望 `父-x` 实得 `祖父-x`」直接指认反序；「期望 P1 实得 P2」直接指认隐式返回序 = 最新优先。

## 测试钉法：钉 DB 事实，不钉返回值

- 「幂等」→ 断言**落库行数**（反查该 (source, target) 恰 1 行）。**别只断言两次调用返回的 id 相同**：若返回的是本地构造的假 id，两次都假、断言为真、缺陷照样在 —— 这正是 `applyTag` 幂等测试长期绿的原因。
- 「不重复聚合 / 不重复字段」→ 断言 `filter(...).length === 1` 或 `new Set(...).size`。
- 「空集语义」→ 断言边界：`sum` 空集 = `0`（加法单位元）、`avg` 空集 = `null`（无定义，**不要返 0**，否则与「真值 0」混淆、渲染侧无法显示「—」）；非数字 / 空串 / `NaN` / `Infinity` / 数组 / 布尔一律**不参与**而不是当 0 参与；补一例「真 0 不是 null」把两者钉开。
- 「纯函数」→ 断言入参未变（如 `groups.every(g => g.metrics === undefined)`）。
- 「降级不抛」→ 未注册字段 / 拼错字段名：断言按「全部无值」走（`sum`→0、`avg`→null），与内核既有风格一致（`matchCondition` 未注册→非匹配、`groupItems`→单一全量桶）。

## 反面样本：AC 声称成立而实际没有

`#130` AC「幂等：同一 (block, tag) 二次 applyTag 复用既有 link」——
守卫误用 page-scoped API（传了 block id）恒返回空集 ⇒ 每次都新建连结行；
而下游 `resolveTagMembers` 按 source 去重、`effectiveFieldsForBlock` 按 key 去重，把症状**全盖住了**。

⇒ 教训：**下游去重会掩盖上游重复**。所以「幂等」只能靠 DB 行数验证，不能靠下游观测量。

## 收尾

- 跑相邻消费方回归（本仓：`src/core/query` + TableView / TaskHub / PagesLibrary + 同族 `*.test.ts`）；`vue-tsc -p tsconfig.app.json`；eslint 改动**源**文件（`*.test.ts` 被 eslint 配置 ignore，属仓库既有约定，不是漏跑）。
- `graphify update .` + `codegraph sync .`。
- 把两个 API 陷阱（查询作用域、核心忽略入参 id）回写 `.workbuddy/memory/MEMORY.md` —— 它们是**全局**陷阱，不只属于标签功能。
