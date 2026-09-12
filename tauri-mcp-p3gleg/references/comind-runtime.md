# comind 运行时拓扑与接入现状

## webview 拓扑（多窗）

comind 不是单窗应用（源：`src/composables/useReaderWindow.ts:36`）：

| 窗口 label | 身份 | 内容 |
|---|---|---|
| `main` | 主窗（tauri.conf 声明） | SPA 全量 UI：编辑器、页面、设置等 |
| `reader-<bookId>` | 每本书一个独立窗 | 阅读器（`new WebviewWindow(label, ...)`，`openReaderWindow` 按需创建） |

操作要点：
- 所有 DOM 类工具默认 `window_label='main'`——**驱动阅读器必须显式传 `reader-<bookId>`**。
- 窗口是动态的：先 `manage_window(action='list')` 或 `query_page(mode='app_info')` 枚举当前存在的窗，再选 label。书一关窗就没了。
- 插件配置了 `default_webview_label("main")`，与 comind 主窗 label 一致，默认路径即正确。

**UI 打开阅读器的路径**（2026-09-07 实测）：侧边栏「页面库」→ `/pages` 切「书房」tab → 点书卡片（如「三体全集」）→ `PagesLibrary.vue:155` 调 `openReaderWindow(bookId)` 创建 `reader-<bookId>` 窗。`bookId` 即页面 id（无连字符 UUID），reader URL 为 `/reader/<bookId>`。其他入口：`Toc.vue:220`、`PropertyDisplay.vue:81`、`Page/index.vue:75`（均带 jumpCfi 或 bookId 判断）。

## 启动方式

- dev：`npm run tauri dev`（标准路径）。
- 产物直启：`target/debug/comind.exe`（**注意**：`src-tauri` 是 workspace 成员，产物在仓库根 `target/`，不在 `src-tauri/target/`）。
- release 构建：插件不注册不编译，工具全部不可用——发现工具全超时/连接失败时先确认跑的是 dev。

## 接入现状（2026-09-07 落地，工作树未提交）

接入改动 4 文件（`src-tauri/Cargo.toml` git 依赖、`src-tauri/src/lib.rs` cfg(debug) 注册、`src/main.ts` DEV 守卫 `setupPluginListeners()`、`src-tauri/capabilities/default.json` 加 `mcp:default`）。要点：

- **认证零配置**：未设显式 token，插件启动时生成随机 token 写 socket 旁 `.token` 文件，MCP server 自动发现。也可两侧同设 `TAURI_MCP_AUTH_TOKEN`。
- **socket 走平台默认**：Unix `/tmp/tauri-mcp.sock`；Windows 命名管道 `\\.\pipe\tmp\tauri-mcp.sock`。多实例并行时每实例设自己的 `TAURI_MCP_IPC_PATH`。
- **CSP 保持严格**（`script-src 'self' 'unsafe-inline'`）：npm guest-js 同源 'self' 不受影响；插件 `on_page_load` 的 eval 注丁可能被 CSP 拦，但主路径走 guest-js，不受影响。
- **dialog stub 生效**：`alert/confirm/prompt` 非阻塞化，confirm 自动 false。comind 用到原生 confirm 的流程（如删除确认）在 MCP 驱动下不会卡死，但会默认「取消」——测试确认流要先设 `window.__TAURI_MCP_DIALOG_RESPONSES__`。
- **capabilities**：comind 无显式 `app.security.capabilities` allowlist，capability 文件自动启用——`mcp:default` 已在 `capabilities/default.json`，console/dialog 日志与 IPC 自报正常。若日后加了显式 allowlist，必须把 mcp capability 加进去，否则日志静默为空（症状见 troubleshooting.md）。

## 与 comind 调试链路的配合

- **Rust 命令层**：`manage_ipc(invoke)` 可直接调 comind 的 `#[tauri::command]`（commands.rs 入口），前后端二分定位。
- **日志**：Rust 侧 `log!()` 与前端 `console.*` 都进 query_logs 缓冲；配合 log_mark 夹逼某个 UI 操作的日志面。
- **状态读取**：comind 前端是 Pinia——若 app 注册了 `__MCP_BRIDGE__` helper 可用 app_bridge 读 store 快照（先 `action='list'` 看；comind 目前未注册任何 helper，则退而 execute_js 读 `window.__pinia` 之类需自行验证）。**实测更省事的路子**：`document.querySelector('.block-list').__vueParentComponent` → `.provides.crossBlockSelection` / `.setupState.{blockStore,pageStore,editorStore}`（`window.__pinia` 确实不存在，但 `__vueParentComponent` 可用）。

## 选区/剪贴板子系统速查（ADR-0035，2026-09-12 真机复核）

手势分流（互斥由 `useCrossBlockSelection.transition()` 保证）：

| 选区 | 起点 | 落点 |
|---|---|---|
| 块选区 | `.block-properties` mousedown（`Block/index.vue:onPropertyMousedown`）+ Ctrl/Cmd+Click（`useBlockEditorLifecycle:handleContentMousedown`） | `.block.cb-selected::after` 全块遮罩（含 bullet） |
| 文本选区 | `.block-content` mousedown（`handleContentMousedown` → `startTextTracking`） | `BlockList.vue` Teleport 的 `.text-selection-rect` 覆盖层（`selectionClientRects`） |

真机复现过的四个陷阱：

