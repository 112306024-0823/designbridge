<script setup>
import { ref, computed } from 'vue'

/**
 * Interactive 2D layout editor. Furniture are draggable / resizable / rotatable
 * boxes positioned with normalized [0,1] coordinates inside a square room, matching
 * the coordinate system used by the backend (x=left→right, y=back→front).
 */
const props = defineProps({
  placements: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:placements'])

// type → { label(zh), default size, floor layer? }
const CATALOG = {
  sofa:         { label: '沙發',   w: 0.30, h: 0.13 },
  armchair:     { label: '扶手椅', w: 0.12, h: 0.12 },
  chair:        { label: '椅子',   w: 0.08, h: 0.08 },
  coffee_table: { label: '茶几',   w: 0.15, h: 0.10 },
  side_table:   { label: '邊几',   w: 0.08, h: 0.08 },
  dining_table: { label: '餐桌',   w: 0.24, h: 0.18 },
  desk:         { label: '書桌',   w: 0.20, h: 0.10 },
  tv_unit:      { label: '電視櫃', w: 0.22, h: 0.07 },
  bed:          { label: '床',     w: 0.30, h: 0.40 },
  nightstand:   { label: '床頭櫃', w: 0.08, h: 0.08 },
  wardrobe:     { label: '衣櫃',   w: 0.20, h: 0.10 },
  bookshelf:    { label: '書櫃',   w: 0.18, h: 0.08 },
  cabinet:      { label: '櫃子',   w: 0.15, h: 0.08 },
  plant:        { label: '盆栽',   w: 0.06, h: 0.06 },
  lamp:         { label: '立燈',   w: 0.05, h: 0.05 },
  rug:          { label: '地毯',   w: 0.38, h: 0.24, floor: true },
}
const FLOOR_TYPES = new Set(['rug', 'carpet'])
const isFloor = (t) => FLOOR_TYPES.has(t)
const labelOf = (t) => (CATALOG[t]?.label) || t.replace(/_/g, ' ')
const SNAP = 0.03           // wall-snap threshold (normalized)
const MIN = 0.04            // min box size

const boardRef = ref(null)
const selectedId = ref(null)
let drag = null             // active drag/resize state

// Local editable copy that syncs up on every change.
const items = computed(() => props.placements)

function commit(next) {
  emit('update:placements', next)
}

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)) }

function boardSize() {
  const el = boardRef.value
  return el ? Math.min(el.clientWidth, el.clientHeight) : 1
}

