---
name: comind-token-name-display-attribute
description: 在 comind 给实体（Tag / Page / 自定义实体）新增一个「以 design token 名存库的展示属性」（如标签颜色 `--tag-color-*`），并让它一次性贯穿 token 表 / TS 单源名单 / 白名单校验 / 后端渲染段 / 所有出现点。当要加「可选的展示性枚举属性」（颜色、图标、强调色）或要排查「色点渲染不出来 / 选回来是空」时使用。
agent_created: true
---

# comind：以 design token 名存库的展示属性（配方 + 判据）

先例：ADR-0050 D11 标签颜色（`--tag-color-1..8`，2026-09-23）。

## 何时用

- 给某实体加一个「可选、有限取值、纯展示」的属性（颜色最典型，图标 / 强调色同理）。
- 现有实现里有 hex 硬编码或凭空多一套色值需要收敛。
- 症状侧：色点渲染成透明点 / 已选色点不回来 / 「有类无色」错配。

## 核心判据（决定所有做法，先想清楚再动手）

1. **存 token 名，不存 hex**（如 `--tag-color-3`）。沿用本仓「组件样式只用 `var(--*)`、禁硬编码色值」铁律；这样换主题时旧数据自动跟随。
2. **值来自存储 ⇒ 一律白名单**。跨设备同步 / 旧版本客户端 / 手改 DB 都可能给出任意串，而它要拼进 HTML 属性或内联 `style` ⇒ 不白名单就是 CSS 注入面。
3. **「是否给样式」与「形态判断」必须同一个谓词**。否则历史非法值会出现「有类无色 / 无色无类」错配 —— 最坏渲染成既无背景又无边框的**不可见点**。
4. **色值只在一处定义**（`src/styles/tokens/_semantic.scss` 的亮 / 暗两个色块各一次）。任何第二份色值名单都是漂移源。
5. **既有数据零观感变化**：若已知默认色，把它定为调色板第 1 位，并让旧常量**收敛成它的别名**（`--color-tag: var(--tag-color-1)`）⇒ 消费点（`.block-tag` 等）零改动，`color=''` 的老数据观感不变。

## 五步配方

### 1. 调色板落到唯一真相文件
亮 / 暗各一段，各 8 条；用 `#{$color-…}` 复用既有 primitive 变量。对比度门槛按**实际用法**定：chip 拿它当**文字色** ⇒ 亮色取 600/700 段（白底过 AA，实测 4.5–5.9）、暗色取 400 段（暗底 6.5–10）。写进注释：「存库的是这些 token 名，故本表是唯一真相」。
编译自检：`npx sass src/styles/tokens/_semantic.scss /dev/null`（亮暗两套都要产出）。

### 2. TS 单源名单 + 白名单谓词
一个文件（如 `src/utils/tag-color.ts`）同时给出：`PALETTE`（token + 中文 label）、派生的 `TOKENS`、`isXxxToken(v): v is Token`、两个样式产出器（胶囊 / 圆点）。**别在组件里另写名单**。
`label` 有第二个用途：色点的 `aria-label` / `title`（可访问性顺手就有了）。

### 3. 名单守卫单测（读 SCSS 双向比对）
TS 名单与 SCSS 名单漂移是**隐蔽 bug**（无报错，只是渲染不出来）⇒ 测试**直接读 `_semantic.scss`**，双向断言（TS 的每个 token 都在 SCSS 里；SCSS 的每个 `--xxx-\d+` 都在 TS 里），并断言每 token 亮 / 暗各定义一次（`hits.length === 2`）。
⛔ 路径**不能**用 `fileURLToPath(new URL(..., import.meta.url))` —— vitest 变换后 `import.meta.url` 不是 file 协议，会抛 `The URL must be of scheme file`（表现为 0 test 通过）。用 `resolve(process.cwd(), 'src/styles/tokens/_semantic.scss')`。

### 4. 跨层：值随「已有的那次查找」一起下发
若渲染走的是后端结构化段（如 `RenderSegment::Tag`），**把色塞进同一个段**，不要在前端用 `id` 回查 store —— 渲染器是纯函数（`useContentRenderer`），回查会把状态依赖拖进渲染路径。做法：把既有的 `title → (id, is_system)` 缓存扩成 `title → (id, is_system, color)` 三元组（同一次查找，零额外成本）；Rust struct 加 `color: String`（空串 = 无色，别用 `Option`，省得前端多一个分支）。
前端渲染器侧：把色经**白名单**收口后再拼成 `style="…"` 属性字符串（无色返回空串 ⇒ 落回 CSS 默认）。
先例省力点：若 chip 内的图标用 `currentColor`（如 `.tag-hash`），着色后图标自动跟随 ⇒ **正文 CSS 零改动**。
别在编辑态重复实现：编辑态的 Decoration 可能只装饰那个图标、并不产出胶囊 ⇒ 无需另写着色。

### 5. 出现点（一次性铺全，别只改一处）
列全「该实体被渲染的地方」再动手：列表行 / 详情标题 / 继承或引用区 / 聚合页标题区 / 正文内联 chip。每处只做一件事：把 `value` 交给共享的样式产出器。
选色器组件：**不持有真相，只 emit** 归一化后的值（`null` = 选了「无色」→ 调用方发空串；D11：空串是有效值，不等于「未改」）。加一条守卫：**点自己当前那一色不 emit**（省一次无意义写 + store 重读）。
系统实体的只读性：写入侧（Rust）已拒绝时，UI **必须不给可点入口**（给了就是「点了没反应且无提示」的静默失败），改成 `readonly` 分支渲染一个 `aria-hidden` 的纯展示元素。

## 验证清单

| 项 | 命令 / 断言 |
|---|---|
| SCSS 编译出亮暗两套 | `npx sass src/styles/tokens/_semantic.scss <out>` |
| 名单不漂移 | 守卫单测读 SCSS 双向比对 |
| 渲染器输出 | 断言**精确** style 串；无色**不含** `style=`；未白名单值（用恶意串 `red;}</style><img src=x onerror=alert(1)>`）不产生 `<img` |
| 组件 | Teleport 面板：`attachTo: document.body` + `afterEach(() => { document.body.innerHTML = '' })` |
| Rust | 加一例「只给其中一个上色，另一个留空」⇒ 验证「无色」不会被误填成默认色 |
| 全链 | `npm run wasm:build` → 跑 JS 套件（改 Rust 不重编 wasm 会静默看不到新字段） |

## 陷阱

- **改 Rust 段结构后必须 `npm run wasm:build`**，产物落 `crates/pkg/`（不是根 `pkg/`）。
- **TS 段类型加了字段就要补测试夹具**（本次 `useContentRenderer.test.ts` 3 处 fixture 各补 `color: ''`），否则类型检查先红。
- **测试里读 SCSS / 任何按仓库根解析的路径**：用 `resolve(process.cwd(), …)`。
- **别把 label 当 token 存**、也别把 token 当 label 显示。
