---
name: comind-dom-geometry-test
description: 在 comind 仓库给「依赖 DOM 布局/选区几何」的模块建 jsdom 回归网——含三类：① selection-geometry 这类几何模块（jsdom 没有 Range.getClientRects）；② BlockList 这类 document 级事件编排层的手势（jsdom 没有 document.elementFromPoint / caretRangeFromPoint）；③ 任何让产品激活块（editorStore.activateBlock ⇒ 真挂 TipTap/ProseMirror）的路径，如撤销/重做落点、方向键跨块导航（jsdom 缺 Range/Node.getBoundingClientRect）。通用手法 = 注入替身 + 把语义编码进假元素/假矩形，让断言落在选中语义而非像素上；症状特征是「用例全绿但 vitest 报 unhandled errors」。当要改动偏移↔Range 映射、高亮矩形计算、坐标↔字符偏移换算、光标落点，或要给 mousemove/mouseup 手势补回归网时使用。
agent_created: true
---

# 给 DOM 几何 / 编排层建 jsdom 回归网

## 何时用

- 要改 `src/services/selection-geometry.ts`（偏移 ↔ DOM Range 双向映射、跨块选区高亮矩形）。
- **要给 BlockList 的 document 级手势补回归网**（mousedown 起点区分、4px 阈值、mousemove 实时重算）——见「变体 B」。
- 任何「结果依赖浏览器布局」的模块：`Range.getClientRects()` / `getBoundingClientRect()` / `elementFromPoint` / `caretRangeFromPoint` 是它的输入。
- 症状是「高亮/矩形算错或整条消失」这类**静默返回空**的 bug —— 光靠真机拖拽很难覆盖全部边界。

## 为什么必须这么做（背景）

`selection-geometry.ts` 长期「不参与 vitest」，注释写着「只在运行时调用」。真因是：

```
jsdom 29 的 Range 原型上根本没有 getClientRects（也没有 getBoundingClientRect）
```

于是 `Array.from(range.getClientRects())` 在 jsdom 里直接抛错，模块天然测不了 → 只能真机验证 → 空行高亮整条消失的 bug 从 #60 一直活到 2026-09-13。**「没布局所以测不了」是伪结论**：被测的不是像素，而是「哪些块被选中、覆盖多少字符、端点怎么归一化」。

## 配方

### 1. 注入替身（不 mock 被测模块）

```ts
const realGetClientRects = Object.getOwnPropertyDescriptor(Range.prototype, 'getClientRects')

beforeEach(() => {
  Object.defineProperty(Range.prototype, 'getClientRects', {
    configurable: true, writable: true,
    value(this: Range) {
      // 把语义编码进假矩形：top = 块序号，left = 覆盖字数
      const node = this.startContainer
      const el = node.nodeType === Node.TEXT_NODE ? node.parentElement : (node as HTMLElement)
      const block = el?.closest('[data-block-id]')
      return [{ top: Number(block?.getAttribute('data-i')), left: this.toString().length, width: 10, height: 10 }]
    },
  })
})

afterEach(() => {
  if (realGetClientRects) Object.defineProperty(Range.prototype, 'getClientRects', realGetClientRects)
  else delete (Range.prototype as { getClientRects?: unknown }).getClientRects
})
```

要点：
- `width`/`height` 必须 > 0 —— 被测模块会过滤零尺寸矩形。
- jsdom **支持** `Range.toString()` / `parentElement` / `closest`，所以「覆盖了多少字」「是哪个块」都能编码。
- 断言写成 `rects.map(r => [r.top, r.left])` 的可读投影，别断言像素。
- 每个测试文件独立环境，替身不会泄漏；仍要在 `afterEach` 还原。

### 2. DOM 夹具照抄真组件形状

别自己发明结构。先读渲染组件（如 `src/components/Block/handlers/bullet/BulletRender.vue`），照抄：

