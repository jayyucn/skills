---
name: tauri-mcp-p3gleg
description: P3GLEG tauri-plugin-mcp v0.3.1 运行时使用手册。当需要通过 mcp__tauri-mcp__* 工具（query_page/click/type_text/execute_js/take_screenshot/manage_ipc 等 19 个）驱动、操控或调试运行中的 comind Tauri 应用时使用——UI 自动化、E2E 式验证、复现 bug、读取页面状态、检查 Rust 命令调用、抓取应用日志。仅限 dev 构建的运行时操作，不覆盖插件接入安装（已由 2026-09-07 完成接入）。
agent_created: true
---

# tauri-mcp-p3gleg — 运行时使用手册

教 agent 如何用 P3GLEG/tauri-plugin-mcp v0.3.1（本会话的 `mcp__tauri-mcp__*` 工具）驱动与调试 comind。仅运行时使用；接入安装知识不在此（已完成，见 `D:\comind\.workbuddy\memory\2026-09-07.md`）。 **本技能只有一份正本**：`C:\Users\jay\.workbuddy\skills\tauri-mcp-p3gleg\`（用户级 = 实际加载者）；项目内 `.workbuddy/skills/` 的同名副本已于 2026-09-14 清理（陈旧漂移），勿再复制回项目——要改一律改这份。

## 前置条件（不满足时先解决再操作）

1. comind 以 dev 模式运行（`npm run tauri dev` 或 `target/debug/comind.exe`）。插件被 `#[cfg(debug_assertions)]` 包裹，release 构建完全没有这套工具。
2. WorkBuddy 已连接 tauri-mcp connector（MCP server 走 stdio，经 IPC 命名管道连 app）。工具调用报连接错误时见 `references/troubleshooting.md`。
3. guest-js 已初始化（comind `src/main.ts` DEV 守卫内 `setupPluginListeners()`，覆盖所有 webview）。未初始化的症状：`execute_js`/`query_page`/`click` 等报 "Timeout waiting for JS execution"。

## 核心工作流：发现 → 检查 → 操作 → 验证

1. **发现**：`query_page(mode='app_info')` 拿应用名/版本/窗口清单/显示器；不确定目标窗口时先做这步。
2. **检查**：`query_page(mode='map', interactive_only=true, scope_selector=...)` 拿带编号 ref 的元素图；读文本用 `read_text`；看几何/样式用 `inspect_element`；页面元信息用 `mode='state'`。
3. **操作**：点击 `click`（优先 selector，其次 ref）；输入 `type_text`；按键 `press_key`（Escape/Enter/Tab/方向键/组合键）；canvas 子区域/拖拽/hover 用 `dispatch_pointer`；原生滚动用 `mouse_action(scroll)`。**Sortable 类拖拽**用的是混合法（`execute_js` 派发带间隔的 `PointerEvent` + `dispatch_pointer('up')` 收尾），配方与踩坑见 `references/troubleshooting.md` 的「拖拽自动化」「双向落位回归配方」。
4. **验证**：`wait_for`（等文本/元素出现消失）→ `take_screenshot`（视觉确认）→ `query_logs` + `log_mark`（日志夹逼）→ `manage_ipc`（arm_event → 动作 → captured，断言 Tauri 事件/命令）。

## 工具速查（19 个）

