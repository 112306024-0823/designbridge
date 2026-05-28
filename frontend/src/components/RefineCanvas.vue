<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps({
  imageUrl:  { type: String,  required: true },
  brushSize: { type: Number,  default: 32 },
  drawMode:  { type: String,  default: 'draw' }, // 'draw' | 'erase'
})

const wrapRef        = ref(null)
const imageCanvasRef = ref(null)
const drawCanvasRef  = ref(null)
const isDrawing      = ref(false)
let imgEl = null

// ── 初始化 / 圖片更換時重繪 ─────────────────────────────
function initCanvas() {
  if (!imageCanvasRef.value || !drawCanvasRef.value) return
  imgEl = new Image()
  imgEl.crossOrigin = 'anonymous'
  imgEl.onload = () => {
    const wrap = wrapRef.value
    if (!wrap) return
    const { clientWidth: W, clientHeight: H } = wrap
    const scale = Math.min(W / imgEl.naturalWidth, H / imgEl.naturalHeight, 1)
    const w = Math.round(imgEl.naturalWidth  * scale)
    const h = Math.round(imgEl.naturalHeight * scale)
    for (const c of [imageCanvasRef.value, drawCanvasRef.value]) {
      c.width = w; c.height = h
    }
    imageCanvasRef.value.getContext('2d').drawImage(imgEl, 0, 0, w, h)
  }
  imgEl.src = props.imageUrl
}

onMounted(initCanvas)
watch(() => props.imageUrl, initCanvas)

// ── 座標 ──────────────────────────────────────────────────
function getXY(e) {
  const rect = drawCanvasRef.value.getBoundingClientRect()
  const sx = drawCanvasRef.value.width  / rect.width
  const sy = drawCanvasRef.value.height / rect.height
  const src = e.touches ? e.touches[0] : e
  return { x: (src.clientX - rect.left) * sx, y: (src.clientY - rect.top) * sy }
}

// ── 繪圖 ──────────────────────────────────────────────────
function paint(e) {
  if (!isDrawing.value) return
  const ctx = drawCanvasRef.value.getContext('2d')
  const { x, y } = getXY(e)
  if (props.drawMode === 'erase') {
    ctx.globalCompositeOperation = 'destination-out'
    ctx.fillStyle = 'rgba(0,0,0,1)'
  } else {
    ctx.globalCompositeOperation = 'source-over'
    ctx.fillStyle = 'rgba(255, 60, 60, 0.55)'
  }
  ctx.beginPath()
  ctx.arc(x, y, props.brushSize / 2, 0, Math.PI * 2)
  ctx.fill()
  ctx.globalCompositeOperation = 'source-over'
}

function startDraw(e) { isDrawing.value = true; paint(e) }
function moveDraw(e)  { paint(e) }
function stopDraw()   { isDrawing.value = false }

// ── 清除 ──────────────────────────────────────────────────
function clearMask() {
  const ctx = drawCanvasRef.value.getContext('2d')
  ctx.clearRect(0, 0, drawCanvasRef.value.width, drawCanvasRef.value.height)
}

// ── 匯出黑白遮罩 Blob ─────────────────────────────────────
function getMaskBlob() {
  return new Promise(resolve => {
    const draw = drawCanvasRef.value
    const { width: w, height: h } = draw
    const pixels = draw.getContext('2d').getImageData(0, 0, w, h)
    // 沒有塗抹任何區域 → 回傳 null，讓後端改用文字 prompt 判斷
    let hasDrawing = false
    for (let i = 3; i < pixels.data.length; i += 4) {
      if (pixels.data[i] > 10) { hasDrawing = true; break }
    }
    if (!hasDrawing) { resolve(null); return }

    const mc = document.createElement('canvas')
    mc.width = w; mc.height = h
    const mCtx = mc.getContext('2d')
    const mData = mCtx.createImageData(w, h)
    for (let i = 0; i < pixels.data.length; i += 4) {
      const v = pixels.data[i + 3] > 10 ? 255 : 0
      mData.data[i] = mData.data[i+1] = mData.data[i+2] = v
      mData.data[i + 3] = 255
    }
    mCtx.putImageData(mData, 0, 0)
    mc.toBlob(resolve, 'image/png')
  })
}

defineExpose({ getMaskBlob, clearMask })
</script>

<template>
  <div class="canvas-root" ref="wrapRef">
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
    <div class="hint">用紅色塗抹要修改的區域</div>
  </div>
</template>

<style scoped>
.canvas-root {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #1a0d08;
  border-radius: 16px;
  overflow: hidden;
}
.layer { display: block; max-width: 100%; max-height: 100%; }
.draw-layer {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}
.hint {
  position: absolute;
  bottom: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.72rem;
  color: rgba(255,255,255,0.45);
  pointer-events: none;
  white-space: nowrap;
}
</style>