```
<div class="block-list">
  <div data-block-id="b0" data-i="0">
    <div class="block-content"><div class="block-text"><span>abc</span></div></div>
  </div>
```

- **空块 = `<span></span>`**：真机上内容为空且非「全页唯一空块」时**不渲染占位符**，于是块内**没有任何文本节点** —— 这正是多类几何 bug 的根（`firstTextNode`/`lastTextNode` 回 null）。
- `data-i` 这类测试专用属性是必要的：替身要据此回报「哪个块」。

### 3. 补一条「前提断言」，证明回归用例不是空过

写回归用例前先问：**错误实现下它会红吗？** 把触发机制本身钉成断言：

```ts
test('前提：无文本节点的块构造不出 Range —— 旧实现据此 return [] 丢弃整条选区', () => {
  expect(collapsedRangeAtBlockOffset('b0', 1)).not.toBeNull()
  expect(collapsedRangeAtBlockOffset('b1', 0)).toBeNull()   // 空块
})
```

配合「导出被测模块的内部工具函数」即可。这条断言若为红，说明前提判断错了，回归用例也就无从谈起。

### 变体 B：document 编排层的手势（2026-09-14 新增，`#92`）

测的是 `BlockList.vue` 的 `handleDocMouseMove` / `handleDocMouseUp`，不是几何模块本身。**必须真派发 mousedown**
（`.block-content` → 文本拖拽起点 / `.block-properties` → 块选区起点），只调 composable 就测不到「起点区分」。

jsdom 缺 **两个** API（实测 `typeof document.elementFromPoint === 'undefined'`，调用即 TypeError）：

```ts
const ROW_H = 30, CHAR_W = 10, X0 = 0
let rows: HTMLElement[] = []           // 每测试重挂载后登记顶层块元素

Object.defineProperty(document, 'elementFromPoint', {
  configurable: true, writable: true,
  value: (_x: number, y: number) => (y < 0 ? null : rows[Math.floor(y / ROW_H)] ?? null),
})
Object.defineProperty(document, 'caretRangeFromPoint', {
  configurable: true, writable: true,
  value: (x: number, y: number) => {
    const el = y < 0 ? null : rows[Math.floor(y / ROW_H)]
    const text = firstTextNode(el?.querySelector('.block-content'))   // TreeWalker SHOW_TEXT
    if (!text) return null
    const offset = Math.max(0, Math.min(Math.round((x - X0) / CHAR_W), text.length))
    const r = document.createRange(); r.setStart(text, offset); r.setEnd(text, offset); return r
  },
})
```

「行带屏幕模型」：每个顶层块占一条 `ROW_H` 高的行带，**y 定位块、x 定位字符偏移**。`blockOffsetFromPoint`
（`selection-geometry.ts:27`）与块选区拖拽都读 `elementFromPoint`，一个替身同时喂两条路径。

### 变体 C：**激活块**会真挂 TipTap，需要一整套几何替身（2026-09-15 新增，`#109` 落点修订）

任何让产品代码调 `editorStore.activateBlock(id)` 的功能（撤销/重做落点、方向键跨块导航、单击进编辑态）
都会在 jsdom 里**真挂 TipTap**，于是 ProseMirror 的两条坐标链路会撞上 jsdom 的布局缺口。症状是
**测试全绿但 vitest 报「N unhandled errors」**（错误从 PM 内部抛出、逃过断言）——**必须把它们清到 0**，
否则同文件的假绿无从识别。实测三个缺口，缺一个就继续报错：