| 分组 | 工具 | 用途一句话 |
|---|---|---|
| 观察 | query_page | 页面检查五模式：map（元素图+ref）/ html / state / find_element（精确坐标）/ app_info（应用+窗口清单） |
| 观察 | read_text | 读元素可见文本+属性，替代 execute_js 抓 innerText |
| 观察 | inspect_element | 元素 bounding rect / computed style / classList / attributes，布局与视觉 QA 首选 |
| 观察 | take_screenshot | 窗口截图，默认存盘+缩略图（省 token） |
| 输入 | click | 点击：selector 模式合成事件；右/中/双击与裸坐标走原生 OS |
| 输入 | type_text | 输入文本：单元素/多字段 fields 模式/焦点元素/文件上传；支持 contentEditable、React、Lexical、Slate |
| 输入 | press_key | 按 Escape/Enter/Tab/方向键/F 键/修饰组合键，模拟默认行为 |
| 输入 | dispatch_pointer | 精确指针手势：click/dblclick/down/up/hover/drag，可带 offset（canvas 命中） |
| 输入 | mouse_action | 原生鼠标：hover / scroll（方向/翻页/滚到元素）/ drag |
| 应用 | navigate | goto / back / forward(delta) / reload（dev 下替代 restart 的刷新手段） |
| 应用 | manage_window | 窗口管理：list/focus/close/size/position/zoom/devtools 等 21 个动作 |
| 应用 | restart_app | 重启应用（dev 模式下拒绝执行；dev 用 navigate reload） |
| 应用 | manage_storage | localStorage 增删查 + cookies 读取（clear_all 是核弹：清 cookies+cache+localStorage） |
| 应用 | execute_js | 任意 JS 逃生舱，返回末表达式值（promise 会 await）——仅在专用工具不覆盖时用 |
| 应用 | app_bridge | 调用 app 注册的 `window.__MCP_BRIDGE__` helper——读 app 状态/触发 app 动作的正规途径，先 action='list' |
| IPC | manage_ipc | invoke 任意 #[tauri::command]、emit/监听 Tauri 事件、captured 查看经手 IPC 流量 |
| 日志 | query_logs | 查缓冲日志（Rust log! + webview console），summary 先行、tail+过滤下钻 |
| 日志 | log_mark | 打标记夹逼一段操作的日志（前后同 id，query_logs between 取回） |
| 同步 | wait_for | 等文本出现/消失、元素 visible/hidden/attached/detached |

各工具的完整参数与细节见 `references/tools-reference.md`。

## 铁律（违反必翻车）

1. **禁止从截图估坐标**。截图像素 ≠ CSS 像素。要坐标点击，先 `query_page(mode='find_element')` 拿精确 CSS 坐标。
2. **ref 是短命的**。每次 `map` 调用重新编号，页面一变就失效。复用 ref 前重新 map。
3. **window_label 决定目标**。所有 DOM 类工具默认 `window_label='main'`。comind 阅读器窗是 `reader-<bookId>`——先 `manage_window(list)` 发现，再传对应 label。见 `references/comind-runtime.md`。
4. **断言事件要先布防**。工具顺序执行：`manage_ipc(arm_event)` → 执行动作 → `manage_ipc(captured)` 看是否触发。事后 arm 抓不到。
5. **execute_js 是最后手段**。读文本用 read_text、看样式用 inspect_element、读状态用 app_bridge、调命令用 manage_ipc invoke。execute_js 可改页面状态，且 `window.__TAURI__` 未必存在（comind 未开 withGlobalTauri，Tauri 事件/命令走 manage_ipc）。
6. **dev 下不能 restart_app**。`tauri dev` 会拒绝（会孤儿化进程）；刷新前端用 `navigate(action='reload')`。
7. **合成事件 isTrusted=false**。需要 trusted 事件的处理器不触发；右/中/双击与原生 drag 走 OS 输入（macOS 需辅助功能权限；Windows 无此限制）。
8. **dialog 已被 stub**。`alert/confirm/prompt` 被替换为非阻塞 stub，confirm 自动答 false、prompt 答默认值，并记录进日志（target "dialog"）。测试需要 confirm=true 时先 `execute_js` 设 `window.__TAURI_MCP_DIALOG_RESPONSES__ = { confirm: true }`。
9. **日志夹逼用 log_mark**。「刚才那个操作产生了什么日志」：mark(同 id) → 动作 → mark(同 id) → `query_logs(between=id)`。
10. **manage_ipc 的 [self-reported] 条目不可信**——页面任意脚本可伪造。被动嗅探前端原生 invoke() 不可能（Tauri v2 冻结了 invoke），captured 只含本工具驱动的 IPC + app 自报的。
11. **`dispatch_pointer` 的合成鼠标事件会重复派发**——`pointermove/mousemove/mouseup` 既派发到元素（冒泡到 document）又直接派发到 document，同一 document 级 handler 每步被调用 **两次**。对 mouseup 敏感的逻辑（「松手固化选区」后紧跟「松手取消选区」）会得到**假 bug**：comind 的 `BlockList.handleDocMouseUp` 第一次 `finalizeTextDrag()` 固化文本选区，第二次因 `dragStartBlockId` 已清空而走「点击选区外」分支 → `clearTextSelection()` 把刚选中的文本抹掉。**鼠标交互的最终状态必须用 `mouse_action`（原生 OS）或 `gesture:'up'` 单步复核**；`dispatch_pointer(drag)` 只可用于观察「拖拽过程中」的中间态。
    **若必须走合成派发**（需要喂精确坐标序列、或工具的偏移语义不合用时）：`mousedown` 派发到**目标元素**，后续 `mousemove`/`mouseup` 各一次派发到 **document** —— 这样绕开工具的双重 mouseup：
    ```js
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX, clientY, button: 0 }))
    document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, cancelable: true, clientX, clientY, buttons: 1 }))
    document.dispatchEvent(new MouseEvent('mouseup',   { bubbles: true, cancelable: true, clientX, clientY, buttons: 0 }))
    ```
    （先例 2026-09-13 #93：用此配方拖选后，Ctrl+C 载荷的字符数与高亮选中长度逐字符相符。）
