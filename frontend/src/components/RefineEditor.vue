<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps({
  imageUrl:   { type: String, required: true },
  loading:    { type: Boolean, default: false },
  error:      { type: String,  default: '' },
})

const emit = defineEmits(['submit', 'cancel'])

// ── Canvas refs ─────────────────────────────────────────
const wrapRef       = ref(null)
const imageCanvasRef = ref(null)
const drawCanvasRef  = ref(null)

// ── Tool state ──────────────────────────────────────────
const brushSize  = ref(32)
const drawMode   = ref('draw')   // 'draw' | 'erase'
const isDrawing  = ref(false)
const textPrompt = ref('')
const hasMask    = ref(false)

let imgEl = null

// ── 初始化 ───────────────────────────────────────────────
function initCanvas() {
  if (!wrapRef.value || !imageCanvasRef.value || !drawCanvasRef.value) return

  imgEl = new Image()
  imgEl.crossOrigin = 'anonymous'
  imgEl.onload = resizeToWrap
  imgEl.src = props.imageUrl
}

function resizeToWrap() {
  if (!imgEl || !wrapRef.value) return
  const { clientWidth: W, clientHeight: H } = wrapRef.value
  const scale = Math.min(W / imgEl.naturalWidth, H / imgEl.naturalHeight, 1)
  const w = Math.round(imgEl.naturalWidth  * scale)
  const h = Math.round(imgEl.naturalHeight * scale)

  for (const c of [imageCanvasRef.value, drawCanvasRef.value]) {
    c.width  = w
    c.height = h
  }
  imageCanvasRef.value.getContext('2d').drawImage(imgEl, 0, 0, w, h)
}

onMounted(initCanvas)
watch(() => props.imageUrl, initCanvas)

// ── 座標換算 ─────────────────────────────────────────────
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

// ── 畫筆 ─────────────────────────────────────────────────
function paintAt(x, y) {
  const ctx = drawCanvasRef.value.getContext('2d')
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
  hasMask.value = true
}

function startDraw(e) {
  isDrawing.value = true
  const { x, y } = getXY(e)
  paintAt(x, y)
}
function moveDraw(e) {
  if (!isDrawing.value) return
  const { x, y } = getXY(e)
  paintAt(x, y)
}
function stopDraw() { isDrawing.value = false }

// ── 清除 ─────────────────────────────────────────────────
function clearMask() {
  const ctx = drawCanvasRef.value.getContext('2d')
  ctx.clearRect(0, 0, drawCanvasRef.value.width, drawCanvasRef.value.height)
  hasMask.value = false
}

// ── 匯出遮罩並送出 ───────────────────────────────────────
function handleSubmit() {
  const draw = drawCanvasRef.value
  const { width: w, height: h } = draw
  const pixels = draw.getContext('2d').getImageData(0, 0, w, h)

  const maskCanvas = document.createElement('canvas')
  maskCanvas.width  = w
  maskCanvas.height = h
  const mCtx  = maskCanvas.getContext('2d')
  const mData = mCtx.createImageData(w, h)
  for (let i = 0; i < pixels.data.length; i += 4) {
    const marked = pixels.data[i + 3] > 10
    mData.data[i]     = marked ? 255 : 0
    mData.data[i + 1] = marked ? 255 : 0
    mData.data[i + 2] = marked ? 255 : 0
    mData.data[i + 3] = 255
  }
  mCtx.putImageData(mData, 0, 0)

  maskCanvas.toBlob(blob => {
    emit('submit', { maskBlob: blob, prompt: textPrompt.value })
  }, 'image/png')
}
</script>