```ts
// ① 落点激活块 → Block/index.vue focusActiveEditor → Editor 暴露的 focus('end')
//    → tiptap 的 scrollIntoView 命令 → PM scrollToSelection → coordsAtPos → singleRect
// ② singleRect 的 target 是**文本节点包成的 Range**（PM 源码 `textRange(...)`），
//    它先调 getClientRects()，空则回落 getBoundingClientRect() ⇒ Range 两个方法都要给
Object.defineProperty(Range.prototype, 'getClientRects', { configurable: true, writable: true, value: () => [] })
Object.defineProperty(Range.prototype, 'getBoundingClientRect', { configurable: true, writable: true, value: zeroRect })
Object.defineProperty(Node.prototype, 'getBoundingClientRect', { configurable: true, writable: true, value: zeroRect })
// （Node 上的一层只为 Text/Comment —— Element 自己的实现优先，不会被覆盖）
// ③ 若此刻 store 里残留 setClickCoords(...)，focusActiveEditor 会走「点击坐标」分支
//    → Editor.focusAtCoords → PM posAtCoords → document.elementFromPoint（jsdom 未实现）
//    恒 null ⇒ PM 判「坐标不在框内」返回 null ⇒ 回落 focus('end')，语义不变
Object.defineProperty(Document.prototype, 'elementFromPoint', { configurable: true, writable: true, value: () => null })
```

`zeroRect` = 全 0 的 DOMRect 形状（`{x,y,top,left,right,bottom,width,height,toJSON}`）。
**别**用「把 `Element.prototype.scrollIntoView` 也一并桩掉」来回避：产品侧对它有 `typeof` 守卫，
静默跳过 ⇒ 想验「滚的是哪一块」必须**局部**装可观测替身（`vi.fn(function(){ this.getAttribute('data-block-id') })`，
用 `function` 才拿得到 `this`），并在 `finally` 里按 `Object.getOwnPropertyDescriptor` 还原。

### 变体 D：让 jsdom 里的**位置判定**可开关（2026-09-15 新增，同 `#109` 落点修订）

产品里凡有「按 `getBoundingClientRect()` 决定要不要做某事」的分支（如落点「已可见就不滚」），
jsdom 的**全零矩形**会让判据恒为「不可见」——于是只测到「做」的那一侧，门控形同没测。
手法 = **按元素选择性覆写**，其余元素仍回报全零（与不装替身等价，不影响别的路径）：

```ts
let onScreen = true
Object.defineProperty(Element.prototype, 'getBoundingClientRect', {
  configurable: true, writable: true,
  value(this: Element) {
    const top = onScreen ? 100 : window.innerHeight + 50     // jsdom 的 innerHeight = 768
    if (this.getAttribute('data-block-id') !== target) return zeroRect()
    return { top, bottom: top + 37, height: 37, left: 0, right: 720, width: 720, x: 0, y: top, toJSON: () => ({}) } as DOMRect
  },
})
```

两条纪律：① **同一夹具内做对照**（先 `onScreen = true` 断言「不做」，再 `onScreen = false` 断言「做」），
否则「替身坏了导致什么都不发生」也会让用例变绿；② 门控类改动要**同时**断言被门控动作之外的旁证仍在
（本例：不滚，但 `cb-restored` 照旧建立）—— 门控写错会连无关信号一起掐掉。

### 变体 E：用**受控 rAF** 把帧序竞态变成确定的事件次序（2026-09-15 新增，`#115` 落点测量轮次守卫）

产品里凡是「`requestAnimationFrame` 链 + 闭包捕获的输入」的组合（连量 N 帧取最终布局、防抖重排、
滚动后再量），都藏一类**帧序竞态**：上一轮余帧迟到了，拿**旧输入**覆盖本轮结果。真 rAF 一帧 ~16ms，
而测试里两次触发之间隔着 `flushAsync`（若干宏任务），**余帧早跑完了 ⇒ 复现不出、用例假绿**。
手法 = 帧不自动跑，由用例决定「哪一帧在何时执行」：

