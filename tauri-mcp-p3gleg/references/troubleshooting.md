# 故障判别与处置

按症状查表。通用排查第一步：`query_page(mode='app_info')`——能通说明 socket/认证/guest-js 全链路活着，问题在别处；不通则往下对号。

## 连接层

| 症状 | 判定 | 处置 |
|---|---|---|
| Connection refused | app 没跑，或 socket server 没起来 | 确认 dev 模式启动；确认插件注册在 `#[cfg(debug_assertions)]` 内 |
| Socket file not found（IPC） | 路径不匹配 | 核对两侧 socket 路径：app 侧 `socket_path`/`TAURI_MCP_IPC_PATH`，server 侧 env `TAURI_MCP_IPC_PATH` |
| Permission denied | 权限 | Unix 查 socket 文件权限（应 0600）；或改走 TCP 模式 |
| Windows 命名管道 os error 5（拒绝访问） | **环境性**：无头/受限环境禁止创建命名管道 | 本机正常桌面 dev 环境应可创建；确需绕开时两侧切 TCP 模式（app `.tcp_localhost(4000)`，server env `TAURI_MCP_CONNECTION_TYPE=tcp` + `TAURI_MCP_TCP_PORT=4000`） |

自测连接：`npx @modelcontextprotocol/inspector npx tauri-plugin-mcp-server`。

## guest-js / capabilities 层

| 症状 | 判定 | 处置 |
|---|---|---|
| `execute_js`/`query_page`/`click`/`type_text`/`wait_for` 报 "Timeout waiting for JS execution" | guest-js 未初始化 | 确认入口（comind `src/main.ts`）DEV 守卫内调了 `setupPluginListeners()`；确认跑的是 dev 构建 |
| 其余工具都好使，唯独 console/dialog 日志与 IPC 自报为空 | Tauri ACL 拒绝 webview→插件命令 | devtools 里查 `window.__TAURI_MCP_LOG_STATS__`：`ok:0, err:N` 且末错为 "mcp.push_log not allowed" = capabilities allowlist 没含 mcp capability。修法：capability 文件授 `mcp:default` 并去掉显式 allowlist，或把 mcp capability 标识加进 allowlist（dev-only） |

## 行为限制（不是故障，是设计）

| 现象 | 原因 | 正确姿势 |
|---|---|---|
| restart_app 被拒绝 | `tauri dev` 下重启会孤儿化进程 | dev 用 `navigate(action='reload')` |
| 点击没反应 | 目标 handler 要求 isTrusted=true（合成事件） | 换原生输入：坐标 click（find_element 取坐标）、mouse_action；macOS 原生输入需辅助功能权限 |
| 点击命中了别的元素 | selector 模式会重定向到最近可交互祖先 | 用 dispatch_pointer（精确命中不重定向），可配 offset |
| 坐标点击打偏 | 从截图目测了坐标 | 禁止。只用 `query_page(mode='find_element')` 返回的 CSS 坐标 |
| ref 失效 | 页面变了 / 重新 map 过 | 复用前重新 `query_page(mode='map')` |
| OS 快捷键（应用菜单/全局键）不触发 | press_key 只派发页内事件 | 无解，走 UI 等价路径 |
| confirm 弹窗「自动取消」 | dialog stub 默认安全侧 false | 先 `execute_js` 设 `window.__TAURI_MCP_DIALOG_RESPONSES__ = { confirm: true }` |
| captured 里看不到 app 自己的 invoke | Tauri v2 冻结 invoke，无法被动嗅探 | 主动 invoke 走 manage_ipc；或依赖 app 自报（push_ipc，标 `[self-reported]`，不可信） |

## 安全红线

- **仅 dev**：插件与 guest-js 均被 debug 守卫包裹；release 二进制无此面。永不在生产启用（`execute_js` = app 源内任意 JS，socket 可达即全控：会话数据、localStorage、cookies、截图）。
- token 文件与管道路径不进任何打包/分发配置。
- Windows 上命名管道与 token 文件用默认 ACL（不像 Unix 0600 限属主）——信任边界是「同用户」。
- type_text 的 files 模式会读宿主机任意文件交给页面——不传凭据/密钥/敏感文件。

## 拖拽自动化（Sortable / pointer 手势）

场景：驱动 Sortable.js（vue-draggable-plus `force-fallback: true`）类拖拽 UI 做回归。