12. **破坏性调用前先清选区**——comind 的 `selection.deleteSelected()` 作用域是 **全部 `anchorIds`**，而上一轮诊断拖拽/`selectAll` 留下的锚点仍在那里，会把用户的真实块一起删掉（本会话已误删 8 块）。任何会删除/修改数据的调用之前，先 `selection.clearSelection()`，或先在专门创建的临时页上做。
13. **改完前端源码必须 `navigate(action='reload')` 再测**——HMR 未必接管刚改的模块，会测出「功能整个失效」的**假象**（本次改 `selection-geometry.ts` 后测出「高亮矩形全空」，实为 HMR 未生效；reload 后一切正常，白查一轮）。判据：先确认改动已生效再解读结果；「全空 / 全不触发」这类**一刀切**的现象优先怀疑没热更，而不是代码错。
14. **几何类断言优于目测**——需要验证「某个视觉行为对不对」时，优先用 `execute_js` 做**像素级相交/等式测试**（如「每个高亮矩形 × 每个 `.block-bullet` 盒子的相交面积」），再补一张放大截图。实测结论比截图目测硬得多，也便于回归比对。
15. **发现「两个矩形同位重合」时，先证是不是浏览器干的**——Chromium 的 `Range.getClientRects()` 在 Range 跨过**嵌套内联元素**时会把同一段内联盒**重复上报**，浮点值逐位相同；DOM 覆盖层于是同位叠两层，颜色深一档。判据：对**单个 Range 的原生输出**取样 `new Set(rects.map(String)).size !== rects.length`（为 true 即浏览器行为，别去改自己的循环）；修法是在几何层按元组去重。详见 `references/comind-runtime.md` 第 7 条。
16. **像素取证的采样姿势**——只采**色带内的背景像素**（取色带上下缘 2–3px 高的横条，避开字形墨迹）取 median 与理论合成值比对；取中线会采到字形抗锯齿而失真。验证「叠两层」的观感可在同位人为叠一个克隆 div（样式用 `getComputedStyle` 复制，`<style scoped>` 的属性选择器不作用于手工元素），同图对比单层/双层。
17. **`press_key` 的合成按键不冒泡，且回报具有误导性**——① 其合成 `keydown` **不冒泡到 `document`**（挂在 document 上的捕获监听一条都收不到，实测 `keys2: []`），所以 **app 的文档级键盘处理器根本不会运行**，「按了没反应」纯属工具造成的假象；② 工具回报的「app handler called preventDefault」**不是 app 行为**——那是 `tauri-plugin-mcp` 自身 `InputState.runHandlers` 调用的（用 `Event.prototype.preventDefault` 探针拿到调用栈 = `handlePressKeyRequest`）；据此判断「app 拦截了该键」会得出**完全相反**的结论（本会话差点误判「Delete 被 app 拦截」）。
    **app 级按键取证的正规姿势** = 手动派发冒泡事件 + 在被测动作上挂记录 wrapper：
    ```js
    const ev = new KeyboardEvent('keydown', { key: 'Delete', bubbles: true, cancelable: true })
    document.activeElement.dispatchEvent(ev)
    // 读 ev.defaultPrevented（app 有没有 preventDefault）
    // + wrapper 记录的调用次数与调用栈（证「走到哪个分支」）
    ```
    另注：合成按键**不触发浏览器原生的编辑默认行为**（contenteditable 不会真的删掉字符），故「内容未变」只能证明 app 未处理，**不能**证明 TipTap 等编辑器无害——那类问题必须用真键盘才能在真机上定论。

