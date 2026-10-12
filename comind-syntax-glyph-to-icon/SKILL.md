---
name: comind-syntax-glyph-to-icon
description: 在 comind 把 block content 里的语法字符（inline tag 的 `#`，将来可能 `[[` / `((` / `@`）在渲染态与编辑态一起换成图标时使用。核心判据是「路径 A：字符留在 DOM 文本里，只用 CSS 换视觉」——因为 render-text 的偏移换算依赖「可见长度 ≡ encoded 长度」；换成真 svg（路径 B）必须同步把该段从明文单元改成吸附单元，否则偏移按块静默错位。含渲染态两处产出点、编辑态 Decoration.inline 单字符装饰、mask + currentColor 着色配方（不能用 color: transparent）、图标尺寸定标（**外接高度口径，不是墨迹面积** —— 面积会叠描边粗细、高估观感；`stroke-width` 是零布局代价的提重主杠杆），以及 **inline-block 图标垂直对位的真机参数扫描法**（对位基准不是框底，放大 height 会让中心下沉 H/2），另有 playwright API 与 tauri-mcp 真机验证法。
agent_created: true
---

# comind：语法字符 → 图标（保住偏移不变量）

先例：2026-09-22 inline tag 的 `#` → lucide `hash`（渲染态 + 编辑态一起）。

## 何时用

- 要把 `#tag` 的 `#`、`[[`、`((`、`@` 这类语法字符在界面上换成图标。
- 用户说「用 `<SomeIcon />` 替代字符 X」（注意：渲染态是 `v-html` 的**字符串**，Vue 组件进不去，只能 CSS 或内联 SVG）。

## 第一原则：字符必须留在 DOM 文本里

- `src/services/selection-geometry.ts` 的偏移口径 = `textContent` 累计长度。
- `src/services/render-text.ts` 的 `unitsOf` / `mapInUnits` 靠 `segmentVisibleText(...).length === encodedLen` 判定该单元是「明文单元（逐字对应）」还是「标记单元（整体吸附）」。

⇒ 字符还在 DOM 里（哪怕视觉上透明）→ 该段继续走明文单元 → 选区 / 光标 / 跨块拖拽 / `renderedOffsetToEncodedOffset` 全不受影响。这就是路径 A。
⇒ 真把字符从 DOM 拿掉（输出 `<svg>`）→ 必须同步改 `render-text.ts` 该分支为吸附单元，否则**每个标记之后偏移恒定少 N**，且只在含该标记的块上发作（极难查）。`useContentRenderer.test.ts` 的「同源」用例组是这条不变量的守门人，但 cases 里若没有该段样例就**不会自动报红**，得自己补。

## 落地清单（5 处）

1. **渲染态产出点**（`src/composables/useContentRenderer.ts`，以 tag 为例是两处）：
   - text 段兜底 `TAG_TRIGGER_REGEX.replace(...)` 的模板串；
   - `case 'tag'` 结构化段（Rust `render_segments` 提供）—— 用 `content.slice(...).startsWith('#')` 防御，`#` 单独包一层。
   两处都产出 `<span class="tag-hash">#</span>`；正则导出成 `TAG_TRIGGER_SOURCE` 供编辑态复用（各自 `new RegExp` 建实例，避免 `lastIndex` 互踩）。
2. **编辑态**：新建 `src/extensions/<X>Extension.ts`，`Decoration.inline(pos, pos + 1, { class: 'tag-hash' })` —— **只装饰语法字符那 1 个字符**，标记名保持正文样式。参照 `WikiLinkExtension`（它装饰 `[[` / `]]` 两段 2 字符）。在 `src/components/Editor.vue` 的 `extensions: [...]` 注册。装饰不改文档内容，故光标偏移天然不变。
3. **样式单点**（`src/styles/components/_block.scss`，渲染态 + 编辑态共用）：

   ```scss
   .tag-hash {
     display: inline-block;
     width: 1.12em; height: 1.12em; vertical-align: -0.1875em;   // 见「尺寸定标」与「垂直对位」
     background-color: currentColor;         // 图标颜色跟随上下文（chip 内 = tag 色 / system = 文本次要色 / 编辑态 = 正文色）
     -webkit-text-fill-color: transparent;   // 隐字形；**不能**用 color: transparent
     -webkit-mask-image: $icon-hash; mask-image: $icon-hash;
     -webkit-mask-position: center; mask-position: center;
     -webkit-mask-repeat: no-repeat; mask-repeat: no-repeat;
     -webkit-mask-size: contain; mask-size: contain;
   }
   ```

   图标源用 `$icon-hash: url("data:image/svg+xml,%3Csvg…")`（lucide path，URL 编码 `#`→`%23`、`<`→`%3C`），其中 `stroke-width='2.6'` 是提重的主杠杆（见「尺寸定标」第 2 条）。