| 尝试 | 结果 | 结论 |
|---|---|---|
| `new MouseEvent('mousedown'/'mousemove')` 序列 | 无 ghost、无重排 | ❌ Sortable 走 pointer 分支（`supportPointer`） |
| `dispatch_pointer(gesture='drag')` | `move` 事件 0 次 | ❌ 步进无时间间隔，`setInterval(_emulateDragOver, 50)` 无机会跑 |
| `execute_js` 内 `PointerEvent` 序列但无间隔 | ghost 有、无重排 | ❌ 同上 |
| `execute_js` 内 `document.dispatchEvent(pointerup)` | ghost 残留、指示器不消失 | ❌ document 级监听未生效 |
| **`execute_js`：PointerEvent 序列，每次 move 间 `await sleep(120)` → 再 `dispatch_pointer(gesture='up')`** | ✅ 落库成功、清理干净 | ✅ **推荐混合法** |

要点：
- 必须 `new PointerEvent(type, { bubbles: true, cancelable: true, clientX, clientY, pointerId: 1, isPrimary: true, buttons })`；合成 MouseEvent 无效。
- 结束手势只用 `dispatch_pointer(gesture='up')`（自带 pointerup→mouseup→click 完整链）。
- `fallbackTolerance`（本项目 =5）→ 首段移动需 >5px 才进入拖拽态。
- **「无指示器/无变化」先排除假阴性**：目标点若仍落在被拖元素自身范围内，Sortable `dragEl.contains(evt.target)` 会早退——这是正确行为，不是 bug。
- `overlayScrollbar.ts findScrollable TypeError` 是合成事件触发的副产物，无害。
- 抓拍中态：dnd 进行中截图看 `.block-ghost` / `.block-drag` / `.drop-indicator` 的 `getBoundingClientRect()` + 内联 `top/opacity`。读**当前意图**最可靠的判据是 `.drop-indicator` 的 `className`（`drop-indicator sort|nest|promote visible`）+ 内联 `left/top/width`。
- **拖拽中坐标会失效**：`pointerdown` 之后 DOM 会重排（Sortable 把被拖元素插到悬停位置），按拖拽**前**量的坐标发 pointermove 会打偏。正确姿势：`pointerdown` → 先发几帧远离目标的 move → **重新测量目标 rect** → 再逐帧逼近目标点 → 读 `.drop-indicator` 的 class/inline style 确认意图 → `dispatch_pointer(gesture='up')`。
- **拖拽期容器里有两个同 id 元素，名字反直觉（2026-09-11 校正）**：`.block-ghost` = 留在列表里的**真实被拖元素（占位）**；`.block-drag` = `_appendGhost` 造的**跟随指针的浮层克隆**（`sortable-fallback` + `pointerEvents: none` + `position: fixed`，`sortable.esm.js:1509`，append 到拖拽起始容器）。所以 `querySelectorAll('.block[data-block-id]')` 对同一 id 返回两个 —— 要取「在流内」那个，就**排除 `.block-drag`**（不是排除 `.block-ghost`）。
- 推论：`document.elementFromPoint` 在指针处**拿到的是被拖元素自己**（克隆 `pointer-events:none` 被排除），不是克隆 —— 「指针压在被拖元素上」是拖拽期的**常态**，不是异常。
- **`@move` 只在悬停块变化时触发，别拿它当意图数据源**：`_onDragOver` 开头是 `if (dragEl.contains(evt.target)) return`，而换位后被拖元素立刻被挪到指针下 → 之后每帧早退、`@move` 彻底停发 → 最后一次采样永远冻结在「指针刚进目标上半区」。表现：**向下拖落点偏上一个、向上拖正常**（同一个 bug，向上拖时冻结值凑巧等于正确答案）。若被测实现把意图挂在 `@move` 上，回归时就会看到这个症状。
- 拖拽中 `elementFromPoint(x,y)` 常命中容器（`.block-children`）而非块本身 → 用 `.closest('.block')` 取归属块。
- 拖拽中读 `.drop-indicator` 的 `className`（`drop-indicator sort|nest|promote visible`）+ inline `left/top/width` 是最可靠的「当前意图」判据；`offsetParent` 对 `position: fixed` 元素恒为 null，不能用来判可见性。

## 隔离前端 vs 后端（定位「UI 做了但没生效」）

合成 UI 操作结果不符预期时，用 `manage_ipc(action='invoke', command='<cmd>', args={...})` 直接调后端命令：

- 命令返回正常、UI 却不符 → 前端（store / 组件接线）问题
- **命令返回的值 ≠ 传入的值 → 后端写入语义问题**（最有价值的一类）

