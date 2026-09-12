---
name: tauri-mcp-p3gleg
description: P3GLEG tauri-plugin-mcp v0.3.1 运行时使用手册。当需要通过 mcp__tauri-mcp__* 工具（query_page/click/type_text/execute_js/take_screenshot/manage_ipc 等 19 个）驱动、操控或调试运行中的 comind Tauri 应用时使用——UI 自动化、E2E 式验证、复现 bug、读取页面状态、检查 Rust 命令调用、抓取应用日志。仅限 dev 构建的运行时操作，不覆盖插件接入安装（已由 2026-09-07 完成接入）。
agent_created: true
---

# tauri-mcp-p3gleg — 运行时使用手册

教 agent 如何用 P3GLEG/tauri-plugin-mcp v0.3.1（本会话的 `mcp__tauri-mcp__*` 工具）驱动与调试 comind。仅运行时使用；接入安装知识不在此（已完成，见 `D:\comind\.workbuddy\memory\2026-09-07.md`）。

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

## Resources

- `references/tools-reference.md` — 19 个工具的参数级细节、模式说明、返回结构。
- `references/comind-runtime.md` — comind 的 webview 拓扑（main + reader-*）、接入现状、dev 启动方式。
- `references/troubleshooting.md` — 连接失败、权限拒绝、capabilities 缺失、日志空、Windows 管道等故障的判别与处置。
