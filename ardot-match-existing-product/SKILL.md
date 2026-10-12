---
name: ardot-match-existing-product
description: 用 Ardot 画布为「已存在的产品」画 UI 原型/设计稿时使用（不是从零做视觉探索）。核心：跳过 search_style_guide/build_style_guide 的通用风格模板，直接从目标仓库 grep 真实设计令牌喂画布，保证原型与产品既有视觉语言一致。触发场景：给某个已有前端项目的功能设计页面原型、按仓库现有组件风格出新屏、给 ADR/issue 配可视方案。
agent_created: true
---

# 为既有产品画 Ardot 原型（不套通用模板）

## 何时用

用户要的是**某个已有前端产品里**的新页面原型（「我想先看原型页面」「按我们的风格画」），而不是脱离产品的视觉探索、品牌稿、营销页。此时通用风格目录（`search_style_guide` → `build_style_guide`）会产出与产品不一致的配色/字体/圆角，**反而增加返工**。

## 铁律：产品既有语言优先于风格目录

ardot-design-core Step 3 明写 *"User guidance wins on conflict"*。仓库本身就是最强的用户上下文 ⇒ **可跳过 Step 4/5**（style search/build），改为从仓库取令牌。

### 取令牌的动作

1. 找令牌源（顺序）：
   - `src/styles/tokens/_primitives.scss`（色阶 hex）
   - `src/styles/tokens/_semantic.scss`（语义映射 + 深色主题覆盖）
   - `src/styles/**/_components.scss`（字号/圆角等）
   - 找不到就 grep `--xxx:` 定义处，或 tailwind.config / CSS 变量文件。
2. grep 出**十六进制原值**，别只用变量名 —— 画布要 hex。
3. 建立 5 值最小集即可开画：背景 / 侧栏或卡片底 / 主文字 / 次文字 / 描边 / 强调色（+ 强调色的浅底、深一档 hover）。

（CoMind 实例：浅色 `#FFFFFF`/`#FAFAF9`、文字 `#1C1917`/`#78716C`/`#A8A29E`、描边 `#E7E5E4`、强调 `#6366F1`(+`#4F46E5`/`#EEF2FF`)，深色 `#1A1A1E`/`#818AF8` 一族见 `_semantic.scss` 覆盖段。）

## 中文字体（必查，别猜）

画布**不是**系统字体环境。中文稿先 `get_available_fonts({keywords:["Sarasa","Noto Sans SC","Source Han","PingFang"]})`，再用**返回里的精确 family + style 字符串**。

坑：CJK 字体常**没有 Medium**，只有 `Regular` / `Semi Bold` / `Bold`。写 `style:"Medium"` 会掉字。层级就用 Regular / Semi Bold / Bold 三档。

## 结构惯例（与本产品壳一致）

- 每屏一个顶层 frame，横向并排（`x = i × (屏宽 + 120)`），同 y。先 `locate_available_space`。
- 侧栏只画一次，其余屏用 `C(侧栏id, 新屏, {width:240, height:"fill_container"})` 复制 —— 省 ops 且保证一致。
- 屏内用「内容容器（padding 28, vertical）」包住所有行；行间距靠插入 `height:N, fills:[]` 的**间距 frame**，不要用 `padding` 拼（padding 是四向均匀的，拼不出左 28 / 上 0）。
- 表格严格 Table→Row→Cell→Content；单元格并排对齐靠**固定列宽**（首列 `fill_container`，其余给 px），否则各行文字不齐。
- 图标一律 `type:"frame"` + `svg`，`layout:"none"`。禁止 emoji / 单字母文字冒充图标。

## ops 预算（实测）

一行表格 = 行 frame + N 个单元格 + N 个文字（状态列再加 徽标 frame + 文字）= **约 12 ops**。所以：表头 13 ops、每行 12 ops ⇒ 单批最多放 **2 行**（25 ops 上限）。三行表格 ≈ 3 次 `batch_edit`。先列表格再动手，别画到一半改结构。

## 验证

- 每屏画完 `capture_screenshot(nodeId)` → 下载 → **看图**。不要每批都截。
- 屏宽 ≤2000 才能整屏截；超高就分段。
- 收敛即止：≤4px 间距噪音不管，最多 2 轮修正，改完不再"再截一张确认"。
- 画布上的「变体对比」比文字更能推进决策：把 A/B 两个形态各画一屏并排，交给用户选。