```ts
const frames: FrameRequestCallback[] = []
const fakeRaf = ((cb: FrameRequestCallback) => frames.push(cb)) as typeof window.requestAnimationFrame
vi.stubGlobal('requestAnimationFrame', fakeRaf)          // 产品侧是 bare 调用 ⇒ 解析到 globalThis
const savedRaf = window.requestAnimationFrame
window.requestAnimationFrame = fakeRaf                    // jsdom 环境里 globalThis !== window，两处都要换
try {
  triggerFirst();  await flushAsync()
  const staleFrame = frames.shift()                       // 扣下**旧轮**那一帧，不让它跑
  triggerSecond(); await flushAsync()
  staleFrame?.(0)                                         // 决定性一步：让旧帧在本轮之后才跑
  await nextTick()                                        // 见下
  expect(...).toEqual(本轮结果)                            // 无守卫 ⇒ 被旧输入覆盖 ⇒ 红
} finally {
  window.requestAnimationFrame = savedRaf
  vi.unstubAllGlobals()
}
```

两个必踩的坑（**都表现为「用例假绿」**，即摘掉守卫后仍全绿）：

1. **只换 `window.requestAnimationFrame` 不够** —— 产品代码写的是 bare `requestAnimationFrame(...)`，
   解析到 **globalThis**，而 vitest jsdom 环境里 globalThis 与 window 不是同一对象 ⇒ 帧照常自动跑，
   旧帧在 `flushAsync` 期间偷偷跑完。必须 `vi.stubGlobal` + 赋值 `window` 两处都换。
2. **执行旧帧后必须 `await nextTick()` 再读 DOM** —— 结果通常落在响应式 ref 渲染出的元素上
   （如 `.restore-flash-rect`），同步读看到的还是上一帧画面 ⇒ 断言不到「旧帧把它改回去了」。

别忘了**牙齿验证**：临时摘掉守卫那一行（脚本改字节 → 跑单条 `-t` → `finally` 还原）确认该例转红；
不红的用例等于没写。

## 踩过的坑

- **挂载 BlockList 后必须 `await nextTick()` 才有块 DOM**：`tree` 在父 `onMounted` 里构建，子列表经
  `defineModel` 接收 → 同步读 `wrapper.element` 拿到空列表（渲染出 `modelvalue=""`，块数 0）。
  症状 = 「屏幕模型未登记块 X」。
- **文本选区一建立就触发高亮 watcher** → `selectionClientRects` 调 `Range.getClientRects`，jsdom 无此方法 →
  **Unhandled Rejection 雪崩**，还会拖累**同文件其它用例**出现「假红」（本次实测红数在 3/4 之间漂移）。
  凡夹具会建立文本选区，即使不验高亮几何，也要补 `Range.prototype.getClientRects = () => []`。
- **`insertBlockAtCursor` 把空 content 视作行尾**（`isEmptyLine`）：`cursorPos=1` 也不走「上方插入」。要测
  「Enter 在选中块上方新建」，被选中的无编辑态块（image）必须用**非空 content**（`![alt](asset://img-1)`）。
- **别用 `Range.compareBoundaryPoints` 判端点先后**：端点块无文本节点时压根构造不出 Range，比较不了 → 必须改用「块在文档序中的位置」判序，同块内退回按字符偏移判序。
- **别让「某个块跳过」升级成「整条丢弃」**：循环内 `continue` 是跳过一格，`function` 顶部 `return []` 是放弃全部；把 null 当作 bail 信号就会出这种 bug。
- **给块加「瞬时类」不能直接改 DOM**（2026-09-15 实证）：`Block/index.vue` 的 `:class` 是**动态绑定**
  （含 `active`），Vue 的 `patchClass` 在绑定值变化时**整体重写 `className`** ⇒ 手加的类会被立刻抹掉；
  且「激活块」（落点必做）与「恢复尾部回写 renderSegments」都会触发这轮 patch。正确做法 =
  `BlockList` 持有 `ref<Set<string>>` 并 `provide`，Block 侧 `inject` 后揉进 `:class`（与既有
  `crossBlockSelection` / `inBlockModal` 同型）；清理用 `setTimeout` + `onBeforeUnmount` 里 `clearTimeout`。
