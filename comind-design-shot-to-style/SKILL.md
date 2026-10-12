---
name: comind-design-shot-to-style
description: 用户发一张设计稿/目标效果截图，要求「把某个 Vue 组件改成图里的效果，并截图验证」时使用（comind 尤其常见：设计稿多为 Ardot/Figma 导出的 1x 图，按 token 绘制）。核心是三步取证链——① 用 PIL 量化目标图（几何+色值，判 1x 还是被缩放）并把色值映射到本仓 design token；② 只改该组件的 CSS（必要时加一层包装 DOM），保留既有类名以不破测试；③ 在 outputs/ 建 vite dev 直开真实 SFC 的夹具 + Playwright 后台截图 + 按「卡片宽 / 控件轨道高」对齐叠图，产出 A/B 对比图与数值对照表。触发词：改成图中的效果、按设计稿改样式、截图验证、视觉还原、设计稿落地、和这张图一样、分段控件、要不要和 X 对齐、改完样式后按钮点不动/点了没反应、样式简陋/想提升质感/重新设计（**无参考图**时走分支 A：先出 HTML 原型对照再落组件，别叠肉眼不可见的纹理）。
agent_created: true
---

# 设计稿截图 → 组件样式落地 + 截图对照验证

## 何时用

- 用户发截图 + 「把 `<某>.vue` 改成图中的效果」「和这张图一样」「截图验证」。
- 组件是 comind 的 Vue SFC（TableView / BoardView / 属性面板…），图是设计稿或参考 UI。
- 图里的字段/数据是示意（如 `待开始` 而仓里是 `待办`）——**照抄的是观感，不是数据**。

### 分支 A：用户说「简陋 / 想提升质感 / 重新设计」，但**没给参考图**（2026-10-05 实证）

与「有设计稿」相反：无从取证，**方向本身是待定的**。别凭直觉直接改 CSS，两条硬教训：

1. **alpha ≤ 0.1 的纹理（点阵 / 角落柔光 / inset 光晕）在真实观感里读作「没改」**。Jay 对「提升质感」的真实
   期待是**换整格的视觉母题 / 结构**，不是叠一层看不见的噪点。做完自检：截图与改前并排，非专业眼能不能说出
   「哪变了」？说不出 = 白做（本次被直接回「没啥改动啊」）。
2. **先出 HTML 原型对照（2–3 个完整方向）再动组件**。原型要**完整渲染目标区域**（如整个 2×2 象限视图，
   不是孤立一格）、带真实示例数据、亮 / 暗可切 —— 用户对着真图挑（可能回「先给 html 原型效果」），挑完再落
   **一个**文件。实例：`outputs/quadrant-redesign-proto.html`（A 巨型网格水印 / B 彩色头部面板 / C 大字号背板）
   → Jay 选 B。方向选项：**换母题 / 换结构 / 加对比**，别出「加一点阴影」这类同级玩具选项。
3. **落组件时「删干净上一版」**：重设计常是替换而非叠加 —— 先把上一版为此加的 CSS **整段删掉**
   （`Edit` old_string 覆盖整块），再写新的，避免新旧规则并存互相打架。
4. **静态预览别把语义写死**：镜像真实 scss 的预览里，图标「点亮格」这类语义必须带参数（与 `Icon.vue` 的
   `PRIORITY_QUADRANT` 映射表对齐），否则预览里各图标长得一样、误导判断（本次第一版就踩了）。
5. **方向选定后仍可能改选**：Jay 先选 B（彩色头部面板）、落完又改「还是改成 A 吧」。⇒ 落组件的代码要
   **干净可换**（上一版整段可删），别把两版揉在一起；「与既有图标母题的一致性」常常比「对比度 / 醒目度」权重更高
   —— A 的胜出理由是「与块行 2×2 图标同母题」，不是它更好看。选方向时把这条摆在台面上。
6. **装饰性水印别为「出画」裁掉结构**：本轮 A 第一版用 `right:-7%;bottom:-9%` 负偏移 ⇒ 四格只露「L 形」三格，
   **读不出 2×2**（而 2×2 就是该图元的语义）。改为完整内嵌（`right:12px;bottom:12px;width:40%`）才立住。
   ⇒ 图元类背景（网格 / 方块 / 点阵）的**结构本身就是信息**，宁可小一点、也要完整；裁切只适合无结构语义的纹理。

## 第 1 步：像素取证（不要目测）

用 `C:/Users/jay/.workbuddy/binaries/python/envs/imgmeta/Scripts/python.exe`（已装 PIL；managed python 没装）。