18. **「命中面积」取证：竖带扫描 + 已确证坐标上做行为断言**——判定「某个交互面真实鼠标能不能点到 / 点到的面积有多大」时，**别只看 `getBoundingClientRect().height`**：0 高度元素仍可能坐落在某个可命中带上（comind 的 `.block-properties` 报 0 高度，但它的 y 带命中的是父级 `.block` 本身）。配方：
    ```js
    // 固定若干 x，沿 y 以 0.5–1px 步进问「这个点是谁」
    for (const x of [1200, 600, 578]) for (const y of ys) {
      const el = document.elementFromPoint(x, y)
      const bb = el?.closest('.block')
      hits.push({ x, y, t: el.tagName + '.' + el.className, inTarget: bb?.dataset.blockId === ID })
    }
    ```
    读出「哪些 y 属于目标块 / 命中的是谁 / 带宽多少」，就能把「交互面覆盖率」量化成像素结论（实例：comind 块盒 29px、`.block-content` 仅 22.4px，新增命中带只有 ≈2px——2026-09-13 #94）。
    行为侧接一刀：`dispatch_pointer(gesture='click', modifiers=['ctrl'], offset)` —— 它**在精确匹配元素上派发且不重定向**，所以选「已由 `elementFromPoint` 确证命中该元素」的坐标 + `offset`，即可把「这个点该触发什么」变成可断言的状态比对。注意合成事件 `isTrusted=false`，只对非 trust 敏感的处理器有效（comind 的 mousedown 处理器不校验 trust，适用）。

19. **⛔ 输入类实验必须在临时页/临时块上做**——`type_text` 打进 contenteditable 时**会先清空再输入**（实测 2026-09-17：`click` 激活真实块后 `type_text('/')`，该块原文「这是一个测试文本sdfs陈述」被覆盖成 `"\n\n/"`，并经 ProseMirror 同步回 store **和 DB**）。验证「加属性 / 输入 / 按键」这类交互时：先建临时页或临时块，测完删除；**真实页只做只读取证**（`query_page` / `read_text` / `execute_js` 读状态）。已误改时的恢复路径：`blockStore.updateBlockContent(id, 原文)` 写回，再用 `manage_ipc(invoke, command='get_block')` 复核 `content` 与 `deleted_at`。
20. **「输入 `/` 菜单不弹」不能直接判为产品缺陷**——comind 的斜杠菜单由 PM `handleTextInput` 派发 `slash-command-trigger`（`src/extensions/SlashCommandExtension.ts:59`），**合成输入未必走该路径**（`/` 确实进文档、菜单却不出现）。此类结论必须由用户手动输入复核，别据合成结果下判断。
21. **`emitsOptions` 空指针 ⇒ 先怀疑「刚改过模板结构 + 走了 HMR」，不是业务 bug**——`TypeError: Cannot read properties of null (reading 'emitsOptions')` 出现在 Vue `shouldUpdateComponent`（栈：`patchBlockChildren → patchElement → processComponent → updateComponent`）时，是热更中**新旧 vnode 结构不匹配**（在已有元素内新增/删除子节点后 HMR）导致该子树**后续每次 patch 都失败**、界面冻结在旧 DOM。症状会伪装成业务缺陷：新元素从不出现、点击无反应、菜单不弹、属性加不上。判据：`navigate(action='reload')` 后错误不再出现即坐实；修法是 reload/重启 dev，不是翻业务代码（2026-09-17 实证：`.block-row` 内新增 chips 容器后，属性「不显示」+「加不了」全部由此解释）。

