---
name: comind-legacy-dialog-to-popover
description: 当 comind 里某个「自绘居中弹窗」（自己写 overlay + dialog + Transition + z-index）要改造成通用原语 BasePopover 时使用——含四步改法（store 加 position、调用方传触发元素矩形、组件只留定宽 panel、断言容器类名的测试同步改）与三个必踩的坑（百分比尺寸 ↔ auto 宽容器循环依赖；表单里 .form-group label 压掉单选框 label 的 display；面板内原生 select/date 的弹层配色只归全局 color-scheme 管）。先例：PropertyEditor（2026-09-17）。另含改造后必补的两件收尾：默认焦点（含 KeepAlive 双实例抢焦点的守卫）与「编辑模式只读字段转纯文本」。
agent_created: true
---

# comind 遗留弹窗 → BasePopover（改造配方）

先例：`src/components/Block/PropertyEditor.vue`（自定义属性创建/编辑面板，2026-09-17）。
同类候选：任何还在自写 `*-overlay` + `*-dialog` + `<Transition>` 的居中弹窗。

`BasePopover`（`src/components/common/BasePopover.vue`，ADR-0009 D8 / 0038）已封装：
Teleport to body、overlay 空白点击关闭、Escape 关闭、定位与视口收边、fade 过渡、面板 chrome
（`--bg-base` 底 + 1px `--border` + `--radius-md` + `--shadow-modal` + `z = --z-popover + 1`）。

## 四步

1. **store 状态加锚点**：`{ visible, ..., position: {x,y} | null }`，`showX(id, ..., position?)`
   写 `position ?? null`。照抄 `showQuickPropertyEditor` 的签名约定。
   ⚠️ 加了字段就要同步**所有** `toEqual` 断言该状态的测试（否则红）。
2. **调用方传触发元素矩形**：`{ x: rect.left, y: rect.bottom + 4 }`（`rect` 取
   `event.currentTarget.getBoundingClientRect()` 或调用方已有的 DOMRect）。同一分量里
   「内置走 quick 菜单、自定义走完整编辑器」两条路要传**同一个** position。
3. **组件只留内层 panel**：
   - 模板：`<BasePopover :visible :position @close>` 包住 `.xxx-panel`；删掉自己的
     `<Teleport>` / `<Transition>` / `-overlay` / `-dialog`。
   - `position` 缺省回退视口居中：`position.value ?? { x: innerWidth/2, y: innerHeight/2 }`。
   - 样式：删 overlay / dialog / fade-transition 规则；`.xxx-panel` 自管 `padding` 与
     **定宽**（见坑 1）。
4. **补默认焦点**（改成浮层后焦点必须主动给，否则用户开面板还得再点一下输入框）：
   - `resolveFocusTarget()` 按模式/类型挑元素，`nextTick` 后 `focus()`——面板随 `v-if` 挂载，
     调用时 DOM 还不存在。
   - ⚠️ **`isConnected` 守卫必需**：调用方组件常被多处挂载（本例 `Page/index.vue` +
     `Ideas/IdeasList.vue`），KeepAlive 下可能同时存活，两份 watcher 都响应 `visible`；未激活
     那份的 Teleport 内容不在文档里，抢 focus 会把焦点从真正打开的那份抢走。
5. **同步测试**：断言容器类名（`.xxx-dialog` → `.xxx-panel`）的用例改类名；`mount` 时
   `stubs: { Teleport: true }` 已够用（BasePopover 内部 Teleport 一并被 stub）。要断言焦点
   则必须 `attachTo: document.body`（游离节点 `focus()` 不生效），并 `await nextTick()` 等
   `nextTick` 里的 focus 回调落地；mock 需要切模式时把状态提到 `vi.hoisted(() => ({...}))`。

## 三个必踩的坑

1. **panel 必须定宽**（`width: 300px` 一类），不能交给内容撑宽：表单控件是
   `width:100%` 或 `flex:1`，而「百分比尺寸 ↔ auto 宽容器」是循环依赖，浏览器会解出
   离谱宽度（本仓 2026-09-17 在 chips 上栽过一次）。定宽后 `flex:1 + min-width:0` 正常。
2. **`.form-group label` 会压掉单选框/复选项的 `label`**：`.form-group label` 特异性 (0,1,1)
   > `.boolean-option` (0,1,0)，中招后单选框被压成「圆点在上、文字在下」两行。
   改法：字段标签用**子组合器** `.form-group > label { flex: 0 0 60px }`（顺带让多行字段
   左边缘对齐），选项类名不必再争特异性。