4. **测试**：渲染态补「HTML 含新 span」+ `html.replace(/<[^>]*>/g, '')` === 原文（去标签即原文，钉住字符仍在文本里），并把该段样例加进「同源」cases；编辑态仿 `WikiLinkExtension.test.ts`（`Document/Paragraph/Text` + 新扩展，断言 `renderedHTML` 含类名、`element.textContent` 与 `editor.getText()` 不变、无标记时不装饰）。
5. **门禁**：`cd "D:/comind"` → `npx vitest run <改动文件>` → `npx vue-tsc -b`（无输出即过）→ `npx eslint <改动文件>`。

## 尺寸定标：口径用「外接高度」，**不是**「墨迹面积」

**先选对口径 —— 这是本节最贵的一课。** 用户感知的「图标比字符大多少」= **外接高度**（次要是宽度）。canvas 数 `alpha>0` 像素得到的**墨迹面积**会额外叠加描边粗细，拿它汇报会严重高估观感差异。实测教训：`0.98em/sw2` 的面积比字形大 **+60%**，高度却只 **+12%**，用户反馈「跟字符差不多」，并直接质疑那个 60% —— **量化前先问：这个数字对应的是用户能感知的那个维度吗？**

三个指标分开量（真机 Noto Sans SC，canvas 大字号定标）：

| | `#` 字形 | `sw2` 等高时 | `0.98em/sw2` |
|---|---|---|---|
| 墨迹高 | 0.727em | 0.727em | 0.817em |
| 墨迹宽 | 0.564em | 0.727em | 0.817em |
| 墨迹面积 | 100% | **+27%** | +60% |

⇒ **lucide `hash` 的线条本来就比字形粗**（等高时面积已 +27%），所以「描边比字形细、需靠放大补偿」这个假设是**错的**，别照它推尺寸。

1. 量字形墨迹的 em 比率，**大字号定标 + 真机字体栈** —— 小字号被 hinting 像素取整污染；同一个 `#` 在默认回退字体是 0.689em、真机 Noto Sans SC 是 0.727~0.733em，差 6%：

   ```js
   ctx.font = `${220}px ${getComputedStyle(el).fontFamily}`   // 别落到默认字体
   const m = ctx.measureText('#')
   const asc = m.actualBoundingBoxAscent / 220     // 基线上方墨迹高，正数
   const desc = m.actualBoundingBoxDescent / 220   // 基线下方墨迹深，**也是正数**（`#` 实测 ≈0）
   // 墨迹高 = asc + desc；中心在基线上方 = (asc − desc) / 2
   ```

2. **两个独立杠杆，优先用描边**：墨迹面积 ∝ `size² × stroke`。
   - `stroke-width`（lucide 默认 `2`）：**零布局代价** —— 不撑行高、不加宽 chip。取 **`2.6`**，上限约 **`2.8`**（再粗则相邻横线净间隙 <2px，小字号糊成团；1.12em 框下 sw2.6 线宽 1.75px、净隙 2.3px）。
   - `width/height`：**受行高约束但有余量** —— `line-height: 1.4` 已固定行盒高度，只要框高不超出行高的 leading 就不会撑行。实测 `1.12em`（chip 内 16.13px，行高 20.16px）在多行折行时**不撑行**（判定法见下节「行盒边界」）。经验上限约 `1.22em`，再大开始挤压。
3. **阈值（实证）**：外接高度 **+12% 在 14.4px 下不可感知**；要 **+25~35%** 才有「明显比字符重」的观感。本次落值 `1.12em / sw2.6` ⇒ 高度 **+32%**、线宽 1.75px、chip 宽 +3.2px（50.67→53.84）。「等重」约取 `0.88em/sw2`。
4. `#` 字形墨迹中心在基线上方 `(asc − desc)/2`（真机实测 **0.364em**）。图标对位 = 让**框中心**落在这个值上，但推算方式见下一节。

## 垂直对位：`inline-block` 的对位基准不是框底（本次踩过，还写错过一版注释）