## 读 comind 应用状态（`hasPinia` 为 false 时的正规路径）

comind 未暴露 `window.__pinia`，但 Vue 在 DOM 上挂了组件实例，足以拿到 provides 与 store：

```js
// BlockList 实例 → 选区 composable（provide 的同一个对象）+ 三个 store
const inst = document.querySelector('.block-list').__vueParentComponent
window.__SEL__ = inst.provides.crossBlockSelection      // 选区状态/composable
window.__BS__  = inst.setupState.blockStore             // blocks store
window.__PS__  = inst.setupState.pageStore              // pages store
window.__ES__  = inst.setupState.editorStore            // editor store
```

- 任意 Block 组件同样可用：`document.querySelector('.block').__vueParentComponent.setupState`（含 `propertyStore`）。
- 直读选区真值：`__SEL__.anchorIds.size` / `[...__SEL__.anchorIds]` / `__SEL__.selectedIds.size` / `__SEL__.textRange.value` / `__SEL__.isDragging.value`。
- **调用路径取证**：把 composable 的方法换成 wrapper 记录 before/after 快照与 stack，即可判定「谁调用了它」——比读代码猜快得多。
- 组件实例计数（判断是否真有第二个 BlockList 实例）：`document.querySelector('#app').__vue_app__._instance.subTree` 递归遍历 `type.__name`。注意 **KeepAlive 缓存态实例不在活动子树上**，此计数会漏。

### 读「没有 DOM 可依附」的组件内部状态（先例：#104 右侧栏，2026-09-14）

`app_bridge(action='list')` 实测返回 `{"helpers":[]}` —— 本仓**没注册任何 bridge helper**，「读状态走 app_bridge」这条路径当前不成立，只能走实例遍历：

```js
const root = document.querySelector('#app').__vue_app__._instance
let found = null
const visit = (vnode, depth) => {
  if (!vnode || depth > 30 || found) return
  if (vnode.component) {
    const ss = vnode.component.setupState
    if (ss && ss.activePanelId !== undefined) { found = vnode.component; return }  // 用目标组件的 setupState 键定位
    visit(vnode.component.subTree, depth + 1)
  }
  const kids = vnode.children
  if (Array.isArray(kids)) for (const k of kids) visit(k, depth + 1)
}
visit(root.subTree, 0)
```

适用场景：组件用 `v-if` 把根元素摘掉了（侧栏关闭时 `.right-sidebar` 整个不存在），**DOM 无从取证**，但实例仍在活动子树上、`setupState` 直接给出真值。

