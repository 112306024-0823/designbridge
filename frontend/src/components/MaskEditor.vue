<script setup>
import { ref, onMounted } from 'vue'

const props = defineProps({
  imageUrl: { type: String, required: true },
})

const emit = defineEmits(['confirm', 'cancel'])

const imageCanvasRef = ref(null)
const drawCanvasRef  = ref(null)
const brushSize  = ref(30)
const drawMode   = ref('draw')   // 'draw' | 'erase'
const isDrawing  = ref(false)
let imgEl = null

// ── 初始化 ──────────────────────────────────────────────
onMounted(() => {
  imgEl = new Image()
  imgEl.crossOrigin = 'anonymous'
  imgEl.onload = () => {
    const maxW = Math.min(window.innerWidth  * 0.82, 860)
    const maxH = Math.min(window.innerHeight * 0.68, 640)
    const scale = Math.min(maxW / imgEl.naturalWidth, maxH / imgEl.naturalHeight, 1)
    const w = Math.round(imgEl.naturalWidth  * scale)
    const h = Math.round(imgEl.naturalHeight * scale)

    for (const c of [imageCanvasRef.value, drawCanvasRef.value]) {
      c.width  = w
      c.height = h
    }
    imageCanvasRef.value.getContext('2d').drawImage(imgEl, 0, 0, w, h)
  }
  imgEl.src = props.imageUrl
})

// ── 座標 ────────────────────────────────────────────────
function getXY(e) {
  const rect = drawCanvasRef.value.getBoundingClientRect()
  const scaleX = drawCanvasRef.value.width  / rect.width
  const scaleY = drawCanvasRef.value.height / rect.height
  const src = e.touches ? e.touches[0] : e
  return {
    x: (src.clientX - rect.left) * scaleX,
    y: (src.clientY - rect.top)  * scaleY,
  }
}

