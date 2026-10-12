---
name: comind-ai-image-as-ui-icon
description: 把 AI 生成的位图（miora text_to_image / ImageGen）当作 UI 图标用时的加工链 —— 场景如「把某个按钮的文字/箭头换成贴合风格的图片」。两个必踩的坑：① 生图默认是不透明纯白底（实测 hy-image-3.5-wb 出 PNG colortype 2），直接塞进 ghost/透明按钮会露出一块白方块；② 生图是「细线插画」，描边占比远轻于 UI 图标（实测 6px/352 = 1.7%，而 lucide 的视觉重量 = stroke-width 2 / viewBox 24 = 8.33%），缩到 16–18px 只剩 ~0.3px，会淡成发丝。三步救回：抠透明底（alpha = 1−亮度、按最暗处归一化）→ 形态学膨胀把描边占比重整到 ~8% → 落 src/assets 用 import 引用 + 暗色模式 filter: invert(1)。含无 PIL 时纯 stdlib(zlib+struct) 的 PNG 解码/编码配方。触发词：换成贴合风格的图片、换成图片、用生成的图当图标、AI 图标、按钮图标换成图、图标太细太淡、位图图标、bitmap icon。
agent_created: true
---

# AI 位图 → UI 图标（抠底 + 描边归一 + 暗色适配）

## 何时用

- 用户说「这个按钮/入口（当前是文字或 lucide 图标）我想换成**贴合风格的图片**」。
- 用户选了「AI 生成位图」，而不是内联 SVG。
- 结果要落进一个已有图标体系的界面（这里以 comind 为例：lucide + design token + `html[data-theme]` 暗色）。

> 先如实提醒一次：18–28px 的 UI 图标用位图不如矢量（不能 `currentColor` 染色、暗色要额外处理、放大糊）。用户仍要位图时按下面做，但**务必把「描边重量」和「显示尺寸」对齐设计系统**，否则一定翻车。

## 第 1 步：生图（拿到的多半是不透明白底）

用 miora（`connect_cloud_service` 取 `clientTempToken` → `miora_text_to_image`）。prompt 里写清 `strictly transparent background, single flat ink color #XXXXXX, thin uniform stroke, no fill/shadow/gradient`。

**但别信 transparent**：实测 `hy-image-3.5-wb` 给的是 **PNG colortype 2（RGB，无 alpha），背景纯白 `(255,255,255)`**。所以必须自己抠。

顺手量一下描边：横向扫一条穿过图形的 y，数连续暗像素的 run 宽度 = 描边像素宽。**这个数决定第 3 步要膨胀多少**。

## 第 2 步：抠透明底（alpha = 1 − 亮度）

原理：图是「深墨 on 白」→ 亮度越低越是墨。令 `alpha = (255 − L) * 255 / (255 − Lmin)`（按图内最暗处归一化，保证描边实心不半透），RGB 统一置成单色（**纯黑**最好，暗色可整体反相）。同时按非白像素的 bbox **裁掉多余留白**（否则图标在按钮里显得偏小）。

## 第 3 步：描边重量归一化（栅格图标最容易翻车的一步）

- **基准**：lucide 图标 = `stroke-width 2` on `viewBox 24` → 描边占画布 **8.33%**。comind 相邻图标都是 lucide，位图往这个数靠。
- **症状**：不改的话，6px/352(1.7%) 缩到 18px ≈ **0.31px** → 肉眼像发丝或直接看不见；相邻图标却清晰。这也是「图标太淡」类反馈的根因。
- **修法**：形态学膨胀（最大滤波），圆形/方形结构元半径 `R`，`描边_new = 描边 + 2R`，画布同步 `+2R`。
  `R = (0.083 × 最终画布 − 原描边) / 2`。
  实测：352 画布、描边 6px → R=12 → 描边 30px / 画布 376 = **8.0%**，18px 下 ≈ 1.44px，与 lucide 的 16px(~1.33px) 同级。
  实现用**可分离**最大滤波（先横扫再竖扫，`max(list[a:b])` 走 C 层），`376²` 量级秒级完成；方形结构元在 18px 下与圆盘无差别（细节全被压掉）。
- **别看的误区**：不要盯 10× 原图判重量。必须**面积平均降采样到实际显示尺寸（如 18px）再 ×10 放大**，并在浅底 + 暗底各看一次。10× 下嫌「太厚重」往往在 18px 下正好。

## 第 4 步：落地组件（以 comind Vue SFC 为例）

```vue
<script setup lang="ts">
import tagDetailOpenIcon from '../../assets/tag-detail-open.png'   // 组件在 src/components/<Dir>/ → '../../assets/'
</script>

<template>
  <button type="button" class="tag-detail-open" aria-label="查看成员" title="查看成员" @click="openAggregatePage">
    <img class="tag-detail-open-img" :src="tagDetailOpenIcon" alt="" draggable="false">
  </button>
</template>
```

```scss
.tag-detail-open {                     /* 保留原按钮类名（测试常挂在它上面） */
  &:hover { .tag-detail-open-img { opacity: 1; transform: translateX(2px); } }
}
.tag-detail-open-img {
  width: 18px; height: 18px;
  opacity: 0.65;                       /* 位图不继承 currentColor → 用 opacity 表达「静默 → 悬停提亮」 */
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}
[data-theme='dark'] .tag-detail-open-img { filter: invert(1); }  /* 纯黑墨稿反相成亮线，alpha 保留 */
```

要点：
- 资源放 `src/assets/`，**用 `import` 引用**（`tsconfig.app.json` 的 `types: ["vite/client"]` 提供 `.png` 的模块类型，无需自己写 `declare module`）。仓里没有 `public/`。
- `alt=""`（按钮已有 `aria-label`，图为装饰）+ `draggable="false"`。
- 位图**不能**靠 `color` 染色 → 删掉原来只服务于图标的 `color: var(--text-tertiary)` 之类（会变死代码）。走 `opacity`。
- 暗色：`[data-theme='dark'] .cls { filter: invert(1) }`。**scoped 样式里这个写法有效**（Vue 只把 `data-v-*` 加到最后一个复合选择器上；`[data-theme]` 在 `<html>` 上无需 scope）。本仓先例：`NamedViewBar.vue`。
- 删掉不再使用的 lucide import（`noUnusedLocals` 会报）。

## 第 5 步：验证

```bash
cd "D:/comind"          # ⚠️ 必须小写盘符，否则 vitest 全挂
npx eslint src/components/<Dir>/<File>.vue
npx vitest run src/components/<Dir>/<File>.test.ts
npx vue-tsc -b          # 确认 .png import 的类型能解析
```

## 工具与坑

- 图像处理优先用 **`C:/Users/jay/.workbuddy/binaries/python/envs/imgmeta/Scripts/python.exe`**（**已装 PIL 12.3.0**）。
- ⛔ managed python（`binaries/python/versions/*`）与新建 venv **装不了包**（sandbox 无网络，`pip install Pillow` → `No matching distribution found`）。装不了就退回下面的纯标准库配方。
- 无 PIL 时用 `references/png-alpha-dilate.py`：纯 `zlib`+`struct` 手写 PNG 解码（含 5 种 filter 还原）与 RGBA 编码，并内置「抠 alpha + 膨胀 + 18px 浅暗底预览」全套。本仓已实测跑通。