四条踩过的坑：
1. **`setupState` 是 `proxyRefs` 解包后的值**：`ss.activePanelId` 拿到的是字符串（不是 ref），对象/数组同理 —— 按 ref 习惯写 `ss.settings.value.defaultPanel` 会得到 `undefined` 并抛 `Cannot read properties of undefined`。先 `Object.keys(ss)` 看一眼再取。
2. **不要调 `vnode.children.default()`**（slot 函数）——在渲染上下文外调用直接抛 `Cannot destructure property 'Component' of 'undefined'`。只走 `component.subTree` 与 `Array.isArray(children)` 两条路。
3. **动态 `import('/src/...')` 未必与 app 同模块实例**（HMR 会给 app 图里的模块 URL 挂 `?t=<ts>`）：2026-09-15 实测，裸路径 import `useUndoHistory.ts` 拿到的是**另一份实例**（`hasStack` false、`_debugStats()` 的 timelineLen 0），而 app 的真实栈有内容 —— 据它读 `canUndo/canRedo` 会得出完全错误的结论，且与行为观测**自相矛盾**（`undo/redo` 明明成功）。规则：要么从组件 `setupState` 取对象，要么**永远用行为结果交叉验证读数**（读数说「无栈」而操作成功 ⇒ 先怀疑模块重复，别怀疑产品）。委派链上的 `useUndoRestore.ts` 因自身被 HMR 重写过，其内部 import 带着 `?t=` ⇒ 它才指向 app 的真实例。
4. **目标逻辑挂在组件内时，直调模块导出会绕过它（不是「没生效」，是「没跑到」）**：2026-09-15 实测，撤销/重做的落点逻辑在 `BlockList.vue` 的 `BlockList.runUndoRedo` 里（`landOnChangedBlocks`），而模块导出的 `useUndoRestore.runUndoOrRedo` 只负责执行、**不含落点**。直接调后者取证 = 落点永远不触发，画出的结论是「功能坏了」（当时误记成 bug，真机走按键路径后矩形正常）。规则：**取证走与用户同源的入口** —— app 级按键用 `document` 级监听捕获，故在块内元素上手动派发**冒泡** keydown 即可命中（`el.dispatchEvent(new KeyboardEvent('keydown', {key:'z', code:'KeyZ', ctrlKey:true, bubbles:true, cancelable:true}))`）；若只测模块内部行为（不涉组件编排），才可以直调模块函数，且结论范围只到该函数为止。

## 布局 / 尺寸类改动的几何取证配方（2026-09-17 沉淀）

验证「CSS / Vue 改动是否真按预期布局」时，别目测截图，用 `execute_js` 做几何断言：

1. **改完源码必须 `navigate(reload)` 再验**（铁律 13）。reload 后 app 回到**初始 URL**，且
   `navigate(action='goto')` 对 SPA 路由**不生效**（本会话实测：goto /ideas 后 `location.href` 仍是旧页）
   —— 用 router 跳，再等一帧：
   ```js
   const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router
   await router.push('/ideas'); await new Promise(r => setTimeout(r, 2500))
   ```
2. **断言三件套**（比目测硬）：裁切 = `list.scrollHeight > list.clientHeight + 1`；
   包含 = `el.getBoundingClientRect().bottom <= box.bottom + 0.5`；
   同行 = 多个元素的 `offsetTop` 相等。再补一张截图做观感确认。
3. **不碰 app 数据也能测 CSS 假设**：往真实容器里 `appendChild` 一个用**同类名**的临时元素
   （如 `class="chips-more-badge"`）再量几何，测完 `remove()`。
   注意：手工元素只吃**全局 `.scss`** 样式；组件 `<style scoped>` 的选择器带 `[data-v-xxx]` 属性，
   不命中手工元素（要测 scoped 样式就 `cloneNode(true)` 复制真元素来改）。