`display: inline-block` 且 `overflow: visible` 时，元素**对外呈现的基线是其内部行盒的基线**，不是 margin box 底边。两个反直觉后果：

- 框顶位置**只由 `vertical-align` 决定**；改 `height` 不会顶起框顶，只会让框**向下**延伸。
- ⇒ 放大图标会让框中心**下沉** `Δheight/2`（不是上浮）；要维持原中心，`vertical-align` 得把负值**减小** `Δheight/2`。

真机拟合式（Noto Sans SC）：

```
框中心(基线上方, em) = K + vertical-align − height/2        K ≈ 1.1115
```

`K` 随字体栈与行高上下文变化 ⇒ **别信这个常数**，直接在真机上参数扫描（一次 `execute_js` 拿全，比反复改文件重测快得多）：

```js
const hash = document.querySelector('.tag-hash'), chip = hash.closest('.block-tag')
const fs = parseFloat(getComputedStyle(hash).fontSize)
const measure = () => {                       // 每次重测 probe：改 va 可能带动行盒
  const p = document.createElement('span')
  p.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline'
  chip.appendChild(p); const by = p.getBoundingClientRect().bottom; p.remove()
  const r = hash.getBoundingClientRect()
  return +((by - (r.top + r.height / 2)) / fs).toFixed(4)   // 中心在基线上方
}
for (const em of [-0.45, -0.35, -0.25, -0.15]) { hash.style.verticalAlign = em + 'em'; console.log(em, measure()) }
hash.removeAttribute('style')                 // 扫完必须清 inline style
```

实测斜率恒为 1（`Δ中心 = Δvertical-align`）⇒ 一步到位：`目标 va = 当前 va + (目标中心 − 当前中心)`。

**别用 `vertical-align: middle`** —— 它对齐 x-height/2，会让图标整体偏高。

## 行盒边界：放大了会不会撑行？

`inline-block` 图标参与行盒高度计算 ⇒ 放大到接近行高时，多行折行的段落可能被撑高、行距不均。**判定用「整块高度 A/B」，不要用字符 rect 聚类。**

做法（零副作用：只改运行时样式，不碰数据）：

```js
const el = /* 含 tag 的 .block-text */;
const measure = () => +el.getBoundingClientRect().height.toFixed(2)
el.style.width = '76px'                                   // 强制窄到折成多行
const withIcon = measure()
const hashes = [...el.querySelectorAll('.tag-hash')]
const snaps = hashes.map(h => h.getAttribute('style') || '')
hashes.forEach(h => h.style.cssText =                     // 退化回普通 `#` 字符
  'display:inline;width:auto;height:auto;vertical-align:baseline;' +
  'background:none;-webkit-text-fill-color:currentColor;-webkit-mask-image:none;mask-image:none;')
const asGlyph = measure()                                 // withIcon === asGlyph ⇒ 不撑行
hashes.forEach((h, i) => snaps[i] ? h.setAttribute('style', snaps[i]) : h.removeAttribute('style'))
el.style.width = ''                                       // 复原后复核 dirtyCount === 0
```

2026-09-22 实测：`1.12em` 框（chip 内 16.13px）在 20.16px 行高下，`withIcon === asGlyph === 44.78px` = 2 × 22.39（两行、行距均匀）⇒ **不撑行**。原因是 `line-height: 1.4` 固定了行盒高度，框仍在 leading 范围内。

**踩过的坑**：别用「逐字符 `Range.getBoundingClientRect()` 按 top 聚类成行」算行距 —— `.tag-hash` 是 `inline-block`，其框 `top` 与同行文字 `top` 差 4.69px，超过聚类阈值就被误判成独立一行，算出 24.39px 的**假行距**（真值 22.39）。

## 编译链验证（只用手写等价 CSS 截图不算验过）

`npx vite build` 在本机会被沙箱 safe-delete 守卫拦在 `vite:prepare-out-dir`（`dist/assets` 条目数超阈值 50 → `SAFE_DELETE_BULK_CONFIRM_REQUIRED`），**不是代码问题**（日志里 `3603 modules transformed` 已过）。改用单文件编译核验 data URI 有没有被 sass 破坏：

```bash
npx sass --no-source-map src/styles/components/_block.scss outputs/_block-compiled.css
grep -n -A 14 "\.tag-hash" outputs/_block-compiled.css   # 确认 %3C / %23 / 单引号原样保留
```

**更轻的办法（app 正在 dev 模式跑时）**：直接看运行中 webview 里 HMR 注入的 `<style>`，一次同时验掉「编译产物 + 热更新链路」：

```js
// tauri-mcp execute_js
[...document.querySelectorAll('style')].filter(s => s.textContent.includes('.tag-hash'))[0]
  .textContent.match(/\.tag-hash\s*\{[^}]*\}/)[0]   // 应见 width: 1.12em + 完整 data URI