必测四项，写成一次性脚本落 `outputs/`：

1. **纵向剖面**：逐 y 统计非白像素数 + 最小亮度 → 得到卡片上下边、表头高、行高、分隔线位置。
2. **横向剖面**：在行内取一条 y，看非白 x 区间 → 竖线有无（comind 目标稿常常「无竖线」）；再逐段扫描文字左缘，反推列宽（文字左缘 − 单元格左内边距）。
3. **色值**：对每类文字/底色取**最暗像素**，直接对上 token（见下表）。半透明底（胶囊）取出现次数最多的底色。
4. **判 1x / 被缩放**：细线若只落在 1 个像素且达到全色（如底边 = `(231,229,228)` 恰好 `--border`）→ 1x 未缩放；若 1px 竖线被摊成 2 列半亮、文字峰值永远到不了色值 → 图被重采样过。**结论决定「按原图像素实现」还是「按 token 尺度实现、只在对照时缩放对齐」**（本仓取后者：保留 `--text-sm/--text-xs`，靠叠图缩放比对比例）。
5. **字号用「字形墨迹高度」比，不要用字宽，也别假设表头更小**：对同类文字（如都是中文）取 `ink_bbox` 的**高度**比
   （4 个像素以内的差就是同级；宽度会因字距/单双字被误读）。实测：comind 那张聚合页设计稿表头与正文**同字号**
   （都是 ~10.5px @1x，墨迹高 9px vs 9-10px）→ 表头靠**浅字色**与数据区分，实现应保持字头 `--text-sm` 而非 `--text-xs`；
   判错会让对照图里表头明显偏小。表头高（目标 31）÷ 行高（目标 40）= 0.775 是另一个可直接对齐的硬指标。

### comind token 实测值（2026-09 核对；`$color-stone-*` 与 Tailwind 编号**差一档**）

| 用途 | token | 亮色值 |
| --- | --- | --- |
| 卡片描边 | `--border` | `#E7E5E4` |
| 表头底 | `--surface-muted` | `#FAFAF9` |
| 胶囊中性底 | `--surface-subtle` | `#F5F5F4` |
| 主文字 | `--text-primary` | `#1C1917` |
| 次要文字（表头/来源页/日期） | `--text-secondary` | `#78716C` ← 是 `$color-stone-600` |
| 三级文字（中性胶囊字） | `--text-tertiary` | `#A8A29E` ← 是 `$color-stone-500` |
| 强调（进行中胶囊） | `--accent` / `--accent-subtle` | `#6366F1` / `#EEF2FF` |

判定捷径：**若目标图所有色值都能落到上表，说明设计稿就是按本仓 token 画的 → 实现必须走 token，不要写死色值。**

### 图标 / 图元稿（自绘 SVG 图元）的特殊取证

设计稿里的图标 / 小图形（非表格 / 卡片 CSS）要重绘成 `<svg>` 组件时，取证维度不同（用 imgmeta 的 PIL）：

1. **外尺寸**：bbox 定图标内容边界（含描边）；转 viewBox 单位按「内容 / 总图」比例。
2. **格宽 / 间隙 / 圆角**：用**行列剖面**（`runs(arr)` 取非空像素连续段）反推 —— 2×2 排布时
   列 runs 给每列起止、行 runs 同理；`gap = 相邻 run 间距`、`size = run 长度`。
   圆角半径：对单数行逐行取 `leftmost fg x`，首行内缩量 ≈ 角弧半径（反解 `r - sqrt(r) ≈ 内缩`；
   `r≈4` 内缩≈2、`r≈3` 内缩≈1.3）。
3. **描边宽度**：单行剖面里描边是两侧对称的 `n` 像素段（如 mid 行 `[30,31,32] [41,42,43]` ⇒ 宽 3）。
4. **填充不透明度**：取实心区色 `C` 与空心描边色 `f`，`a = (f-bg)/(C-bg)` 反解 alpha（bg 用四角色）。
   参考图的**不透明度只是层级处理**，颜色 / 位置按本仓语义重定 —— **不要照抄色相**（用户常标注「颜色、位置是错的」）。

5. **⚠ 描边同心内缩（最易踩）**：SVG `stroke` 居中落在 path 几何上。若 N 个方格同 path 几何、
   相邻间隙 ≤ 描边宽，相邻描边会**互相吞并**糊成一片。修法：以「外边界」为布局基准，
   方格 path 几何 = 外尺寸 − `sw/2`，相邻外边界间隙 = 几何间隙 − `sw` ≥ 1 单位。
