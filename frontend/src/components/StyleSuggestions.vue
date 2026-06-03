<script setup>
import { computed } from 'vue'

const props = defineProps({
  candidates:     { type: Array,   default: () => [] },
  confirmed:      { type: Object,  default: null },
  loading:        { type: Boolean, default: false },
  apiBase:        { type: String,  default: 'http://localhost:8000' },
  styleOptions:   { type: Array,   default: () => [] },
  selectedStyle:  { type: String,  default: 'auto' },
  showRebatch:    { type: Boolean, default: false },
  rebatchLoading: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'clear', 'filter-change', 'rebatch', 'recommend-similar'])

const topCandidates = computed(() => {
  const list = Array.isArray(props.candidates) ? props.candidates : []
  return [...list]
    .filter((c) => c && typeof c.image_url === 'string')
    .sort((a, b) => (Number(b.similarity ?? 0) - Number(a.similarity ?? 0)))
    .slice(0, 6)
})

function similarityLabel(score) {
  if (score >= 0.85) return '非常符合'
  if (score >= 0.70) return '相當符合'
  if (score >= 0.55) return '部分符合'
  return '參考'
}

function normalizeImageUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return ''
  const url = rawUrl.trim()
  if (!url) return ''
  if (url.startsWith('http://') || url.startsWith('https://')) return url
  if (url.startsWith('/')) return `${props.apiBase}${url}`
  return url
}
</script>

<template>
  <div class="suggestions">
    <div class="header">
      <div class="header-title-row">
        <h2>AI 推薦風格參考 <span class="sparkle">✦</span></h2>
        <p class="subtitle">根據你的需求與偏好，挑選以下風格圖片，選一張套用其風格參數</p>
      </div>

      <!-- Filter chips + rebatch action row -->
      <div class="filter-action-row">
        <div v-if="styleOptions.length > 1" class="filter-row">
          <button
            v-for="opt in styleOptions"
            :key="opt.value"
            type="button"
            :class="['filter-chip', { active: selectedStyle === opt.value }]"
            @click="emit('filter-change', opt.value)"
          >{{ opt.value === 'auto' ? '全部風格' : opt.label }}</button>
        </div>
        <button
          v-if="showRebatch && !loading"
          type="button"
          class="rebatch-btn"
          :disabled="rebatchLoading"
          @click="emit('rebatch')"
        >↻ 換一批</button>
      </div>
    </div>

    <!-- 骨架載入 -->
    <div v-if="loading" class="rail">
      <div v-for="i in 5" :key="i" class="card skeleton">
        <div class="card-img skeleton-img"></div>
        <div class="card-body">
          <div class="skeleton-line short"></div>
          <div class="skeleton-line"></div>
          <div class="skeleton-line medium"></div>
        </div>
      </div>
    </div>

    <!-- 無結果 -->
    <div v-else-if="!topCandidates.length" class="empty-state">
      找不到相符的風格參考，請嘗試更換關鍵字或選擇特定風格
    </div>

    <!-- 候選卡片 -->
    <div v-else-if="topCandidates.length" class="rail" role="list" aria-label="風格參考圖候選清單">
      <div
        v-for="c in topCandidates"
        :key="c.image_url"
        class="card"
        :class="{ selected: confirmed?.image_url === c.image_url }"
        role="listitem"
      >
        <div class="card-img-wrap">
          <img :src="normalizeImageUrl(c.image_url)" :alt="c.style_name" loading="lazy" @error="$event.target.style.display='none'" />
          <!-- Applied badge (top-right) -->
          <div v-if="confirmed?.image_url === c.image_url" class="applied-badge">✓ 已套用</div>
        </div>
        <div class="card-body">
          <div class="style-name">{{ c.style_name }}</div>
          <p class="description">{{ c.description || (c.style_id + ' 風格') }}</p>
          <div class="card-actions">
            <button
              type="button"
              class="btn-similar"
              @click="emit('recommend-similar', c)"
            >推薦類似</button>
            <button
              type="button"
              class="btn-apply"
              :class="{ applied: confirmed?.image_url === c.image_url }"
              @click="confirmed?.image_url === c.image_url ? emit('clear') : emit('confirm', c)"
            >{{ confirmed?.image_url === c.image_url ? '✓ 已套用' : '套用風格' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Applied hint bar -->
    <div v-if="confirmed" class="confirmed-bar">
      <span>已選：<strong>{{ confirmed.style_name }}</strong></span>
      <button class="clear-btn" @click="emit('clear')">取消</button>
    </div>
  </div>
</template>

<style scoped>
.suggestions {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
}

.swipe-hint {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  color: #a07850;
}

.header-title-row {
  margin-bottom: 0.75rem;
}
.header h2 {
  font-size: 1.4rem;
  font-weight: 800;
  color: #5c3d24;
  margin-bottom: 0.15rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.sparkle {
  font-size: 0.95rem;
  color: #b07845;
}
.subtitle {
  font-size: 0.875rem;
  color: #a07850;
  margin-bottom: 0.2rem;
}

/* Filter + rebatch row */
.filter-action-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
  padding-top: 0.6rem;
}
.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  flex: 1;
}
.rebatch-btn {
  flex-shrink: 0;
  padding: 0.35rem 0.85rem;
  border-radius: 99px;
  border: 1.5px solid #d4b89a;
  background: rgba(255, 250, 243, 0.9);
  color: #7a5530;
  font-size: 0.82rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s;
  white-space: nowrap;
  align-self: center;
}
.rebatch-btn:hover:not(:disabled) {
  background: var(--btn-gradient);
  border-color: transparent;
  color: #fff;
}
.rebatch-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.filter-chip {
  padding: 0.35rem 0.85rem;
  border-radius: 99px;
  border: 1.5px solid #d4b89a;
  background: rgba(255, 250, 243, 0.9);
  color: #7a5530;
  font-size: 0.82rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s;
  white-space: nowrap;
}
.filter-chip:hover {
  border-color: #b07845;
  background: rgba(255, 245, 230, 0.95);
  color: #5c3d24;
}
.filter-chip.active {
  background: var(--btn-gradient);
  border-color: transparent;
  color: #fff;
  box-shadow: var(--btn-shadow);
}


/* Grid */
.rail {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1.05rem;
  padding: 0.25rem 0.25rem 0.6rem;
}

/* Card */
.card {
  background: #fff;
  border: 1.5px solid #e8d8c4;
  border-radius: 16px;
  overflow: hidden;
  transition: all 0.22s;
  display: flex;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  box-shadow: 0 2px 8px rgba(160, 110, 60, 0.06);
}
.card:hover {
  border-color: #b07845;
  box-shadow: 0 8px 28px rgba(139, 94, 60, 0.16);
  transform: translateY(-3px);
}
.card.selected {
  border-color: #8B5E3C;
  box-shadow: 0 0 0 3px rgba(139, 94, 60, 0.18), 0 6px 20px rgba(139, 94, 60, 0.15);
}

/* Image */
.card-img-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: #f0e4d4;
}
.card-img-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.32s ease;
}
.card:hover .card-img-wrap img { transform: scale(1.05); }