- **「替身必须还原」也适用于 `document` / `Node` 原型**：`beforeAll` 存 `getOwnPropertyDescriptor`、
  `afterAll` 还原或 `delete`；局部替身（如 `scrollIntoView`）在 `try/finally` 内成对。
- **夹具若会让产品激活块，就要预判「真挂编辑器」的连锁**：卸载时 `Editor` 的
  `onBeforeUnmount` 会把内容同步回 store（可能绕过你正在验的机制）——集成网里断言要落在
  **store / DOM 标记 / editorStore 字段**上，别断言「编辑器里看到的文本」。
- **给某层加 `position: relative` 前，别只靠「代码里搜 `position: absolute`」下结论 —— 用矩形差实测**（2026-09-15）：
  加 `position: relative` 会**改掉它所有后代的包含块**，浮层可能集体挪位；但反过来，**包含块变了 ≠ 出问题**
  （相对定位元素不吃包含块，只有百分比偏移才吃）。本仓实测：给 `.block-content` 加 relative 后，块内有 **11 个**
  元素（`.cm-editor`、`.image-block`）的包含块从 `.block` 变成 `.block-content`，而 **362 个后代的矩形差 = 0**
  —— 两者都是 `position: relative`，属假警报。判定配方（真机，不落盘）：
  ① 扫一遍 `.block-content *` 的矩形；② 注入 `.block-content{position:static !important}` 再扫一遍；
  ③ 移除注入**再扫第三遍当噪声基线**（CodeMirror 等会重渲染，不设基线就会把渲染抖动当成效果）；
  ④ `①vs②` 与 `①vs③` 都必须 0 差。
  本仓现成三处「本来就有自己宿主」的浮层（可放心）：`.bullet-chevron` → `.block-bullet`、
  图片浮层（`.image-toolbar` / `.crop-layer` / `.resize-handle` / `.image-flash`）→ `.image-frame`、
  `.editor-placeholder` → `.editor-wrapper`。
- **伪元素宿主迁移要走真机 computed style，别靠截图肉眼判断**：`getComputedStyle(el, '::after')` 读
  `content` / `animationName` / `animationDuration` / `backgroundColor` / `zIndex`，并顺带核旧宿主
  （如 `.block::after`）的 `content` 已成 `none` —— 这才证明宿主真的迁走了。要看**冻结的那一帧**
  （截图耗时 > 动画时长）就临时注入 `animation:none !important;opacity:1 !important`，截完立即移除。
- 每次改完仍要跑真机/全量对照既有失败基线（2026-09-15 实测 19 文件 / 54 例红；2026-09-14 曾测 22 文件 / 60 例红，**红数会漂移**，只看「有没有新增」，并用「失败文件是否 import 了我改的组件」做三段比对）。

## 已落地先例

- `src/services/selection-geometry.test.ts`（2026-09-13，提交 `24f9b92`）：无文本节点块（空行/图片）跳过而不弃整条选区；端点判序改按文档序位置。ADR-0035 D9。
- `src/components/BlockList.selection-orchestration.test.ts`（2026-09-14，提交 `d2f9a76` + `cb6038e`，23 例）：变体 B 的首例
  ——手势（4px 阈值、内容区 vs 属性区起点）、按键分发、粘贴分发、编排豁免门。issue #92。
- `src/components/BlockList.undo-redo.test.ts`（2026-09-15）：变体 C + D + E 的首例 —— G 组 8 例验撤销/重做落点
  （不进块选区、`cb-restored` 建立与到期摘除、光标落文档序最后一块、已可见不滚 / 掉出视口才滚、光标落行尾，
  以及「连发撤销时过期测量帧作废」——变体 E 首例，提交 `4a0accb`）。
  撤销/重做落点由「块选区持久高亮」改为「内容区一次闪烁（600ms）+ 光标 + 可见性门控滚动」，见该文件头部的替身清单。