## 原型定稿后：落成真实代码（Design → Code）

用户说「按这个效果复刻」时，目标通常是**在仓库里实现**，不是再画一遍。此时图纸已经确定，真正的成本在**找现有基建**。

动手前先按这个清单摸一遍，能省掉大半代码（CoMind P1+P2 实例：整份落地页零新表格/零新部件，全部是接线）：

1. **页面外壳**：有没有 `QueryPageFrame` / `PageTitle` 这类现成页头外壳？有就复用，视觉天然对齐，且不用自己写工具条。
2. **记录投影**：是否已有「实体 → 卡片」的批量投影store（一次 IPC 全量、内联 properties）？有 ⇒ 「成员/结果集 → 表格」不需要新写取数。
3. **表格/视图组件**：是否已存在实体无关的 `<TableView>`，只吃 `items + fields + config`？有 ⇒ 只需把业务字段适配成它的 `FieldDescriptor`。
4. **字段 cater**:  商品/能力的字段定义（`XXXSpec`）与视图契约（`FieldDescriptor`）之间往往只差一层纯函数适配（type vocab 映射 + `get` 取值闭包）。**优先写适配层，别急着注册进全局 registry** —— 写进去会泄漏到其它消费方。
5. **持久化**：要「每个对象记住自己的视图/列」时，先看命名视图 store 是不是 keyed by entityKey。是 ⇒ 用 `entityKey = '<prefix>:<id>'` 就天然 per-object，不用新轮子。
6. **字段来源标注**（自身 vs 继承）这类纯呈现关切，留在 UI 层解算，不要污染 store。

### 三个高频坑（会浪费一整轮）

- **泛型逆变**：外壳/表格的 `fields` 契约常是 `FieldDescriptor<unknown>[]`，把它强转成具体泛型会在 `vue-tsc` 报 TS2322。用 registry 返回的**原类型**直接传。
- **同路由不同参数复用实例**：Vue Router 复用组件实例，而 store 若在 setup 顶层按 id 绑定，切对象时 store 不换 ⇒ 必须外层 `<Impl :key="id">` 强制重建。因此这类页面要拆成「路由壳 + 实现组件」两层。
- **入口去重**：新开路由承载的功能，若旧路径也渲染同一对象，要给旧路径加重定向（`router.replace`），否则同一个概念有两个界面。

### 门禁

按目标仓库既有脚本（`vue-tsc -b` / `eslint` / `vitest` / `vite build`）。**务必先看预测失败文件是否依赖你改过的模块**——成熟仓库常有基线红，不比对就修会把别人的锅算进来。

### 运行时冒烟（比编译通过强得多）

编译/单测过了不等于页面能挂载。补一次 headless 冒烟，成本约 1 分钟：

1. **优先用仓库自带 Playwright**（`playwright.config.ts` + 已缓存浏览器）。不要先花时间在全局 `agent-browser` CLI 上——它在本机曾两次静默退出（无输出 + SIGTERM），而仓库自带的 playwright 直接可用。也可用 `evaluate` 读 `#app.__vue_app__.config.globalProperties.$pinia._s.keys()` 看哪些 store 可达。
2. **必抓 `pageerror` 与 `console.error`**，只截图不看错等于没验。
3. **判「既有噪声」用对照实验**：找一个架构相同、但你**一行没改**的既有页面（如任务中心）跑同样探针。两边报同样的错 ⇒ 环境既有，别去修。例：web/WASM 路径常有主动抛错的功能存根（Screen/Tab 之类），凡用到对应 store 的页面都会报。
4. **注意环境的数据模型差异**：换成浏览器跑时，数据可能不跨会话持久（每次新 profile 都是空库）⇒ 需要"先造数据再验证"的链路，要么在一次会话内连贯完成，要么留给桌面端手工验。
5. 需要交互造数据时，先探一次**真实 DOM**（节点数 + 关键文本），别假设输入框一开始就在——很多空态页面要先点击占位文案才进编辑态。

冒烟截图与临时脚本放仓库既有的产物目录（如 `outputs/`），不要散落在根目录或 `src/`。

## 收尾

截图是内部校验物，**不要**把路径暴露给用户、不要落到仓库目录。原型屏的 node id 与文件 URL 记进项目记忆，便于后续会话直接改。