3. **面板里的原生 `<select>` / `<input type="date">` 弹出的那层颜色不归你管**：展开的选项列表、
   日历面板、日历图标、滚动条、自动填充底、数字步进按钮都是**浏览器自绘**，读不到 CSS 变量，
   只认 `color-scheme`。全局收口在 `src/styles/base/_reset.scss`
   （`html { color-scheme: light }` + `html[data-theme="dark"] { color-scheme: dark }`）。
   **组件里绝不要再写 `color-scheme`** —— 它比全局规则更靠近元素、会覆盖收口；写成 `light dark`
   更错：那让 UA 按**系统偏好**二选一，而本应用主题由应用内开关写 `data-theme` 决定，两者解耦，
   「应用深色 + 系统浅色」时会解出白色弹层（2026-09-17 用户报的正是这个）。
   同期从 3 处组件收口回来：`ConditionPopover` / `FilterBuilder` / `PaginationFooter`。
   也别给 `::-webkit-calendar-picker-indicator` 加 `filter: invert()` —— 有了 `color-scheme: dark`
   会自动反色，再加会双重反色。

## 布局偏好（用户默认口味）

- 表单项**横排**：`.form-group { display:flex; align-items:center; gap:8px }`，标签
  `flex: 0 0 60px`、字段 `flex: 1; min-width: 0`。
- 标签**右对齐**（`text-align: right`）：标签 basis 定宽，右对齐后各标签右缘重合，右侧字段
  的左缘因此天然重合——**只加这一条就够，不必去动字段**（用户 2026-09-17 明确要的观感）。
- **编辑模式的只读字段转纯文本**，不要留 `disabled` 的 input/select：`v-if="!isEdit"` 渲染
  input/select，`v-else` 渲染 `<span class="form-static">`（`flex:1; min-width:0;
  overflow-wrap:anywhere`，长 key 换行而不撑破面板）。禁用的控件既占高度又给不出可读性。
- 分支容器（`.boolean-options` / `.array-input`）要补 `flex: 1; min-width: 0`；
  分支里的 input 若不是 flex 容器的直接子级，另补 `width: 100%`（全局
  `box-sizing: border-box`，100% 含内边距不溢出）。
- 颜色一律语义令牌：`--text-primary/secondary`、`--border`、`--accent(-hover)`、`--surface-faint`。
  旧套 `--color-ink*` / `--color-border*` / `--color-accent(-deep)` 与语义套**取值逐一相同**，
  迁移零视觉变化，别指望它带来视觉差异。

## 真机验收清单（tauri-mcp）

1. `navigate reload` 后**先等到布局稳定**（`.block` 与目标行都在、再 `wait(2~3s)`）——
   半渲染时 `getBoundingClientRect` 会全 0、`getComputedStyle().display` 为空串，
   极易误判成「样式没生效」。
2. 面板落在入参点上（含 1px 边框差：入参 `{x:420,y:260}` → panel `421/261`，外框 `420/260`）。
3. 外框 chrome 自查：`--bg-base` 底 + 1px `--border` + 圆角 + shadow + `z=901`。
4. 逐分支量「标签/字段同排」：标签左边缘一致、字段左边缘一致、中心线差 < 8px。
5. 关闭路径三连：Escape / 点 overlay 自身 / 取消按钮 → 都关；点面板内部 → **不关**。
6. 保存接线用 wrapper 拦截（`ps.setProperty = (...a)=>{calls.push(a); return Promise.resolve({})}`），
   断言入参后还原——**数据零变更**。
7. 默认焦点：`document.activeElement` 逐个模式/类型对（新建→名称 input；编辑→按类型：布尔取
   `checked` 的单选框、数组取标签输入框、其余取共用 input）。
8. 打字链路：`window focus` → `type_text`（**只给 text、不给 selector**，即「打给当前焦点元素」）
   → 回读字段值。这一步同时证明「焦点真的在输入框里」和「全局键盘处理（BlockList/TipTap）没抢
   走按键」。跑之前先确认 `editorStore.activeBlockId === null`，避免按键漏进块内容。
9. 面板里有原生 `select` / `input[type=date]` 时，自查
   `getComputedStyle(document.documentElement).colorScheme` 是否与 `data-theme` 一致
   （`light` / `dark`，**不该是 `light dark`**），并确认面板到 html 的路径上没有元素把它改回去。
   原生弹层本身抓不到截图，只能这样验证。