1. **`.block-properties` 在无属性的块上高度为 0** → `elementFromPoint` 命中 `.block` 自身，真实鼠标**无法**从属性区起拖；`PropertyDisplay` 无属性时 `v-if` 不渲染，也没有 hover 撑高。故普通块上块选区实际只剩 Ctrl+Click 一条路。
2. **激活块的内容区完全不启动 comind 选区**：`useBlockEditorLifecycle.ts:266` `if (editorStore.activeBlockId === blockId.value) return`（交给 ProseMirror 定位光标）；加之单编辑器模型，TipTap 只能在单块内选 → 「在激活块处开始拖拽无法多选」是设计结果，非回归。
3. **反向（向上）拖拽的高亮曾整体失效**：`selectionClientRects` 用 `range.setStart(anchor); range.setEnd(head)`，head 在 anchor 之前时 DOM Range **不报错**而是把起点钳到终点 → range 塌缩为锚点处 `0x24` 零宽矩形。修复：先按 `Range.START_TO_START` 比较并交换两端点。`text-range.ts:textRangeToText` 早已做方向归一化（`normalizeTextRange`），所以**复制正常、只有高亮失效**——这种「数据对、渲染错」的不对称是定位该 bug 的关键线索。
4. **块选区的 `Backspace` 删除在 Tauri 下正常**（`deleteSelected` → `cleanupAfterDelete` → Rust `extract_links_from_content` 命令存在）。浏览器里 red 的 4 个「基线」用例是 `WasmClientAdapter.extractLinksFromContent` 硬编码 throw（`src/wasm/client.ts:838`），**与 Tauri 运行时无关**，别把浏览器症状套到 Tauri 上。
5. **高亮矩形必须「逐块构造 + 非端点侧夹首/末文本节点」**（2026-09-12 二次修正后的正确形态）：① 跨块大 Range 在文档序上必然包住各块行首的 `.block-bullet` / chevron（都排在 `.block-body` **之前**）→ 为这些槽位各吐一个矩形，高亮**凭空盖住 bullet dot**（实测端点块 `[570,251,20×27]` 与 `.block-bullet` 盒子逐像素相等）；② 非端点侧若用容器边界 `(root,0)…(root,childNodes.length)`，还会多吐一个「整个内容区盒子」的矩形，把高亮铺成**整行色带**（单行块铺满内容区宽；多行块甚至一整个 `700×90` 盒子）。**验证判据 = 逐个渲染矩形 × 逐个 `.block-bullet` 盒子做像素级相交测试**（远比目测硬），再叠加正/反序矩形列表逐项比对。
6. **改前端 `.ts` 模块后必须 `navigate(reload)` 再测**：HMR 未接管时会测出「高亮矩形全空」的假象（本次踩过一次，白查一轮）。
7. **同一段内联盒会被 `getClientRects()` 重复上报**（2026-09-12 用户报「遮罩叠加了 2 次」）：Range 跨过**嵌套内联元素**时（`[[page]]` 实际渲染成 `span > span.block-link > span.wiki-bracket`），Chromium 按外层 span 与内层 `.block-link` **两遍**上报同一段内联盒 → 两个**逐像素相同**的矩形（浮点逐位相同，如 `622.28125|194.296875|10.828125|24`）→ 覆盖层同位叠两层、颜色深一档（单层 α=.55 = (83,88,150)、双层 α=.7975 = (108,117,204)）。**判定纪律**：先对**单个 Range 的原生输出**取样（`new Set(rects.map(String)).size !== rects.length`）——为 true 即浏览器行为，别去改自己写得好好的循环。属既有缺陷（修前的跨块大 Range 同样重复）。修法 = 在几何层按「四舍五入到 0.01px 的几何元组」去重 + 丢弃零尺寸矩形。
8. **像素取证的采样姿势**：截图后**只采色带内的背景像素**（色带上下缘各取 2–3px 高的横条，避开字形墨迹）取 median，再与理论合成值比对；采到字形（取中线）会被抗锯齿污染（本次首轮因此得到「比背景亮」的失真数字）。想确认「两层叠加」的观感，可在同位**人为叠一个克隆 div**（用 `getComputedStyle` 复制样式 —— `<style scoped>` 的属性选择器不会作用于手工创建的元素），同图对比单层/双层。
9. **键盘删除路径有两条缺口（2026-09-12 复核；均为 backlog issue，未实施）**：
   - **文本选区无删除实现** —— `handleDocKeyDown` 的 `Backspace` 只读 `anchorIds`（块选区），`textRange` 在键盘路径**零消费方**；文本选区**能复制**（`copyTextToClipboard`）**不能删**，是**对称性缺口**。规格上属**明示的范围外**（#91 非目标「Text Range 不新增删除操作（ADR-0035 D7 维持）」）→ issue **#95**。
   - **`Delete` 键对块选区无实现** —— `deleteSelected()` 全仓**唯一调用点** = `BlockList.vue:261`（在 `if (e.key === 'Backspace')` 分支内）；`handleDocKeyDown`（`:231`）键分支只有 `Backspace`/`Escape`/`Enter`/`Tab`/`Ctrl+C` → issue **#96**（用户故事 #10 承诺「按 Backspace/Delete 删除选中子树」，实现只有 Backspace）。实测块选区下：`Backspace` → `defaultPrevented: true` + 调用 1 次（栈来自 `BlockList.vue`）；`Delete` → `false` + **0** 次 + 内容**零变化**（编辑器聚焦时同）。
10. **`press_key` 不可用于文档级按键断言**：其合成 keydown **不冒泡到 document**（app 的文档级处理器根本不会运行），且它回报的「app handler called preventDefault」是插件自身 `InputState.runHandlers` 调用的、**不是 app** —— 据此会得出相反结论。正规姿势见 `SKILL.md` 铁律 17：手动 `dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}))` + 在动作上挂 wrapper。
11. **两个 API 语义易踩**：`toggleBlock` 会**连带子树**（选父块时自动带入其子块 → `anchorIds` 数多于 toggle 次数）；**`finalizeSelection()` 在非拖拽态会把选区清空** —— toggle 式块选区**不能**再调 finalize（只能在真实拖拽后调）。