```

**注意改完 `stroke-width` 后别只 grep 上面这段 `<style>`** —— 项目里还有别的图标也带 `stroke-width='2'` / `'2.5'`，出现目标值也不足以证明是 `.tag-hash` 那条。要读**元素上算出来的**值：

```js
getComputedStyle(document.querySelector('.tag-hash')).maskImage   // → 里面搜 stroke-width='2.6' + 确认是 hash path
```

**真机验证（tauri-mcp，最有说服力）**：`query_page mode=state` 探活 → `$router.push` 导航到含 tag 的页面 → 量 `getComputedStyle` 事实而非看图猜：

- 渲染态：`webkitTextFillColor` 应为 `rgba(0,0,0,0)`，`backgroundColor` 应等于所在 chip 的文本色（暗色主题自动跟随，别写死）。
- 编辑态：点进块后用 `.ProseMirror` 内同类名元素量一次，并核对 `.ProseMirror` 的 `textContent` 仍含该字符（装饰不改文档 = 不变量成立）。**陷阱：`execute_js` 每次调用结束后编辑器会失焦关闭** ⇒ 「点开块 + 布局（放大字号 / 固定定位）+ 测量」必须在**同一次**调用内完成；`take_screenshot` 不会导致关闭，可紧随其后，但中间不要再插 `execute_js`。
- 现成数据可用 `$pinia.state.value.<store>` 直读，**不必靠 UI 造数据**；`take_screenshot` 的 `output_dir` 只接受 temp/home（传项目路径会被拒）。

## 三个坑

- **`color: transparent` 会毁掉一切**：`currentColor` 随之变透明 → `background-color: currentColor` 失效（图标全白/全透明）。改用 `-webkit-text-fill-color`（项目已有 `-webkit-line-clamp`、`-webkit-user-drag` 等先例；Tauri WebView2 / Chromium 全覆盖）。
- **scss 里 mask 别写简写** `mask: url(...) center / contain no-repeat`（`/` 有歧义），一律分离属性。
- **playwright 在本机不可靠，真机优先**：`npx playwright screenshot` CLI 直接 SIGTERM；换成 `outputs/*.mjs` 里 `import { chromium } from '@playwright/test'` 的 API 脚本后，**大尺寸截图仍可能卡死**（2026-09-22 实证：`deviceScaleFactor: 2` + `fullPage: true` 跑了 4m57s 零输出，只能 kill）。⇒ playwright 只用于**手写等价 CSS 的预览页**取图，且必须 `run_in_background` + `> outputs/*.log`；**任务显示「卡住」时先 `ls` 目标文件再 kill** —— 截图常已写盘、只是 `browser.close()` 挂住（2026-09-22 实证：`tag-hash-weight.png` 已落盘 131KB / 1760×1486，脚本却一直 running）；要「真实字体栈 / 真实样式 / 真实几何」的证据**一律走 tauri-mcp 真机**（`execute_js` 读 `getComputedStyle`、`getBoundingClientRect`），它更快、更可信，也不受渲染尺寸影响。

## 判据：编辑态要不要一起做

编辑器里语法字符是**源码文本**（`Editor.vue` 的 `textToHtml` 只做 HTML 转义，tag 无 decode；只有 typed link 才 decode 成中文 label）。只在渲染态换图标会留下「渲染态图标 / 编辑态原字符」的割裂 —— 先问用户，两条路工作量差一倍。另外 `.block-tag` 的点击链路（`useBlockEditorLifecycle.ts` 里 `closest('.block-tag')`）靠类名 / `data-tag-id` 定位，不依赖字符本身，换图标不会破坏它。

两态共用同一个类时，垂直对位的 `K` 只在**行高比例**不同时才会变 —— 本例两态都是 `line-height: 1.4`（chip 内 14.4/20.16、编辑态 16/22.4）⇒ `K` 相同，一次调参两态同时对齐（实测编辑态残差 +0.29px、渲染态 +0.07px）。**改完仍要两态各量一次**，别假设。
