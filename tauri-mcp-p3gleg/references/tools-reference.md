# 工具目录（19 个，v0.3.1 实测 schema）

来源：本仓库连接的 mcp server（P3GLEG tauri-plugin-mcp v0.3.1，git commit c7d271a0）一线 schema。通用约定：DOM 类工具均支持 `window_label`（默认 `'main'`，见 comind-runtime.md）；所有坐标均为 CSS 像素。

## 观察

### query_page
| mode | 用途 | 关键参数 |
|---|---|---|
| `map` | 结构化元素图，返回带编号 ref | `interactive_only`（默认 false）、`scope_selector`（字符串或数组，收窄扫描范围）、`include_content`（默认 true）、`max_depth` |
| `html` | 原始 DOM HTML（大，map 不够用才上） | — |
| `state` | URL/标题/滚动/视口元信息 | — |
| `find_element` | 按 ref/selector 定位元素，返回**精确 CSS 像素坐标**——坐标点击的唯一合法来源 | ref / selector |
| `app_info` | 应用名/版本/OS/窗口清单/显示器 | — |

要点：内容多的页面 map 会产出几百个文本 ref，务必 `interactive_only=true` 和/或 `scope_selector`。ref 每次 map 重编号、随页面变化失效。

### read_text
读匹配元素的可见文本。参数：`selector`（必填 CSS）、`all`（默认 true）、`limit`（默认 20，上限 200）、`attrs`（附带属性如 `['aria-label','data-testid']`）、`max_chars`（总预算默认 4000，截断时置 truncated 标志）、`scope_selector`。返回每元素 `{tag, text, visible}`，空白折叠。

### inspect_element
视觉/布局 QA 专用。参数：`selector`（必填）、`all`（默认 false 只看第一个）、`limit`（默认 10，上限 50）、`style_props`（任意 CSS 属性名数组；默认给布局+颜色标准集）。返回 bounding rect、computed styles、classList、attributes。

### take_screenshot
参数：`window_label`、`quality`（JPEG 1-100，默认 70）、`max_width`（默认 1024）、`max_size_mb`（默认 1.0）、`output_dir`（默认系统临时目录）、`inline`（默认 false：存盘+小缩略图，省 token；true 则返回全尺寸 base64）、`audience`（user/assistant/both）。只读不改状态。**截图坐标 ≠ CSS 坐标，禁止目测点击点。**

## 输入

### click
- **selector 模式**（首选）：`selector_type`（ref/id/class/css/tag/text）+ `selector_value`；可选 `scope_selector`（限定容器）、`match`（text 的 exact/contains）、`nth`（多命中取第 n 个，0 基）。左键单击走合成事件（pointerdown→mousedown→pointerup→mouseup→click），不受窗口焦点/显示缩放影响，可能重定向到最近可交互祖先。
- **坐标模式**：裸 `x`/`y`（CSS 像素）——只能用 find_element 返回的坐标。右/中键、双击与坐标模式走原生 OS 点击。

### type_text
四种模式：
1. `fields` 数组一次填多字段（每项 ref 或 selector_type+selector_value + value + clear 默认 true），可带 `submit_ref` 填完点提交。
2. `selector_type`+`selector_value` 定位单元素。
3. 只给 `text` 打进当前焦点元素。
4. `files`（绝对路径数组）+ selector 上传文件到 `<input type="file">`（单文件 10MB、总量 25MB 上限；**会读宿主机任意文件交给页面——勿传敏感文件**）。

支持 input/textarea/`<select>`（按 value 或 label 选中）/contentEditable/React 受控组件/Lexical/Slate。`delay_ms` 键间延迟、`initial_delay_ms` 焦点模式初始延迟。

### press_key
`key`（DOM 键名 'Escape'/'Enter'/'Tab'/'ArrowDown'/'Backspace'/'Delete'/'Home'/'End'/'PageUp'/'PageDown'/'Space'/'F1'-'F12' 或单字符）、`modifiers`（ctrl/cmd/shift/alt）、`repeat`（1-100，如 ArrowDown×3）、可选 selector 先聚焦目标。模拟默认行为（Enter 提交、Tab 移焦点、Backspace 删字），除非 app preventDefault。**OS 级快捷键不触发**（应用菜单/全局快捷键）。

### dispatch_pointer
在**精确匹配元素**上派生手势，不重定向到交互祖先。参数：`selector_value`（必填；selector_type 默认 css，可用 ref）、`gesture`（click/dblclick/down/up/hover/drag）、`offset`（相对元素左上角 px，默认中心——**canvas 命中测试必备**）、`to`（drag 目标：绝对 {x,y} 或相对 {dx,dy}）、`steps`（drag 插值步数默认 8）、`button`（0/1/2）、`modifiers`。drag 的 move 事件同时派发到 document（兼容 d3-drag；合成事件绕过 setPointerCapture）。合成事件 isTrusted=false。

### mouse_action
原生 OS 输入。`action`：
- `hover`：移光标到 x,y（macOS 无辅助功能权限时降级为合成事件——JS handler 触发但 CSS :hover 不生效）；`relative=true` 时为相对偏移。
- `scroll`：`direction`（down/up）、`amount`（像素数/'page'/'half'）、或 `to_ref`（滚到某元素进视口，响应会报告是否落进视口）、`to_top`/`to_bottom`。
- `drag`：start (x,y) → (end_x,end_y)，两次顺序 move 的尽力模拟，需辅助功能权限。