// ── Pointer handlers ────────────────────────────────────────────
function onDown(e, item, mode) {
  e.preventDefault()
  e.stopPropagation()
  selectedId.value = item.id
  drag = {
    id: item.id, mode,
    startX: e.clientX, startY: e.clientY,
    ox: item.x, oy: item.y, ow: item.w, oh: item.h,
    size: boardSize(),
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

function onMove(e) {
  if (!drag) return
  const dx = (e.clientX - drag.startX) / drag.size
  const dy = (e.clientY - drag.startY) / drag.size
  const next = items.value.map((it) => {
    if (it.id !== drag.id) return it
    if (drag.mode === 'move') {
      return { ...it, x: clamp(drag.ox + dx, 0, 1 - it.w), y: clamp(drag.oy + dy, 0, 1 - it.h) }
    }
    // resize from bottom-right corner
    const w = clamp(drag.ow + dx, MIN, 1 - drag.ox)
    const h = clamp(drag.oh + dy, MIN, 1 - drag.oy)
    return { ...it, w, h }
  })
  commit(next)
}

function onUp() {
  // wall snap on release (move only)
  if (drag && drag.mode === 'move') {
    const next = items.value.map((it) => {
      if (it.id !== drag.id) return it
      let { x, y, w, h } = it
      if (x < SNAP) x = 0
      if (x + w > 1 - SNAP) x = 1 - w
      if (y < SNAP) y = 0
      if (y + h > 1 - SNAP) y = 1 - h
      return { ...it, x, y }
    })
    commit(next)
  }
  drag = null
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
}

// ── Item ops ────────────────────────────────────────────────────
function rotate90(item) {
  // swap footprint w/h (keeps centre), and record rotation for the renderer
  const cx = item.x + item.w / 2
  const cy = item.y + item.h / 2
  const w = item.h, h = item.w
  const next = items.value.map((it) => it.id === item.id ? {
    ...it, w, h,
    x: clamp(cx - w / 2, 0, 1 - w),
    y: clamp(cy - h / 2, 0, 1 - h),
    rotation: ((it.rotation || 0) + 90) % 360,
  } : it)
  commit(next)
}

function removeItem(item) {
  commit(items.value.filter((it) => it.id !== item.id))
  if (selectedId.value === item.id) selectedId.value = null
}

function addItem(type) {
  const spec = CATALOG[type]
  const id = `${type}_${Date.now().toString(36)}`
  const w = spec.w, h = spec.h
  const item = { id, type, w, h, x: clamp(0.5 - w / 2, 0, 1 - w), y: clamp(0.5 - h / 2, 0, 1 - h), rotation: 0 }
  commit([...items.value, item])
  selectedId.value = id
}

const addOpen = ref(false)
const catalogList = computed(() => Object.entries(CATALOG).map(([type, s]) => ({ type, label: s.label })))

function pct(v) { return `${v * 100}%` }
</script>

<template>
  <div class="editor">
    <div class="toolbar">
      <div class="add-wrap">
        <button class="tool-btn primary" @click="addOpen = !addOpen">＋ 新增家具</button>
        <div v-if="addOpen" class="add-menu" @mouseleave="addOpen = false">
          <button v-for="c in catalogList" :key="c.type" class="add-item"
                  @click="addItem(c.type); addOpen = false">{{ c.label }}</button>
        </div>
      </div>
      <span class="hint">拖動移動 · 右下角縮放 · ⟳ 旋轉 · 選取後可刪除 · 靠牆自動吸附</span>
    </div>

    <div ref="boardRef" class="board" @pointerdown="selectedId = null">
      <!-- grid -->
      <div class="grid"></div>
      <!-- door / window markers -->
      <div class="door" title="門"></div>
      <div class="window" title="窗"></div>

      <div
        v-for="item in items"
        :key="item.id"
        class="node"
        :class="{ floor: isFloor(item.type), selected: selectedId === item.id }"
        :style="{ left: pct(item.x), top: pct(item.y), width: pct(item.w), height: pct(item.h) }"
        @pointerdown="onDown($event, item, 'move')"
      >
        <span class="node-label">{{ labelOf(item.type) }}</span>

        <template v-if="selectedId === item.id">
          <button class="node-btn rotate" title="旋轉 90°"
                  @pointerdown.stop @click.stop="rotate90(item)">⟳</button>
          <button class="node-btn del" title="刪除"
                  @pointerdown.stop @click.stop="removeItem(item)">✕</button>
          <div class="handle" @pointerdown="onDown($event, item, 'resize')"></div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.editor { display: flex; flex-direction: column; gap: 0.6rem; width: 100%; }

.toolbar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.add-wrap { position: relative; }
.tool-btn {
  border: 1.5px solid #d8c3a5; background: #fff8ef; color: #6b4f30;
  border-radius: 8px; padding: 0.4rem 0.85rem; font-size: 0.82rem;
  font-family: inherit; font-weight: 700; cursor: pointer; transition: all 0.15s;
}
.tool-btn.primary { background: #8B5E3C; color: #fff; border-color: #8B5E3C; }
.tool-btn:hover { filter: brightness(1.05); }
.hint { font-size: 0.74rem; color: #a08a6f; }

.add-menu {
  position: absolute; top: 110%; left: 0; z-index: 20;
  background: #fff; border: 1px solid #e2d4bf; border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.14); padding: 0.35rem;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.25rem; width: 260px;
}
.add-item {
  border: none; background: #f7efe3; border-radius: 7px; padding: 0.45rem 0.3rem;
  font-size: 0.78rem; font-family: inherit; color: #5c4630; cursor: pointer;
}
.add-item:hover { background: #ecdcc4; }

.board {
  position: relative; width: 100%; max-width: 560px; aspect-ratio: 1 / 1;
  margin: 0 auto; background: #fbf6ee;
  border: 3px solid #2b2b2b; border-radius: 4px; overflow: hidden;
  box-shadow: 0 4px 24px rgba(0,0,0,0.12); touch-action: none;
}
.grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(to right, rgba(120,90,60,0.08) 1px, transparent 1px),
    linear-gradient(to bottom, rgba(120,90,60,0.08) 1px, transparent 1px);
  background-size: 20% 20%;
}
.door {
  position: absolute; bottom: -3px; left: 45%; width: 10%; height: 6px;
  background: #fbf6ee; border-bottom: 3px solid #bfae95;
}
.window {
  position: absolute; top: -3px; left: 40%; width: 20%; height: 6px;
  background: #c0daf8; border: 1.5px solid #2e6ab5;
}

.node {
  position: absolute; box-sizing: border-box;
  border: 1.5px solid #7a5c3a; background: rgba(180,140,100,0.32);
  border-radius: 3px; cursor: grab; display: flex; align-items: center; justify-content: center;
  user-select: none; transition: box-shadow 0.12s;
}
.node:active { cursor: grabbing; }
.node.floor { background: rgba(160,160,160,0.20); border: 1.5px dashed #999; z-index: 0; }
.node.selected { box-shadow: 0 0 0 2px #8B5E3C, 0 3px 12px rgba(0,0,0,0.2); z-index: 5; }
.node-label {
  font-size: 0.68rem; font-weight: 700; color: #4a3620; pointer-events: none;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 2px;
}

.node-btn {
  position: absolute; width: 18px; height: 18px; border-radius: 50%;
  border: none; color: #fff; font-size: 0.7rem; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center; padding: 0;
}
.node-btn.del { top: -9px; right: -9px; background: #c0392b; }
.node-btn.rotate { top: -9px; left: -9px; background: #6b4f30; }
.handle {
  position: absolute; right: -6px; bottom: -6px; width: 13px; height: 13px;
  background: #8B5E3C; border: 2px solid #fff; border-radius: 3px;
  cursor: nwse-resize;
}
</style>