/* Applied badge (top-right corner) */
.applied-badge {
  position: absolute;
  top: 0.55rem;
  right: 0.55rem;
  background: var(--btn-gradient);
  color: #fff;
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.2rem 0.6rem;
  border-radius: 99px;
  backdrop-filter: blur(4px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

/* Body */
.card-body {
  padding: 0.85rem 0.95rem 0.95rem;
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
  flex: 1;
}
.style-name {
  font-size: 0.95rem;
  font-weight: 700;
  color: #3a2010;
}
.description {
  font-size: 0.76rem;
  color: #8a6040;
  line-height: 1.55;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Card action buttons */
.card-actions {
  display: flex;
  gap: 0.45rem;
  margin-top: 0.3rem;
}
.btn-similar {
  flex: 1;
  padding: 0.45rem 0.5rem;
  border: 1.5px solid var(--primary-border);
  border-radius: 8px;
  background: transparent;
  color: var(--primary);
  font-size: 0.76rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s;
  white-space: nowrap;
}
.btn-similar:hover {
  background: var(--primary-subtle);
  border-color: var(--primary);
}
.btn-apply {
  flex: 1;
  padding: 0.45rem 0.5rem;
  border: 1.5px solid var(--primary);
  border-radius: 8px;
  background: transparent;
  color: var(--primary);
  font-size: 0.76rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.16s;
  white-space: nowrap;
}
.btn-apply:hover {
  background: var(--btn-gradient);
  border-color: transparent;
  color: #fff;
}
.btn-apply.applied {
  background: var(--btn-gradient);
  color: #fff;
  border-color: transparent;
  box-shadow: var(--btn-shadow);
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #a07850;
  font-size: 0.9rem;
  background: rgba(255,250,243,0.6);
  border: 1px dashed #d4b89a;
  border-radius: 12px;
}

/* Confirmed bar */
.confirmed-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(139, 94, 60, 0.07);
  border: 1px solid #d4b89a;
  border-radius: 10px;
  padding: 0.6rem 1rem;
  font-size: 0.875rem;
  color: #5c3d24;
}
.clear-btn {
  background: none;
  border: none;
  color: #b07845;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0;
}
.clear-btn:hover { color: #8B5E3C; }

/* Skeleton */
.skeleton { pointer-events: none; }
.skeleton-img {
  aspect-ratio: 4 / 3;
  background: linear-gradient(90deg, #f5e8d8 25%, #e8d4b8 50%, #f5e8d8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, #f5e8d8 25%, #e8d4b8 50%, #f5e8d8 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skeleton-line.short  { width: 45%; }
.skeleton-line.medium { width: 70%; }

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

@media (max-width: 900px) {
  .rail { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 520px) {
  .rail { grid-template-columns: 1fr; }
}
</style>