4. **量「占几行 / 多大」前先证基准盒子选对**。`round(元素高 ÷ computed line-height)` 这类除法
   在 comind 栽过四次（2026-09-17 实测数据）：
   - chips 容器自身：`height:100%` 有时解析成内容高 → 多行块判成 1 行；
   - `.block-row`：chip 行 24px > 文本行 22.4px → **度量对象反过来把度量基准撑大 → 自激放大**；
   - `.block-inner`：内含 `.block-bullet`（27px 托底），单行块也报 28px，且行高与正文不同源；
   - `.block-text`：含高内联元素时算多（文本「今日任务」元素高 34 / 行高 22.4 → 误判 2 行，实际 1）；
   - `.block-text` 还有**编辑态不存在**这一坑：块一旦激活，正文 DOM 被 `.ProseMirror` 取代，
     选择器只认 `.block-text` 就测不到行数 → 上层只能兜底成「不收纳、全显示」→ 实测 5 个 chip
     占 3 行、块行 47.2 被撑到 70.8（2026-09-17）。**基准一律写 `.block-text, .ProseMirror`**，
     并在**编辑态与渲染态各量一次**——两者 DOM 不同，只测一种必漏。
   **注（2026-09-17 补）**：chips 的「行数 × 2」放量规则随后已按用户要求下架（改为**恒定前 2 个** +
   「+N」），故上例不会复现；但**度量基准的坑与本节配方通用**——凡「按行数/高度自适应」的布局都适用。

   **首选「数视觉行盒」**（字面答案）：
   ```js
   const rg = document.createRange(); rg.selectNodeContents(textEl)
   const tops = [...rg.getClientRects()].map(r => Math.round(r.top)).sort((a, b) => a - b)
   // 容差 4px 合行：同线内联盒 top 差 1–2px，行高 ~22px
   let lines = 0, prev = -1e9
   for (const t of tops) if (t - prev > 4) { lines++; prev = t }
   ```
   后端实现同理：`Range.getClientRects` 在 jsdom **不存在** → `try/catch` 返回 0 → 调用方跳过收纳
   （保住单测行为，这也是「几何类改动无法用单测证明」时的合法出口）。
5. **度量可信度要「分布 + 逐例比对」**，不能只看一个样本：本会话取 /ideas 73 个块，行数分布
   `{1行:61, 2行:9, 3行:1}`，再用另一种度量逐例比对，0 不符才算成立。
6. **收工把路由还原**到探测前用户所在的 URL（探针会切页，别把人家的界面留在别处）。

### 已知布局陷阱：百分比尺寸 + auto 宽容器 = 循环依赖（2026-09-17 实测）

`.block-row-properties`（chips 容器）是 `width: auto`（按内容收缩），我给它内部的 chip 写
`flex: 0 0 calc(50% - 28px)` 想实现「每行 2 个」：百分比基数要等容器宽，容器宽又要等内容 ⇒
**循环**。浏览器解出的容器比 chip 实际所需**多出 56px 死空间**，chip 反被压扁——
单 chip 24px 装约 70px 内容（图标后文字被 `text-overflow: ellipsis` 截成「…」，用户截图报
「文字不显示」「一个的时候不显示」）、两个 chip 57.2px 同样截断。

**判据（一条即可确诊）**：几何量出「容器宽 ≠ 子项宽之和」——本例容器 170.5 vs 子项 2 × 57.2 = 114.5，
差 56px。凡是 `width:auto` 祖先里出现百分比 `flex-basis` / `width`，先怀疑它。

**改法**：换网格 `display: grid; grid-template-columns: repeat(2, minmax(0, max-content))`——
max-content 轨道没有循环，容器宽 = 两列内容宽之和；容器被 `max-width` 钳住时两列等比收缩，
由子元素的 `overflow:hidden + text-overflow:ellipsis` 兜底。`1fr`（两列等宽）与 `auto` 在本例也能
消除截断，但只有 max-content 是「按内容」。**别再在 auto 宽容器里用百分比表示「平分」。**

**连带坑**：`+N` 徽标若留在网格里会占掉一个格位、把块行多撑一行（行高 47.2 → 65.2）→ 把它挪出
网格，当网格容器的 flex 兄弟（`align-items: center` 即垂直居中，行高不变）。

### 改样式 / 布局前的「注入式验证」（2026-09-17 补，强烈推荐）

**落盘前先证明方案成立**：用 `execute_js` 往 `document.head` 注入一份 `<style>`——只改运行态、
不碰任何文件、即时生效、随时 `remove()` 回退：

```js
const s = document.createElement('style'); s.id = 'probe-css'
s.textContent = `.block-row-properties { width: auto !important; margin-right: 0 !important }`
document.head.appendChild(s)
// 命中真元素量几何：contW / itemW / 各 item 的 top 是否同行 / 是否溢出
document.getElementById('probe-css').remove()
```

