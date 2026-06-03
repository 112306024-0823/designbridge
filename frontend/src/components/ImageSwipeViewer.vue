<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  open:         { type: Boolean, default: false },
  slides:       { type: Array,   default: () => [] }, // [{ url, label }]
  initialIndex: { type: Number,  default: 0 },
})

const emit = defineEmits(['close', 'update:open'])

const currentIndex = ref(0)
const dragOffset = ref(0)
const isDragging = ref(false)
const trackRef = ref(null)

let pointerId = null
let startX = 0
let startOffset = 0

const slideCount = computed(() => props.slides.length)

const canSwipe = computed(() => slideCount.value > 1)

watch(
  () => props.open,
  (open) => {
    if (!open) return
    const max = Math.max(0, slideCount.value - 1)
    currentIndex.value = Math.min(Math.max(0, props.initialIndex), max)
    dragOffset.value = 0
    isDragging.value = false
  },
)

watch(
  () => props.initialIndex,
  (idx) => {
    if (!props.open) return
    const max = Math.max(0, slideCount.value - 1)
    currentIndex.value = Math.min(Math.max(0, idx), max)
    dragOffset.value = 0
  },
)

const trackStyle = computed(() => ({
  transform: `translate3d(calc(${-currentIndex.value * 100}% + ${dragOffset.value}px), 0, 0)`,
  transition: isDragging.value ? 'none' : 'transform 0.32s cubic-bezier(0.4, 0, 0.2, 1)',
}))

function closeViewer() {
  emit('update:open', false)
  emit('close')
}

function goTo(index) {
  if (!slideCount.value) return
  const max = slideCount.value - 1
  currentIndex.value = Math.min(Math.max(0, index), max)
  dragOffset.value = 0
}

function goPrev() {
  goTo(currentIndex.value - 1)
}

function goNext() {
  goTo(currentIndex.value + 1)
}

function handleKeydown(e) {
  if (!props.open) return
  if (e.key === 'Escape') {
    e.preventDefault()
    closeViewer()
  } else if (e.key === 'ArrowLeft') {
    goPrev()
  } else if (e.key === 'ArrowRight') {
    goNext()
  }
}

function handlePointerDown(e) {
  if (!canSwipe.value) return
  if (e.button !== undefined && e.button !== 0) return
  pointerId = e.pointerId
  isDragging.value = true
  startX = e.clientX
  startOffset = dragOffset.value
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function handlePointerMove(e) {
  if (!isDragging.value || e.pointerId !== pointerId) return
  const width = trackRef.value?.clientWidth || 1
  let next = startOffset + (e.clientX - startX)
  const min = currentIndex.value >= slideCount.value - 1 ? 0 : -width * 0.35
  const max = currentIndex.value <= 0 ? 0 : width * 0.35
  if (currentIndex.value === 0) next = Math.min(next, max)
  if (currentIndex.value === slideCount.value - 1) next = Math.max(next, min)
  dragOffset.value = next
}

function finishDrag(e) {
  if (!isDragging.value) return
  if (e.pointerId !== undefined && pointerId !== null && e.pointerId !== pointerId) return
  isDragging.value = false
  pointerId = null

  const width = trackRef.value?.clientWidth || 1
  const threshold = width * 0.18
  if (dragOffset.value < -threshold) goNext()
  else if (dragOffset.value > threshold) goPrev()
  dragOffset.value = 0
}

function handleBackdropClick(e) {
  if (e.target === e.currentTarget) closeViewer()
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="viewer-fade">
      <div
        v-if="open && slides.length"
        class="viewer-overlay"
        role="dialog"
        aria-modal="true"
        :aria-label="slides[currentIndex]?.label || '圖片檢視'"
        @click="handleBackdropClick"
      >
        <button type="button" class="viewer-close" aria-label="關閉" @click="closeViewer">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div
          ref="trackRef"
          class="viewer-track-wrap"
          :class="{ 'is-dragging': isDragging }"
          @pointerdown="handlePointerDown"
          @pointermove="handlePointerMove"
          @pointerup="finishDrag"
          @pointercancel="finishDrag"
          @pointerleave="finishDrag"
        >
          <div class="viewer-track" :style="trackStyle">
            <div
              v-for="(slide, i) in slides"
              :key="slide.url + i"
              class="viewer-slide"
            >
              <img :src="slide.url" :alt="slide.label" draggable="false" />
              <p class="viewer-caption">{{ slide.label }}</p>
            </div>
          </div>
        </div>

        <template v-if="canSwipe">
          <button
            v-if="currentIndex > 0"
            type="button"
            class="viewer-nav viewer-nav--prev"
            aria-label="上一張"
            @click.stop="goPrev"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <button
            v-if="currentIndex < slideCount - 1"
            type="button"
            class="viewer-nav viewer-nav--next"
            aria-label="下一張"
            @click.stop="goNext"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>

          <div class="viewer-dots" role="tablist" aria-label="切換圖片">
            <button
              v-for="(slide, i) in slides"
              :key="'dot-' + i"
              type="button"
              role="tab"
              :aria-selected="currentIndex === i"
              :aria-label="slide.label"
              :class="['viewer-dot', { active: currentIndex === i }]"
              @click.stop="goTo(i)"
            />
          </div>

          <p class="viewer-hint">左右拖曳或按方向鍵切換</p>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: rgba(12, 8, 6, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.25rem 4.5rem;
  touch-action: none;
  user-select: none;
}

.viewer-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  z-index: 3;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.18s;
}
.viewer-close:hover {
  background: rgba(255, 255, 255, 0.22);
}

.viewer-track-wrap {
  width: min(96vw, 1200px);
  height: min(78vh, 820px);
  overflow: hidden;
  cursor: grab;
  border-radius: 12px;
}
.viewer-track-wrap.is-dragging {
  cursor: grabbing;
}

.viewer-track {
  display: flex;
  height: 100%;
  width: 100%;
  will-change: transform;
}

.viewer-slide {
  flex: 0 0 100%;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  min-width: 0;
}
.viewer-slide img {
  max-width: 100%;
  max-height: calc(100% - 2rem);
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.45);
  pointer-events: none;
}
.viewer-caption {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
  letter-spacing: 0.04em;
}

.viewer-nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  width: 48px;
  height: 48px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.18s, transform 0.18s;
}
.viewer-nav:hover {
  background: rgba(255, 255, 255, 0.26);
  transform: translateY(-50%) scale(1.05);
}
.viewer-nav--prev { left: max(0.5rem, calc(50% - min(48vw, 600px) - 3rem)); }
.viewer-nav--next { right: max(0.5rem, calc(50% - min(48vw, 600px) - 3rem)); }

.viewer-dots {
  position: absolute;
  bottom: 2.5rem;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 0.5rem;
  z-index: 2;
}
.viewer-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: none;
  padding: 0;
  background: rgba(255, 255, 255, 0.35);
  cursor: pointer;
  transition: transform 0.18s, background 0.18s;
}
.viewer-dot.active {
  background: #fff;
  transform: scale(1.25);
}

.viewer-hint {
  position: absolute;
  bottom: 1rem;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.45);
}

.viewer-fade-enter-active,
.viewer-fade-leave-active {
  transition: opacity 0.22s ease;
}
.viewer-fade-enter-from,
.viewer-fade-leave-to {
  opacity: 0;
}

@media (max-width: 640px) {
  .viewer-nav { display: none; }
  .viewer-overlay { padding: 2.5rem 0.5rem 3.5rem; }
}
</style>