6. **实心格与描边格要同视觉尺寸**：实心方块只画 `fill`、不画描边，会比带描边空心方格**小一圈**。
   统一做法：实心格也带同色描边（`fill + stroke` 同色 ⇒ 视觉尺寸 = 外边界）；或实心格 path 取外尺寸、空心格内缩。
7. **形状验证靠 4× DPR 截图**：`deviceScaleFactor: 4` + 各档 24/20/16/12px 全列、亮暗双底，`outputs/` 落夹具
   （gitignore），肉眼 / 像素扫描确认「实心格位置可辨、四格不并档」。
8. **组件侧**：自绘 SVG 经 `Icon.vue` 的 `h()` 包装层透传 `size`/`color`/`strokeWidth` 时，
   必须 `inheritAttrs: false` + `{...attrs}` 展开，否则 `color` 丢失、图标退回 `currentColor`。

## 第 2 步：改组件

- 只动必要 CSS；**保留既有类名与 DOM 层级**（TableView/BlockList 等有大量测试断言类名）。
- 需要新的结构层（如「值胶囊」包住 label）时，把新层**加在**既有类名外面/里面，不要重命名。
- 观感差异可能不在 CSS 而在字段元数据：例如「进行中」要变 indigo 胶囊，正确落点是
  `useBlockQueryRegistry.ts` 的 `Option.color`（配色上提为字段元数据，ADR-0007），组件里只做通用机制
  （有 color → `color: c` + `color-mix(in srgb, c 10%, transparent)` 底；无 color → 中性 token 胶囊）。
- 既有测试若断言了被替换的元素（如 `.color-dot`），**改测试**并写清新契约，不要为迁就测试牺牲观感。

### 组件自绘卡片 vs 宿主外壳供框：先数消费方再决定

设计稿只画了组件本身（如表格卡片），看不出那圈外框是「组件自绘」还是「宿主容器提供」。判据顺序：

1. **数消费方**：grep 组件的使用点。comind 实测 TableView 的三个消费方（`PagesLibrary` / `TaskHub` /
   `TagAggregateBody`）**全部**经 `QueryPageFrame` 的 `#table` slot 注入 —— 组件从不脱离宿主存在，
   故两层框必然同时出现，**只能舍其一**（不存在「谁都不动」的选项）。
2. **别从设计稿反推宿主底色**：聚合页设计稿卡片外是 #FAFAF9，我曾据此认定「页面底 = `--color-paper`」并写进了产品注释；
   真机 `inspect_element` 实测 app 页面底是**纯白 `--bg-base`** —— 那片灰只是设计工具的画布底。
   宿主/页面底的 `background-color` 必须实测，不能从设计稿的裁切外区域推断。
3. **优先让宿主让位**（去它的 border），而不是让组件放弃自绘：组件保持自洽（离开宿主仍是卡片），
   宿主退回纯滚动容器。**只去 border、保留 padding** 时 board/calendar 无需按视图类型分叉 ⇒ 零耦合的一处改动。
4. 若真需要按视图分叉，走 `ViewTypeOption`（`core/view/management.ts`）加可选标记的数据驱动路线，
   不要在宿主里写 `currentViewType === 'table'`（ADR-0023 D6 外壳零视图耦合）。
5. **宿主难以直开时，复刻它的几何做多格对照**：`QueryPageFrame` 依赖 screenView store + 查询引擎，
   夹具里直开成本高 → 复刻宿主的 border / padding / border-radius 三个属性（数值逐个从源码抄），
   排成四格一趟截完：A 改前（带框）、B 改后、C/D 同宿主下的其它视图（看板 / 日历，验证连带影响）。
   `fullPage: true` 一次给齐「效果 + 副作用」，比只测目标组件负责。实例：`outputs/tv-shell-ab.png`。

### 本仓踩过的坑（改表格/卡片必看）

- **th 的 UA 样式是 `text-align: center`**：只删 CSS 里的 `center` 仍会居中，必须显式 `text-align: left`（列显式 align 由内联样式覆盖）。
- **卡片描边必须用 `border`，不能用 `outline`**（2026-09-23 真机实证；本节前版写反了）：
  `thead` 是 `position: sticky`（属定位后代），按 CSS 绘制顺序画在**表格自身装饰（outline）之上** → 表头灰底把卡片
  上缘那 1px 描边整段吃掉，左右描边在表头高度内也断裂（真机实测：左描边暗段 `y283-462`，表头段缺 32px）。
  `border` 是表格盒子的一部分，**子元素背景都盖不住它**（sticky 表头、`td:hover` 高亮同理）。同理适用于任何
  「祖先用 outline 画框、后代又带背景」的组合。