// ── 畫筆 ────────────────────────────────────────────────
function paint(e) {
  if (!isDrawing.value) return
  const ctx = drawCanvasRef.value.getContext('2d')
  const { x, y } = getXY(e)
  if (drawMode.value === 'erase') {
    ctx.globalCompositeOperation = 'destination-out'
    ctx.fillStyle = 'rgba(0,0,0,1)'
  } else {
    ctx.globalCompositeOperation = 'source-over'
    ctx.fillStyle = 'rgba(255, 60, 60, 0.55)'
  }
  ctx.beginPath()
  ctx.arc(x, y, brushSize.value / 2, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
}

function startDraw(e) { isDrawing.value = true; paint(e) }
function moveDraw(e)  { paint(e) }
function stopDraw()   { isDrawing.value = false }

// ── 清除 ────────────────────────────────────────────────
function clearAll() {
  const ctx = drawCanvasRef.value.getContext('2d')
  ctx.clearRect(0, 0, drawCanvasRef.value.width, drawCanvasRef.value.height)
}

// ── 匯出遮罩並送出 ──────────────────────────────────────
function confirmMask() {
  const draw = drawCanvasRef.value
  const { width: w, height: h } = draw
  const drawCtx = draw.getContext('2d')
  const pixels  = drawCtx.getImageData(0, 0, w, h)

  // 建立黑白遮罩：紅色塗抹區 → 白色；其餘 → 黑色
  const maskCanvas = document.createElement('canvas')
  maskCanvas.width  = w
  maskCanvas.height = h
  const mCtx = maskCanvas.getContext('2d')
  const mData = mCtx.createImageData(w, h)
  for (let i = 0; i < pixels.data.length; i += 4) {
    const marked = pixels.data[i + 3] > 10   // alpha > 10 = 使用者塗的
    mData.data[i]     = marked ? 255 : 0
    mData.data[i + 1] = marked ? 255 : 0
    mData.data[i + 2] = marked ? 255 : 0
    mData.data[i + 3] = 255
  }
  mCtx.putImageData(mData, 0, 0)
  maskCanvas.toBlob(blob => emit('confirm', blob), 'image/png')
}
</script>

<template>
  <div class="overlay" @mousedown.self="$emit('cancel')">
    <div class="modal">

      <!-- Header -->
      <div class="header">
        <span class="title">繪製想修改的區域</span>
        <div class="tools">
          <button :class="['tool-btn', { active: drawMode === 'draw' }]" @click="drawMode = 'draw'">
            畫筆
          </button>
          <button :class="['tool-btn', { active: drawMode === 'erase' }]" @click="drawMode = 'erase'">
            橡皮擦
          </button>
          <label class="brush-label">
            筆刷 {{ brushSize }}px
            <input type="range" v-model.number="brushSize" min="5" max="120" step="5" />
          </label>
          <button class="clear-btn" @click="clearAll">清除</button>
        </div>
      </div>

      <!-- Canvas 區域 -->
      <div class="canvas-wrap">
        <canvas ref="imageCanvasRef" class="image-layer" />
        <canvas
          ref="drawCanvasRef"
          class="draw-layer"
          :style="{ cursor: drawMode === 'erase' ? 'cell' : 'crosshair' }"
          @mousedown="startDraw"
          @mousemove="moveDraw"
          @mouseup="stopDraw"
          @mouseleave="stopDraw"
          @touchstart.prevent="startDraw"
          @touchmove.prevent="moveDraw"
          @touchend="stopDraw"
        />
      </div>

      <p class="hint">用紅色塗抹要修改的區域，再點「確認」</p>

      <!-- Footer -->
      <div class="footer">
        <button class="cancel-btn" @click="$emit('cancel')">取消</button>
        <button class="confirm-btn" @click="confirmMask">確認遮罩</button>
      </div>

    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal {
  background: #fff;
  border-radius: 16px;
  padding: 1.25rem 1.5rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
  max-width: 95vw;
}

/* Header */
.header {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #2d1b5e;
  flex-shrink: 0;
}
.tools {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.tool-btn {
  padding: 0.3rem 0.75rem;
  border: 1.5px solid #c4b0e8;
  border-radius: 8px;
  background: #f5f0ff;
  color: #5c3e9e;
  font-size: 0.8rem;
  font-family: inherit;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s;
}
.tool-btn.active {
  background: #7c5cbf;
  color: #fff;
  border-color: #7c5cbf;
}
.brush-label {
  font-size: 0.78rem;
  color: #5c3e9e;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.brush-label input[type='range'] {
  width: 90px;
  accent-color: #7c5cbf;
  cursor: pointer;
}
.clear-btn {
  padding: 0.3rem 0.65rem;
  border: 1.5px solid #e0b0b0;
  border-radius: 8px;
  background: #fff5f5;
  color: #c0392b;
  font-size: 0.78rem;
  font-family: inherit;
  cursor: pointer;
  font-weight: 600;
}
.clear-btn:hover { background: #fde; }

/* Canvas */
.canvas-wrap {
  position: relative;
  display: inline-block;
  border-radius: 10px;
  overflow: hidden;
  border: 2px solid #ddd4f0;
  line-height: 0;
}
.image-layer,
.draw-layer {
  display: block;
  max-width: 100%;
}
.draw-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

/* Hint */
.hint {
  font-size: 0.75rem;
  color: #8a7aaa;
  margin: 0;
  text-align: center;
}

/* Footer */
.footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.65rem;
}
.cancel-btn {
  padding: 0.55rem 1.2rem;
  border: 1.5px solid #ddd4f0;
  border-radius: 10px;
  background: #f8f5ff;
  color: #7c5cbf;
  font-size: 0.88rem;
  font-family: inherit;
  cursor: pointer;
  font-weight: 600;
}
.confirm-btn {
  padding: 0.55rem 1.4rem;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #7c5cbf 0%, #a06edb 100%);
  color: #fff;
  font-size: 0.88rem;
  font-family: inherit;
  cursor: pointer;
  font-weight: 700;
  box-shadow: 0 4px 14px rgba(124, 92, 191, 0.4);
}
.confirm-btn:hover { opacity: 0.9; }
</style>
