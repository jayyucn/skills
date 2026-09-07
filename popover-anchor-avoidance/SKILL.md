---
name: popover-anchor-avoidance
description: Position a popover/tooltip/menu so it never obscures its anchor, with flip + size-cap, and the scrollHeight trick that avoids a ResizeObserver measurement loop. Use when building or fixing floating panels (dropdowns, command palettes, context menus) in Vue/React/TS.
---

# Popover anchor avoidance (flip + cap)

When a floating panel is anchored to an element and must **not cover the anchor**, naive
"place below, clamp to viewport edge" fails in two cases:

1. **Flip then blind clamp**: flipping to the opposite side when it overflows, then
   `Math.max(top, EDGE_MARGIN)` clamps it back onto the anchor when the panel is taller
   than the space on that side. Symptom users report: "翻转之后还是遮挡调用方" / "it flips but still covers the trigger".
2. **Size-cap feedback loop**: if you cap the panel's `maxHeight` to the available space,
   the element's `offsetHeight` shrinks, a `ResizeObserver` fires, re-measures, drops the
   cap, the element grows back, and you oscillate forever.

## Algorithm (placement = preferred side)

```
order = [preferred, FLIP[preferred]]
fits(side) = inViewport(side) AND not overlap(anchor, side)   // overlap = box intersection
chosen = order.find(fits) ?? bestSideByFreeSpace(order)
if no side 'fits':
    effH = min(naturalH, freeSpaceOn(chosen))   // cap height to available space
    effW = min(naturalW, freeSpaceOn(chosen))   // cap width for left/right too
pos = place(chosen)
clamp pos into viewport using effH/effW (NOT natural ph)
if effH < naturalH: style.maxHeight = effH
if effW < naturalW: style.maxWidth  = effW
```

- `place('bottom') = { left: rect.left, top: rect.bottom + GAP }` (start-align; left/right use `rect.top`).
- `FLIP = { bottom:'top', top:'bottom', left:'right', right:'left' }`.
- "space on side" for top = `rect.top`, bottom = `vh - rect.bottom`, minus `GAP + EDGE_MARGIN`.
- Choosing the side with **more free space** when neither fits keeps the panel as far from the anchor as possible.
- Capping guarantees the panel edge never crosses the anchor edge → never obscures it.

## The ResizeObserver loop fix (critical)

`naturalH` / `naturalW` used for the cap **decision** must come from `scrollHeight` / `scrollWidth`
(the content's real size, which `maxHeight` does NOT shrink), NOT `offsetHeight`.

```ts
function measure() {
  panelW = el.offsetWidth
  panelH = el.offsetHeight
  panelScrollH = el.scrollHeight   // stable under maxHeight cap
  panelScrollW = el.scrollWidth
}
const naturalH = panelScrollH || panelH   // || fallback before first measure
```

Because `naturalH` stays constant after you apply `maxHeight`, `effH` is deterministic → no re-trigger,
no oscillation. `offsetHeight` (panelH) is only used for the *current* raw placement; the final
position is clamped with `effH`, so a one-frame discrepancy self-corrects and converges.

## Placement order in code

1. Trigger: record the anchor element (or a getter that re-resolves it, e.g. for a text cursor
   use `editorView.domAtPos(pos)` → text node's `parentElement`). Keep the legacy `{x,y}` point path
   as a first-frame fallback so there is no flash before measurement.
2. On open: `observe()` (ResizeObserver) + `updateAnchorRect()` + attach `scroll`/`resize` listeners
   so the panel follows the anchor; detach all on close/unmount.
3. `panelStyle` computed reads `anchorRect` + measured sizes and returns fixed `left/top` (+ optional `maxHeight/maxWidth`).

## Test checklist
- preferred side fits → placed there, no cap.
- preferred overflows, flipped fits → flipped, no cap.
- preferred AND flipped both overflow (tall panel, centered anchor) → cap applied (assert `maxHeight`),
  and panel edge does not cross anchor edge (e.g. bottom of panel < anchor.top).
- anchorEl null → no inline positioning (falls back to CSS / legacy point path).
- jsdom note: `offsetWidth/Height` and `scrollHeight` are 0 by default — fake `offsetHeight` for size
  and `scrollHeight` for the cap decision in tests.