- **`border-collapse: collapse` 下 `border-radius` 不生效**（Chrome 忽略 collapse 表格的圆角 → 四角是直角）。
  要圆角必须 `border-collapse: separate` + `border-spacing: 0`；代价是 **separate 模式不绘制 `tr` / row group 的边框**
  —— 行分隔线要挪到 `td` 上，末行 `tbody tr:last-child td { border-bottom: none }` 收口。
- **表框会不会「撑宽」，取决于是 collapse 还是 separate**（2026-09-23 两次真机实测，前版那条笼统结论要拆开）：
  - `collapse`：表格边框与单元格边框合并 → **不计入** used width（实测带 `border` 时 `tableW` 恒 1218 = 声明宽）。
  - `separate`：表格边框**计入** used width —— fixed 布局取 `used = max(声明宽, 列宽和 + 表格边框)`。若列宽和被分配到
    声明宽全额（本仓 `distributeColumnWidths` 的契约就是「各列之和恰为 W」），`used` 就多出边框这 1~2px，表格右缘
    越过 `.table-scroll`（`overflow: auto`）的可视区 → **右侧描边被裁，左侧描边照常可见**（症状即「右边 border 不显示」）。
    修法：**列宽预算扣掉表框宽** —— `tableWidth = max(容器宽, n*MIN + 表框)`，分配时传 `tableWidth − 表框`；fixed 布局
    会把差额摊回各列、无留白（实测列宽和 1246 时仍被拉伸到 1248 = 内容宽）。**别把边框挪到滚动容器上**：它是 `flex: 1`
    会撑满 → 卡片高度变成容器高度（偏离设计稿），还牵动 ADR-0024 D4。
  - 通用判据：**只要 `border` 画在 fixed 布局的表格上，就检查 `列宽和 + 边框 ≤ 声明宽`**。**先量再断言，别把注释里的推断当事实。**
- **sticky 表头的圆角裁切**：不能用 `overflow: hidden` 包一层（会杀掉 sticky）。把底色从 `thead` 挪到 `th`，再给首/末 `th` 加圆角，底色才被裁。
- **hover / 选中态背景会把圆角填成直角**：`border-radius` **不裁子元素** —— 卡片下缘两角的 `td` 背景（`--bg-hover`，
  亮色下与 `--border` 同值 `#E7E5E4`）会铺满「圆角弧外的角区」。修：末行首/末 `td` 加
  `border-bottom-{left,right}-radius: calc(var(--radius-sm) - 1px)`（`td` 在 border 内侧 1px，减 1px 才与表格圆角同心）。
  同类场景：tab 高亮、行选中、列表项 hover。
- **行分隔线分级**：卡片外框 `--border`、行分隔线 `--surface-subtle`（浅一档）、末行 `border-bottom: none`（由卡片外框收口）。
- 竖线删净：`th/td` 的 `border-right` 与「末列不画线」规则一起删（别留死规则）。
- **删整个函数/规则块时，`Edit` 的 old_string 必须覆盖整块**——只锚「函数上方那行注释」会把函数体当 new_string 插回去，
  连做两次就变 4 份重复定义（2026-09-23 实证）。改完 `grep -n <符号名>` 复核命中数，再顺带清掉因此变成死代码的
  `import` 与 scoped 样式规则（如删表头图标后要一并删 `.col-header-icon` + 8 个 lucide 导入）。
- 表头若删掉图标，既有测试（断言 `thead svg` 存在）要**改成反向断言**（表头只有字段名），别让测试替设计做决定。
- **夹具的「页面底」要用容器承载，不能只设 `body`**：`main.scss` 的 `_reset.scss` 里有 `body { background: var(--color-paper) }`
  （#FAFAF9），会盖掉夹具 `<style>` 里的 `body` 规则 → 卡片外底色比真机暗 5/255。真机铺满视口的是 app 外壳
  （`_common.scss` 的 `background: var(--bg-base)` = #FFF），故夹具应包一层 `.harness-app { min-height: 100vh; background: var(--bg-base) }`。
- **已知边界（接受，不修）**：`th` 的顶部圆角在表头 sticky 滚离卡片顶部后，会在容器顶端露出 6px 弧缺口
  （实测 `x17..20 / y16..19`，露出 app 白 255 vs 表头灰底 250 → 差 **5/255 ≈ 2%**，显示器上不可辨）。
  修它需要 scroll 监听切 class 或 scroll-driven animation，为零收益引入复杂度，不值。**别为它纠结。**