comind 实例：`invoke('save_block_tree', { blocks: [ { id, page_id, parent_id, pos, content, format, type, created_at, updated_at } ] })` 会回显每个块落库后的**最终 DB 值**（含 `version` 自增），是「这次写入到底生效没有」的权威判据。据此曾定位存储层缺陷：`parent_id: null` 被 UPDATE 忽略（version 照样 +1，值保持旧值），传 `""` 才写入（该缺陷已于 2026-09-11 修复：`save_blocks` 比对 `updated.parent_id != block.parent_id` 后调 `BlockService::set_parent_id` 补写 NULL）。补充：回显值应再用 `get_blocks_by_page` 独立复核一次，避免回显取自入参导致误判。

## 其他实测注意

- `query_logs` **不接受 `window_label`** 参数（传了会 additionalProperties 校验失败）。
- `query_logs(mode='tail', level='warn')` 同时覆盖 webview console 与 Rust `log!`，找前端 `[BlockStore]` 类警告很快。
- 真机数据被改坏时，不要靠反复拖拽还原：直接用 `manage_ipc invoke` 把 `parent_id` / `pos` 按原值写回，再 `navigate(action='reload')` 逐行比对 DOM 顺序确认。

### 拖拽落位断言（2026-09-11 实测补充）
- **终点坐标必须在拖拽进行中重测**：`pointerdown` 后 Sortable 会把源元素插到 hover 位置（force-fallback 的 `_emulateDragOver` 轮询），列表整体位移可超过 50px；按拖拽前量的坐标发 move 会瞄到隔壁块。正确顺序：pointerdown → 先绕远几帧（触发 related 变化）→ 用**元素引用**重测 `getBoundingClientRect()` → 逐帧逼近 → 读指示器。
- **落位判据看 IPC，不看 DOM**：拖拽结束后 DOM 可能与数据脱节（实测出现块文本重复、被拖块消失），必须 `navigate reload` 后用 `manage_ipc invoke get_blocks_by_page` 比对，并用独立读回复核回显值。
- **别把 `dispatch_pointer(gesture='up')` 的坐标当落点**：它会重定位到元素中心，若那次定位触发了 move，意图会被改写（症状：看到的线与落位不符）。更稳的收尾是 `selector_value='.block-drag'`（浮层克隆就在指针处，坐标与指针一致）。若实现把意图判据挂在「指示器可见性」上，up 之后指示器会被清掉，连带作废意图 —— 先看「up 之后 class 是否还带 `visible`」。
- **跨容器拖拽（子容器→根容器）会拆散子树**（本项目未修缺陷）：带子块的块拖到根容器后，其实二级子块会被提升为根级。回归时不要据此断言。


### 双向落位回归配方（2026-09-11 定型）

想严格验证「向下拖 / 向上拖各一次」，用一对相邻兄弟块（记 A、B），按下面顺序做，天然自还原：

1. `navigate(action='reload')`，等 DOM 就绪；量出 A、B 的 `.block-row` 矩形（`band = [round(top), round(bottom)]`）。
2. `pointerdown` 派发在 **A 的 `.bullet-dot`** 上（`handle: '.bullet-dot'`，Sortable 的 `_onTapStart` 绑在容器上靠冒泡命中）。坐标用 bullet 中心。
3. **一帧越过 `fallback-tolerance`（本项目 5px）**：`pointermove` 到 `(x, y±8)`，`await sleep(130)`。
4. 再一帧瞄准目标：下拖 → `y = B.row.bottom - 3`（下半区 ⇒ sort-after）；上拖 → `y = B.row.top + 3`（上半区 ⇒ sort-before）。`x` 取 `B.row.left + width*0.5`（中区；`x ≤ left+15` 是 promote、`x ≥ right-15` 是 nest）。`pointermove` 一律派发到 `document`（`_onTouchMove` 挂 document）。再 `await sleep(220)` 让动画落定。
5. 读 `.drop-indicator` 的 `className` + `style.top` 作为意图快照；同时 dump 容器直接子块（排除 `.block-drag`）的 `[data-block-id, row band, nextElementSibling]`。
6. 收尾 `dispatch_pointer(gesture='up', selector_value='.block-drag')`。
7. **判据只认 IPC**：`manage_ipc invoke get_blocks_by_page {pageId}`，按 `pos` 排序看 `parent_id=null` 的根级顺序。也可对比 `updated_at` / `version` 是否变化，确认「到底有没有写库」。

已实测（page `70fd4424…`，末两块 `DD`/`EE`）：下拖 `(930,521)` → `EE(4000)/DD(5000)`；上拖 `(930,471)` → `DD(4000)/EE(5000)`。两个方向都对才算修好 —— **只测向下拖会漏掉「向上拖原本就正常」的对照信息**。
