# HTML 报告格式
架构评审结果将生成为**独立完整的 HTML 文件**，存放于系统临时目录。页面样式基于 CDN 引入 Tailwind，图表使用 CDN 引入 Mermaid。流程图类图表优先使用 Mermaid 绘制；复杂排版视图、截面大图等自定义视觉内容，采用原生区块与内联 SVG 实现。两种方式结合使用，不要全部依赖 Mermaid，避免样式千篇一律。

## 基础页面结构
```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>架构评审 — {{仓库名称}}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });
    </script>
    <style>
      /* 自定义样式：补充 Tailwind 未覆盖的样式
         虚线衔接线、手绘风格箭头等 */
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
    </style>
  </head>
  <body class="bg-stone-50 text-slate-900 font-sans">
    <main class="max-w-5xl mx-auto px-6 py-12 space-y-12">
      <header>...</header>
      <section id="candidates" class="space-y-10">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```

## 页面头部
展示仓库名称、评审日期及简易图例：实心方框 = 模块，虚线 = 衔接点，红色箭头 = 逻辑外溢，深色粗框 = 深度模块。无需额外引言，直接展示待优化项。

## 待优化项卡片
图表为核心内容，文字描述精简直白，统一使用 [LANGUAGE.md](LANGUAGE.md) 中的标准术语。
每个待优化项单独放在一个 `<article>` 标签内，包含以下内容：
- **标题**：简洁描述模块深化方案（例如：整合订单接入流程）。
- **标签栏**：标注推荐优先级（**Strong** 绿色、**Worth exploring** 琥珀色、**Speculative** 灰色），同时标注依赖类型：`in-process`、`local-substitutable`、`ports & adapters`、`mock`。
- **文件列表**：等宽字体展示，样式 `font-mono text-sm`。
- **改造前后图表**：核心区域，分两栏左右对照，参考下文图表样式规范。
- **现存问题**：一句话说明当前痛点。
- **优化方案**：一句话说明调整内容。
- **收益项**：项目符号列表，每项不超过6个词。示例：统一测试入口、阻断定价逻辑外溢、移除4层浅层封装。
- **架构决策提示（可选）**：琥珀色底色单行提示框。

禁止大段文字解释。如果图表需要额外文字才能看懂，重新设计图表。

## 图表样式规范
根据场景选用对应图表样式，可组合搭配，保证视觉多样化。

### Mermaid 流程图（适用于依赖、调用链路）
适合展示“X 调用 Y、Y 调用 Z，链路混乱”这类场景。外层使用 Tailwind 样式卡片包裹，通过 `classDef` 定义样式：外溢链路标红、深度模块加深底色。时序图适合对比调用往返次数（例如：改造前6次请求往返，改造后1次）。
```html
<div class="rounded-lg border border-slate-200 bg-white p-4">
  <pre class="mermaid">
    flowchart LR
      A[OrderHandler] --> B[OrderValidator]
      B --> C[OrderRepo]
      C -.leak.-> D[PricingClient]
      classDef leak stroke:#dc2626,stroke-width:2px;
      class C,D leak
  </pre>
</div>
```

### 自定义区块+箭头（Mermaid 排版受限场景）
使用带边框 `<div>` 表示模块，结合相对定位容器 + 绝对定位内联 SVG 线条/路径绘制箭头。适用于制作**整体深度模块、内部置灰**的效果图，这类视觉效果 Mermaid 无法精准实现。

### 分层截面图（适用于多层浅层结构）
用横向色块（样式 `h-12 border-l-4`）展示调用经过的层级。改造前：多层薄色块，功能冗余；改造后：合并为一个厚色块，标注整合后的职责。

### 界面体量对比图（适用于接口与实现体量相近的浅层模块）
每个模块绘制两个矩形，分别代表**接口**与**实现**。改造前：接口高度接近实现（浅层模块）；改造后：接口收窄、实现区域扩大（深度模块）。

### 调用树合并图
改造前：嵌套区块展示多层函数调用树；改造后：整棵调用树合并为单个区块，原有内部调用在区块内置灰展示。

## 视觉风格要求
- 偏向简约排版风格，不采用企业数据大屏样式，留白充足。标题可选用衬线字体（`font-serif`），搭配浅灰系色调观感更佳。
- 配色克制：主强调色选用翠绿色或靛蓝色，红色标识逻辑外溢，琥珀色标识警示内容。
- 图表高度统一控制在 320 像素左右，保证改造前后两栏可并排展示，无需滚动。
- 图表内模块标签使用 `text-xs uppercase tracking-wider` 样式，突出示意图属性，弱化界面感。
- 页面仅引入 Tailwind 与 Mermaid 两段脚本，整体为静态页面，除 Mermaid 原生渲染功能外，无额外交互逻辑。

## 最优推荐区域
单独使用大号卡片展示，包含方案名称、一句话推荐理由，以及指向对应详情卡片的锚点链接。

## 行文风格
语言通俗精简，严格沿用 [LANGUAGE.md](LANGUAGE.md) 中的架构专业词汇，不得随意替换。

**固定使用词汇**：module、interface、implementation、depth、deep、shallow、seam、adapter、leverage、locality。

**禁止替换词汇**：
禁止用 component、service、unit 替代 module；
禁止用 API、signature 替代 interface；
禁止用 boundary 替代 seam；
禁止用 layer、wrapper 代指 module。

**标准句式示例**
- 订单接入模块为浅层结构，接口体量与实现体量几乎一致。
- 定价逻辑通过衔接点发生外溢。
- 模块深化：统一接口，测试入口唯一。
- 双适配器适配衔接点：生产环境使用 HTTP 适配器，测试环境使用内存适配器。

**收益项描述**：必须使用标准术语撰写，例如：*区域内聚：问题集中在单一模块*、*复用性提升：一套接口适配多处调用*、*接口精简，实现层整合原有封装逻辑*。禁止使用“易于维护”“代码更整洁”等非标准描述。

行文简洁直接，不使用铺垫、委婉表述。单句可转为列表项的一律改为列表，冗余内容直接删减。优先选用标准术语，不自行造词。