判据与注意：
- **必须 `!important`**：要压过全局 `.scss` 与组件 `<style scoped>` 的既有声明。
- 注入的 `<style>` 不会被 Vue 重渲染清掉；但**手工 append 的 DOM 会被清** → 探针元素测完立刻
  `remove()`，别把假 chip / 假徽标留在用户界面上。
- `remove()` 后**复量一次**（几何应回到原值），证明探针本身没有副作用。
- **只想量「内容超长时会不会收敛」，别去造数据**
- **要验证的是 CSS `:hover` 的布局后果时，前两个工具都不够，用 DOM-only 内联样式探针**：
  `mouse_action(hover)` 在 Windows 走合成事件回退（自述「CSS :hover styles do not」）；
  `dispatch_pointer(gesture:'hover')` 只让 JS 的 `@mouseenter` 生效（`matches(':hover')` 仍 false）。
  正确做法：`el.style.paddingRight = '20px'`（或任何真 hover 才有的声明）→ 量几何 → `= ''` 还原。
  2026-09-17 靠它量到 chip hover「向左扩 16px、正文可用宽被压 16px」并证伪了「正文不动」。
- **`mouse_action(drag)` 在本机不产生真实「按下」**（自述 best-effort、需 Accessibility）：2026-09-23 用它拖
  `TableView` 表头分隔线，拖动后 `th` 宽度 / `.col-resizer` 位置 / tab config **三样全无变化** —— 是「根本没按下」，
  不是「拖了没生效」。凡验 **`pointerdown` 起始的手势**（列宽缩放、自绘 resize、无 `delay` 的拖拽），改用
  `execute_js` 派发**成对 PointerEvent**（元素上 `pointerdown` + `window` 上 `pointermove*` → `pointerup`，
  带 `pointerId` / `pointerType:'mouse'` / `buttons`），步长可控、不依赖窗口焦点；带 `delay` 的 Sortable 仍走混合法。
- **`navigate(reload)` 之后别立刻量**：应用要异步载入 screen/tab，本次 reload 后 900ms 读到的是**旧 screen 的 tab**
  （`currentTabId` 随后自己变成另一个），于是把「换 tab 造成的几何差」误判成「拖拽留下的异常」，白追一轮。
  判据：量之前回读 `store.currentTabId`，两次探测一致再采信。
- **验「自动焦点」这类接线，`type_text` 只给 `text`、不给 selector 就是「打给当前焦点元素」**：
  先 `manage_window(focus)`，再 `type_text({text:'abc'})`，回读字段值即可同时证明「焦点真在输入框里」
  与「全局键盘处理（BlockList/TipTap）没抢走按键」。它默认走 react-input 策略（写 value + 派发 input），
  Vue 的 v-model 会正常收到（表现为按钮由禁用转可用）。**跑之前先确认 `activeBlockId === null`**，
  否则按键可能漏进块内容。：直接改渲染出的 DOM 文本
（`val.textContent = 长串`）——临时态、不碰任何 store，量完把原文写回（或关掉浮层，
随组件卸载一起消失）。本次靠它证明纵向面板在超长值下仍收敛在 `max-width` 内、
`×` 不被挤出（面板 115.9 → 299.9，值被 240px 上限截断）。

为什么值：用户刚丢弃过一版实现、且不确定问题出在方案还是落盘时，**注入验证把「方案是否可行」
与「落盘后是否回归」解耦**——本次靠它先证「贴内容行右端 + 每行 2 个」可行（两 chip 同行、
`itemW 67.9`），再动文件，一次成功。

## Resources

- `references/tools-reference.md` — 19 个工具的参数级细节、模式说明、返回结构。
- `references/comind-runtime.md` — comind 的 webview 拓扑（main + reader-*）、接入现状、dev 启动方式。
- `references/troubleshooting.md` — 连接失败、权限拒绝、capabilities 缺失、日志空、Windows 管道等故障的判别与处置。