<template>
  <div class="refine-root">

    <!-- ── 上方：圖片畫布 ── -->
    <div class="canvas-wrap" ref="wrapRef">
      <canvas ref="imageCanvasRef" class="layer image-layer" />
      <canvas
        ref="drawCanvasRef"
        class="layer draw-layer"
        :style="{ cursor: drawMode === 'erase' ? 'cell' : 'crosshair' }"
        @mousedown="startDraw"
        @mousemove="moveDraw"
        @mouseup="stopDraw"
        @mouseleave="stopDraw"
        @touchstart.prevent="startDraw"
        @touchmove.prevent="moveDraw"
        @touchend="stopDraw"
      />

      <!-- 返回按鈕 -->
      <button class="back-btn" @click="$emit('cancel')">← 返回</button>

      <!-- 提示文字 -->
      <div class="canvas-hint">用紅色塗抹要修改的區域</div>
    </div>

    <!-- ── 下方：工具列 ── -->
    <div class="toolbar">

      <!-- 左：繪圖工具 -->
      <div class="tool-group">
        <button
          :class="['tool-btn', { active: drawMode === 'draw' }]"
          @click="drawMode = 'draw'"
        >畫筆</button>
        <button
          :class="['tool-btn', { active: drawMode === 'erase' }]"
          @click="drawMode = 'erase'"
        >橡皮擦</button>
        <label class="brush-label">
          <span>{{ brushSize }}px</span>
          <input type="range" v-model.number="brushSize" min="5" max="120" step="5" />
        </label>
        <button class="clear-btn" @click="clearMask">清除</button>
      </div>

      <!-- 中：Prompt -->
      <div class="prompt-group">
        <textarea
          v-model="textPrompt"
          class="prompt-input"
          placeholder="描述要修改的地方，例如：把沙發換成藍色布藝款式"
          rows="2"
        />
      </div>

      <!-- 右：動作 -->
      <div class="action-group">
        <p v-if="error" class="error-msg">{{ error }}</p>
        <button
          class="submit-btn"
          :disabled="loading || !textPrompt.trim()"
          @click="handleSubmit"
        >
          <span v-if="loading" class="spinner" />
          <span v-else>生成微調</span>
        </button>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* ── 整體佈局 ── */
.refine-root {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100vh;
  background: #f4f0fa;
  overflow: hidden;
}

/* ── 上方畫布區 ── */
.canvas-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: #1a0d08;
}

.layer {
  display: block;
  max-width: 100%;
  max-height: 100%;
  border-radius: 8px;
}
.draw-layer {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}
.image-layer {
  position: relative;
}

/* 返回 */
.back-btn {
  position: absolute;
  top: 1rem;
  left: 1rem;
  padding: 0.4rem 0.9rem;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 0.82rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: background 0.15s;
}
.back-btn:hover { background: rgba(255, 255, 255, 0.28); }

/* 提示 */
.canvas-hint {
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.55);
  pointer-events: none;
}

/* ── 下方工具列 ── */
.toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1.25rem;
  background: #fdf6ee;
  border-top: 1.5px solid #e0d4b8;
  box-shadow: 0 -4px 20px rgba(100, 60, 20, 0.08);
  min-height: 88px;
}

/* 左：工具 */
.tool-group {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-shrink: 0;
}

.tool-btn {
  padding: 0.35rem 0.75rem;
  border: 1.5px solid #d4b89a;
  border-radius: 8px;
  background: #f7f0e8;
  color: #5c3d24;
  font-size: 0.8rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tool-btn.active {
  background: #8B5E3C;
  color: #fff;
  border-color: #8B5E3C;
}

.brush-label {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
  font-size: 0.72rem;
  color: #8B5E3C;
  font-weight: 600;
}
.brush-label input[type='range'] {
  width: 80px;
  accent-color: #8B5E3C;
  cursor: pointer;
}

.clear-btn {
  padding: 0.35rem 0.65rem;
  border: 1.5px solid #e0b0b0;
  border-radius: 8px;
  background: #fff5f5;
  color: #c0392b;
  font-size: 0.78rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.clear-btn:hover { background: #fde; }

/* 分隔線 */
.tool-group::after {
  content: '';
  display: block;
  width: 1px;
  height: 40px;
  background: #e0d4b8;
  margin-left: 0.3rem;
}

/* 中：Prompt */
.prompt-group {
  flex: 1;
  min-width: 0;
}
.prompt-input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.55rem 0.85rem;
  border: 1.5px solid #ddd0c0;
  border-radius: 10px;
  font-size: 0.88rem;
  font-family: inherit;
  color: #2c1810;
  background: #fffaf5;
  resize: none;
  outline: none;
  line-height: 1.5;
  transition: border-color 0.15s;
}
.prompt-input:focus { border-color: #8B5E3C; }
.prompt-input::placeholder { color: #c8a882; }

/* 右：動作 */
.action-group {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.4rem;
  flex-shrink: 0;
}

.error-msg {
  font-size: 0.75rem;
  color: #e53935;
  margin: 0;
  max-width: 160px;
  text-align: right;
}

.submit-btn {
  padding: 0.65rem 1.6rem;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #8B5E3C 0%, #b07845 100%);
  color: #fff;
  font-size: 0.9rem;
  font-family: inherit;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(139, 94, 60, 0.4);
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  transition: opacity 0.15s;
}
.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.submit-btn:not(:disabled):hover { opacity: 0.88; }

/* Loading spinner */
.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