## 应用控制

### navigate
`action`：`goto`（+url）、`back`/`forward`（+可选 `delta`，正负号决定方向，delta=2 向前跳两步）、`reload`。完成后用 `query_page(mode='state')` 确认。

### manage_window
`action` 21 种：窗口类 `list`/`focus`/`minimize`/`maximize`/`unmaximize`/`close`/`show`/`hide`/`set_position`(x,y 屏幕像素)/`set_size`(width,height)/`center`/`toggle_fullscreen`；缩放 `set_zoom`(scale 0.1-5)/`get_zoom`；devtools `open_devtools`/`close_devtools`/`is_devtools_open`；webview 状态 `clear_browsing_data`/`set_background_color`(r,g,b,a)/`get_bounds`/`set_auto_resize`(enabled)。全部按 `window_label` 作用到对应窗。

### restart_app
`delay_ms`（100-5000，默认 500，让在途操作完成）。冻结时强杀（仅 IPC 模式）。**`tauri dev` 下拒绝执行**（避免孤儿化 dev supervisor 之外的进程）——dev 下刷新用 `navigate(action='reload')`。破坏性：内存态全丢。

### manage_storage
- `store='local_storage'`：`get`/`set`/`remove`/`clear`/`keys`（+key/value）。
- `store='cookies'`：`get_all`/`get_for_url`(+url)/`clear_all`。
**`clear_all` 清全部浏览数据（cookies+cache+localStorage），不只是 cookies。**

### execute_js
`code`（必填；末表达式值被返回，promise 自动 await；值必须 JSON 可序列化——DOM 节点/函数返回为字符串）、`timeout_ms`（默认 5000，上限 300000，await 慢 promise 时调大）、`window_label`。通用逃生舱，但注意：`window.__TAURI__` 仅在 app 开 `app.withGlobalTauri` 时存在（comind 未开）——Tauri 事件/命令一律走 manage_ipc。

### app_bridge
调用 app 经 `window.__MCP_BRIDGE__.register(name, fn, description)` 注册的 helper——读 app 状态（store 快照）/触发 app 级动作的正规途径，优于对 app 内部结构 execute_js。**先 `action='list'` 发现可用 helper**；`action='call'` 时给 `name`+`args`（位置参数数组）+`timeout_ms`（默认 10000）+`max_chars`（默认 20000）。每个窗口有独立注册表（window_label）。helper 可为 async，结果 JSON 序列化。

## IPC 与日志

### manage_ipc
`action`：
- `invoke`：调任意 `#[tauri::command]`（`command` 名、`args` 对象按前端 camelCase、`timeout_ms` 默认 10000）——前后端二分定位 bug 利器。也支持插件命令（`plugin:dialog|open` 形式）。
- `emit`：向 app 发 Tauri 事件（`event`+`payload`）。
- `arm_event`：**动作前**注册后台监听（`event`+`timeout_ms` 默认 60000 上限 300000），之后动作用别的工具触发，`captured` 查收。
- `wait_event`：阻塞等待事件——只对自复发事件有用（阻塞期间无法触发任何东西）。
- `captured`：列本工具经手的 IPC（invoke+emit/收发事件），过滤：`kind`（invoke/event）、`name_contains`、`status`（ok/error/emitted/received；**status='error' 只看失败 invoke**）、`since_id`（游标）、`limit`（默认 50）。
- `commands`：按命令聚合统计（含 app 经 PluginConfig::expose_commands 声明的）。
- `clear`：清缓冲。

限制：**无法被动嗅探 app 前端原生 invoke()**（Tauri v2 冻结 invoke 函数）；captured/commands 只反映本工具驱动的 IPC + app 自报（push_ipc）条目；自报条目标 `[self-reported]`，页面脚本可伪造，**视为不可信**。

### query_logs
查缓冲日志（Rust `log!()` + webview `console.*` + 拦截的 dialog）。`mode`：
- `summary`（先看这个）：计数 + 最近 10 条 warn/error，小载荷。
- `tail`：`level`（最低严重级，'warn'=warn+error）、`source`（rust/js）、`contains`（子串）、`since_id`（配 nextCursor 增量跟读）、`since_ms`、`limit`（1-1000 默认 100）、`head`（true=最旧，默认最新）、`format`（compact/json）、`between`（log_mark 标签，只取两标记间的）、`include_markers`、`include_plugin`（默认 false 隐藏插件自身日志）。

缓冲有界——`droppedTotal` 非零表示旧日志被挤掉。

### log_mark
`id`（1-128 字符，begin/end 对复用**同一个** id，如 'click-submit'）+ `note`（可选说明）。只打一次时上界为「现在」（"自从我开始 X 以来的一切"）。

### wait_for
`text`/`selector`/`ref` 三选一 + `state`（visible/hidden/attached/detached，默认 visible；hidden 对文本=消失）+ `timeout_ms`（默认 10000，上限 300000）。异步内容加载（导航/提交/AJAX）后等条件成立。