### 控件类稿（分段控件 / 胶囊组）：基准与浮层（2026-09-23 实证 NamedViewBar）

- **归一化基准换成「轨道高」**：控件稿没有「卡片宽」可比 → `scale = mock_track_h / render_track_h`，左右靠轨道左缘对齐；
  胶囊宽度只在同一基准下比才有意义。
- **明暗双向映射**：轨道 = `--surface-subtle`；胶囊亮色 = `--bg-base`（就是设计稿的纯白），**暗色必须覆写成
  `--bg-active`** —— 暗色 `--bg-base`(#1A1A1E) 比轨道 `--surface-subtle`(#2A2A2E) 更暗，直用读成「凹坑」。
  做法：胶囊色收在轨道选择器的局部变量（`--nvb-thumb`），再 `[data-theme='dark'] .tab-row { --nvb-thumb: … }`
  （scoped 样式给最后一个复合选择器补 `[data-v-x]`，该写法成立；仓内先例 `ConditionGroup.vue`）。
- **字号反推**：CJK 墨迹高 ≈ 0.85em、双字墨迹宽 ≈ 1.7em ⇒ 由墨迹回落原图字号（本次 9px/17px → 10px），
  再按本仓 `--text-xs`(12px) 等比缩放其余几何（本次比例 1.2：轨道 26→30、胶囊 22→26、内边距 9→11）。
- **「宽度合适」的算法**：参考图段内边距 = 0.9em（本次实测 9px @10px 字）⇒ 实现取 `padding: 0 0.9em`。
  若胶囊内必须放 hover 才现的浮层（⋯ / 拖拽 grip），**浮层绝对定位在预留内边距里且盒子宽 ≤ 内边距**：
  否则它的 hover 底色与 `cursor: pointer` 命中区会压到最后一个字（本次 ⋯ 从 14×18 收到 12×16 + `right:1px`，
  胶囊才既保住 46px 又不压字）。**别用「hover 时让胶囊变宽」**——同排兄弟会跟着抖。
- **宿主同缘取证（用户会追问「要不要和 X 对齐」）**：组件自带水平内边距 ×宿主内边距会让控件与卡片不同缘。做法：
  夹具里复刻宿主内边距（`QueryPageFrame: padding: 0 var(--space-8)` = 32px）+ 一张假卡片（`border: 1px solid var(--border)`
  + `radius-sm`）→ 量 `trackX − cardX` 与 `cardRight − toolbarRight`；再用**注入法**在同页注入旧值出 A/B。
  本次结论：`NamedViewBar` 自带 `padding: 0 10px` ⇒ 轨道左缘 +10px、右侧工具栏右缘 −10px（**双侧都不齐**），
  归零后 `trackX = cardX`、`toolbarRight = cardRight` 同时成立 —— 修法是删组件自己的内边距，而不是给某个子元素加负 margin。
- `Edit` 坑：old_string 以换行结尾、new_string 漏掉换行 ⇒ 下一行被拼到同一行（本次两次踩到）；改完**读回复核**。
- Playwright 坑：`page.goto` 后指针停在原位 ⇒ idle 截图前先 `page.mouse.move()` 移开，否则拍到 hover 残留（伪 bug）。

### 改样式把「点击」改坏时：可点性三查（2026-09-23 实证 NamedViewBar「清除/保存无法激活」）

用户报「按钮点不动」时**先只读取证、后动代码**（本次 harness + 真机双环境都复现失败，最终改掉的是三条同形的静默失效通道）：

1. **命中盒是否撑满宿主**：小按钮若按内容取盒（本次 `.action` 仅 28×12，而宿主 tab 高 26px）⇒ 上下各 7px 死区；
   落进死区的点击命中宿主，宿主 handler 若是「选中当前项」这类**幂等早返回**，就表现为完全静默。
   探测法：`elementFromPoint` 沿宿主高度取**上/中/下三点**（单点中测发现不了死区）。
2. **隐形元素是否仍可点**：`opacity: 0` 不改变命中测试，淡入的浮层（⋯）只写 `opacity` 就留下透明抢点盒。
   修法 `pointer-events: none` + **把 `pointer-events: auto` 与 `opacity: 1` 写在同一规则**（本次 `.tab:hover .kebab`）——
   分叉必出「看不见却抢点击」或「看得见点不动」。静态核对：`document.querySelectorAll('style')` 里取该规则 CSSOM 原文。
3. **守卫是否常真**：拖拽/长按守卫若用常真布尔、只靠库回调（Sortable `onEnd`）复位，回调在「指针在窗口外松开 /
   元素被 v-for 替换」下不保证触发 ⇒ 卡住后整个控件点击永久静默且零视觉线索。改「结束时间戳窗」
   （`Date.now() - dragEndedAt < 200`，初值 `0` ⇒ 天然 false、不可能粘死；Sortable 的 onEnd 早于 click 派发，顺序成立）。

- **同权重相邻类**：`.nvb-drag`（胶囊色）与 `.nvb-chosen`（hover 灰）同权重，Sortable 的 fallback 克隆体是
  **源元素深克隆、同时带两类** ⇒ 后写的 `.nvb-chosen` 截胡（浮动块变灰）。改 `&.nvb-chosen:not(.nvb-drag)`。
  另：Sortable 给克隆体写**内联** `opacity: 0.8`，普通声明压不过（要么 `!important`，要么别声明）。
- **测试坑**：**Pinia setup-store 的 action 属性不可直接覆写**（`store.foo = vi.fn()` 静默无效，断言会收到 0 次），
  `$onAction` 在模板事件处理器调用场景也可能收不到 ⇒ 断言**真实效果**（脏标是否被清 / `workingQuery` 是否回退）。
  另 `vi.spyOn(Date,'now')` 会把「从未触发过」的时间戳窗算成常量、干扰判定 ⇒ 时间窗测试用**真时钟 + 真实等待**。

## 第 3 步：夹具 + 截图 + 叠图验证

### 3.1 夹具（`outputs/` 已 gitignore，放这里不脏仓库）

`outputs/<name>-harness.html` + `.ts`，用 **vite dev server 直开真实 SFC**（不要手抄 HTML 复刻 CSS，那就不是验证组件了）：

```html
<style>
  html, body { margin: 0; background: var(--bg-base, #fff); }
  .harness-root { padding: 16px; }
  /* 容器必须是块级且定宽：flex 会让 .table-view 塌成内容宽，列宽退化到下限 */
  .harness-box { width: 1176px; height: 320px; }
</style>
<script type="module" src="/outputs/<name>-harness.ts"></script>
```

```ts
import { createApp, defineComponent, h, markRaw } from 'vue'
import '../src/styles/main.scss'      // 全局 token + reset 是观感的一半，必须引
import { createPinia } from 'pinia'
// 组件 + 自定义单元格（如 SourcePageCell）；store 直接塞数据，别走 wasm/IPC
usePageStore().pages = [{ id: 'p1', title: '产品迭代' }] as unknown as Page[]
app.use(createPinia()); app.mount('#app')
```

- 字段/配置对齐真实消费方（列宽用 `config.columns[].width` 给，例如内容列 720 吸收剩余空间、元数据列 110/80）。
- 首屏 `.table-scroll` 的 `clientWidth` 由 ResizeObserver 现算 → 夹具容器宽度就是「表格宽」。

### 3.2 截图 + 几何取样脚本（`outputs/<name>-shot.mjs`）

```js
import { chromium } from 'playwright'
const page = await browser.newPage({ viewport: { width: 1208, height: 260 } })
page.on('pageerror', e => errors.push(String(e)))   // 夹具报错必须显式收集
await page.goto('http://localhost:5173/outputs/<name>-harness.html', { waitUntil: 'networkidle' })
await page.waitForSelector('.data-table tbody tr'); await page.waitForTimeout(300)  // 等 RO 算完列宽
await page.screenshot({ path: 'outputs/<name>-render.png' })
const geo = await page.evaluate(/* 取 box + getComputedStyle：table/header/dataRow/chip/每列宽/文字色 */)
console.log(JSON.stringify({ errors, geo }, null, 2))
```

**必须后台跑**（`run_in_background` 或 nohup）：前台跑会静默 SIGTERM（本机实证，与 agent-browser CLI 同症状）。
进程跑完不会退出（shell 会一直显示 running，实测挂 20 分钟）——**以 `outputs/*.png` / `*.log` 的 mtime 为准判断完成，不要傻等**；
每轮收尾用 `TaskStop` 把挂着的 shell 清掉（否则越堆越多）。
不要用 agent-browser CLI；用仓库自带 `playwright` / `@playwright/test`。

### 3.3 对齐叠图（`outputs/_<name>-compare.py`）

以目标图的**卡片外框宽**为基准缩放渲染图（`scale = mock_card_w / table.w`），再把渲染图的卡片左上角对到目标图同位置，
上下叠成一张 A/B（中间留 14px 白）。同时打印数值对照：行高/表头高/胶囊尺寸/各列宽 —— 这个表比图更能说服人。

### 3.4 1px 线「看不见」的像素探针（描边 / 分隔线验收）

整表缩略图和「同区域并排」都看不出 1px 差异（2026-09-23 实证：2284px 宽的并排图里根本分不清），必须上探针：

1. **暗线扫描**（`outputs/_tv_edge_probe.py`）：逐行/逐列数「暗像素」，阈值取在 `--border` 与表头灰底之间（`min(p) < 248`，
   因为 jpg 抗锯齿会把 1px 线从 228 淡化到 ~243）；行内**最长连续暗段 > 800** 才算一条线（文字是分散的，段长很小）
   → 直接列出「有哪几条水平线、中点像素值多少」。**某条边完全没被列出，就是描边被后代背景吃掉了。**
2. **聚焦核对**（`outputs/_tv_border_check.py`）：① 左右描边列的**连续段**（正常段长覆盖表头+表体全高；出现 ~30px
   缺口即被表头遮）；② 表格上边缘的**垂直剖面**（只打印发生变化的 y）——正确形状是「描边暗线 `(238,238,236)` →
   紧邻灰底 `(251,251,249)` → 白卡面」；③ 角部 4x `NEAREST` 裁剪目视圆角。
3. **同口径 A/B**：两个状态跑同一脚本、数字并排（例：描边段 180 → 211；上描边剖面从「无」到 `(238,238,236)`）。
   交付图用**角部 4x + 标注框**（红框圈缺口位置、绿框圈修复后同位置），别用整表缩略图。
4. 坐标不必手算：窗口截图有黑边框 + 可能被 `max_width` 缩放，用「在候选区间内搜索连续段最长的列」自适应定位，
   比按 CSS 坐标换算稳（真机实测图/坐标比 ≈ 0.88）。
5. **差异量级用逐像素 diff 报**（角部 10×10 逐点比，`_tv_hover_ab.py`）：例 —— hover 底角修正只改 **13/10 个像素**，
   且形态是圆角抗锯齿过渡带。这种量级要**如实说「收尾级」**，别包装成重大修复；反过来，只有 diff 的**形态**
   （弧带 / 短线 / 缺口）符合预期机制才算验明，光有"数字变了"不算。
6. **角部形态用「字符图」看，比数值表好读**（`_tv_sticky_probe.py`）：按 `min(p)` 三档印成 `W≥253 / m 240..252 / # 更深`，
   每行一个 y —— 一眼就能看出「描边弧（# 从水平线弯到竖直线）」「灰底 250」「卡片外 255」三种结构。
   配套：需要溢出内容时给夹具加 `?rows=N` 造行（30 行 → scrollHeight 1601 / clientH 320），再 `scrollTop=200` 看 sticky 表头。
7. **A/B 首选「注入法」**：同页面、同数据、同视口下用 `execute_js` 改 1~2px 复现旧行为（例：把 `th[0].style.width` +1px
   让 `used` 溢出 1px），比跨版本/跨页面截图对比硬得多 —— 差异只来自那一个变量。配套探针 `outputs/_tv_right_edge.py`：
   **只在目标候选区间逐列扫**（全图垂直扫描会被左侧导航栏淹掉），报每列「最长连续暗段」——修复后 `len=741`（近全高）、
   注入后「无近全高长段」，就是决定性对照。
8. **改了「按容器宽算列宽」这类逻辑，必须单独验下限分支**：本次修复的 `tableWidth = max(容器宽, n*MIN + 表框)` 只在
   容器 < `n*MIN + 表框` 时执行，而真机容器 1250 / 夹具 1176 都远大于它 → **默认路径永远走不到**。做法：夹具上用
   `addStyleTag('.harness-box{width:150px!important;height:auto!important}')` 压窄（ResizeObserver 会自动重算列宽），
   再 `scrollLeft = scrollWidth` 横滚到最右看描边。判据仍是 **`rect.width === inline width`**（列宽和 + 表框 = 声明宽）；
   对照：把 inline width 手动减 2px 模拟「不补偿」→ `rect.width` 立刻变成 inline + 2，精确复现溢出。
   ⚠ 本仓列宽常量：**`MIN_COL_WIDTH = 60`（`tableWidths.ts` 的默认参数 40 只在未传时生效）、`DEFAULT_COL_WIDTH = 160`、
   link 列 40** —— 别按默认参数猜（本次就猜错过一次）。
9. **「浮点层算对」≠「渲染层对」：像素量必须整数化收口，且改动要在规模最大的实例上验证。**
   症状是「右侧描边时有时无」：`colWidths` 运行时浮点和恰为预算 1248 ✅，但渲染层 `Math.round(w)` 逐列取整，
   把 11 列中 10 列的小数（.53 / .71）进位 → 整数和 **1251** → fixed 布局 `used = max(声明宽 1250, 1251 + 表框 2) = 1253`
   → 右缘 3px 出 `.table-scroll` 可视区被裁。**列少时（页面库 6 列）偏差没越界，看起来「已修好」** ⇒ 验证必须挑
   「列数最多 / 基准宽差异最大」的实例（本例 tag 聚合页 11 列），否则会得到假结论。
   - 判据三连：`矩形宽 === inline 声明宽`、`整数列宽和 === 预算`、`容器 scrollWidth === clientWidth`。
   - 修法：在纯函数里整数化（全部 `Math.floor` 后把余量按小数部分从大到小分配 = 最大余数法），**不要在渲染层逐列 round**。
     别用「末列独自吸收余量」—— 列多时会明显偏窄（11 列实测末列 82px vs 其余 85px）。
   - 诊断入口：从 `el.__vueParentComponent` 逐级 `.parent` 找 `setupState` 含 `colWidths` 的组件，直接读
     `containerWidth / tableWidth / colWidths` 的**运行时值**，一次分清「算错」（预算传错）与「画错」（渲染再取整）。
   - 零改动反证仍是首选：注入 `th.style.width`，扫 `和 1251 → used 1253 → 右缘命中容器` vs
     `和 1248 → used 1250 → 右缘命中 table` 这条梯度（`outputs/_tv_right_int_ab.py` 出整表高度窄条 A/B）。
   - **把不变量固化成确定性 fuzz**（定 seed ⇒ 失败可复现）：这类「和 = 容器」的契约，手写用例覆盖不了
     「列数 × 基准宽」的组合空间。参考 `tableWidths.test.ts` 的 2000 组（列数 1–24 × 预算 0–1800 × 基准宽 30–430
     × 下限 40–70，断言「各列整数且 ≥ 下限」「整数和恰为 `max(round(预算), n×下限)`」）。
   - 跨页复核：改完在**列数不同的两个页面**各验一次（本例 6 列页面库 / 11 列聚合页）。`navigate goto` 是 pushState，
     回原位用 `back` —— 顺带白得一次「组件冷启动重挂」验证（比 HMR 态更硬）。若目标页当前是别的视图
     （如 TaskHub 默认看板，页面里没有 `.data-table`），**别为了验证去切视图**（会写用户配置）。

## 第 4 步：回归与交付

1. `npx vitest run <改过的组件>.test.ts` + 受影响目录（`src/components/views`、`src/components/Tags`、`src/composables`）。
2. `npx vue-tsc --noEmit -p tsconfig.app.json`（后台）+ `npx eslint <改动文件>`。
3. `present_files` 交付**对照图**（`outputs/<name>-compare.png`），正文给数值对照表。
4. 报告里必须单列「图中没有但代码里有 / 图看不出但代码需要决定」的歧义项（例：设计稿表头无类型图标、真实页面列宽仍来自 config、外层 `.lib-body` 自带宽框会形成双层卡片），**不要替用户静默决定**。
5. **真机复核（app 在跑时必做；夹具只是忠实复刻）**：`navigate(reload)` 先让新 CSS 进真机（HMR 未必接管样式）
   → 停在目标页（`query_page(mode='state')` 读 url）→ `inspect_element` 断言宿主 `border-top-width: 0px` 与
   组件 `outline: 1px solid rgb(231,229,228)`，并核对**几何自洽**（宿主 x + padding-left == 组件 x；
   宿主 w − 2×padding == 组件 w，顺带证明没有 1px 横向溢出）→ 截图 + PIL 像素扫描定案：
   卡片中线横切面上应只有 **1** 个暗像素，出现 2 个即双层框未消。工具用法见技能 `tauri-mcp-p3gleg`。
6. 命令：`npx vitest run <改过的组件>.test.ts` + 受影响目录；类型检查用项目自带的 `npx vue-tsc -b`。
   **vitest 4 已移除 `--reporter=basic`**（报 `Failed to load custom Reporter from basic`）—— 别当成测试失败。
7. 记忆落 `.workbuddy/memory/YYYY-MM-DD.md`（含取证数值、token 映射、坑、待裁定项）。
