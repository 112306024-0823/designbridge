<script setup>
const props = defineProps({
  candidates:  { type: Array,  default: () => [] },  // [{ style_id, style_name, image_url, similarity, description }]
  confirmed:   { type: Object, default: null },       // 使用者選中的那筆
  loading:     { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'clear'])

function similarityLabel(score) {
  if (score >= 0.85) return '非常符合'
  if (score >= 0.70) return '相當符合'
  if (score >= 0.55) return '部分符合'
  return '參考'
}
</script>

<template>
  <div class="suggestions">
    <div class="header">
      <h2>AI 推薦風格參考</h2>
      <p class="subtitle">根據你的文字描述，找到以下相似風格圖片，選擇一張套用其風格參數</p>
    </div>

    <!-- 骨架載入 -->
    <div v-if="loading" class="grid">
      <div v-for="i in 3" :key="i" class="card skeleton">
        <div class="card-img skeleton-img"></div>
        <div class="card-body">
          <div class="skeleton-line short"></div>
          <div class="skeleton-line"></div>
          <div class="skeleton-line medium"></div>
        </div>
      </div>
    </div>

    <!-- 候選卡片 -->
    <div v-else-if="candidates.length" class="grid">
      <div
        v-for="c in candidates"
        :key="c.image_url"
        class="card"
        :class="{ selected: confirmed?.image_url === c.image_url }"
        @click="emit('confirm', c)"
      >
        <div class="card-img-wrap">
          <img :src="c.image_url" :alt="c.style_name" loading="lazy" @error="$event.target.style.display='none'" />
          <div class="similarity-badge">
            {{ similarityLabel(c.similarity) }}
            <span class="score">{{ (c.similarity * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="confirmed?.image_url === c.image_url" class="selected-overlay">
            <span class="check">✓</span>
          </div>
        </div>
        <div class="card-body">
          <div class="style-name">{{ c.style_name }}</div>
          <p v-if="c.description" class="description">{{ c.description }}</p>
          <p v-else class="description muted">{{ c.style_id }} 風格</p>
          <button
            class="apply-btn"
            :class="{ applied: confirmed?.image_url === c.image_url }"
            @click.stop="confirmed?.image_url === c.image_url ? emit('clear') : emit('confirm', c)"
          >
            {{ confirmed?.image_url === c.image_url ? '✓ 已套用' : '套用此風格' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 已選提示 + 清除 -->
    <div v-if="confirmed" class="confirmed-bar">
      <span>已選：<strong>{{ confirmed.style_name }}</strong></span>
      <button class="clear-btn" @click="emit('clear')">取消套用</button>
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

.header h2 {
  font-size: 1.4rem;
  font-weight: 800;
  color: #3d2b6e;
  margin-bottom: 0.3rem;
}
.subtitle {
  font-size: 0.875rem;
  color: #9880bb;
}

/* Grid */
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}

/* Card */
.card {
  background: rgba(255, 255, 255, 0.8);
  border: 1.5px solid #d4c4ef;
  border-radius: 14px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
}
.card:hover {
  border-color: #9b6dd6;
  box-shadow: 0 8px 24px rgba(124, 92, 191, 0.2);
  transform: translateY(-2px);
}
.card.selected {
  border-color: #7c5cbf;
  box-shadow: 0 0 0 3px rgba(124, 92, 191, 0.25);
}

/* Image */
.card-img-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: #ede6fa;
}
.card-img-wrap img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  transition: transform 0.3s;
}
.card:hover .card-img-wrap img { transform: scale(1.04); }

.similarity-badge {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  background: rgba(0, 0, 0, 0.55);
  color: white;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.2rem 0.55rem;
  border-radius: 99px;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  backdrop-filter: blur(4px);
}
.score {
  background: rgba(255,255,255,0.2);
  padding: 0.05rem 0.35rem;
  border-radius: 99px;
  font-size: 0.68rem;
}

.selected-overlay {
  position: absolute;
  inset: 0;
  background: rgba(124, 92, 191, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
}
.check {
  font-size: 2.5rem;
  color: white;
  text-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

/* Body */
.card-body {
  padding: 0.9rem 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  flex: 1;
}
.style-name {
  font-size: 0.95rem;
  font-weight: 700;
  color: #3d2b6e;
}
.description {
  font-size: 0.78rem;
  color: #6b5494;
  line-height: 1.55;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.description.muted { color: #b0a0cc; }

.apply-btn {
  margin-top: auto;
  padding: 0.5rem 0.75rem;
  border: 1.5px solid #7c5cbf;
  border-radius: 8px;
  background: transparent;
  color: #7c5cbf;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
  text-align: center;
}
.apply-btn:hover { background: #7c5cbf; color: white; }
.apply-btn.applied { background: #7c5cbf; color: white; border-color: #7c5cbf; }

/* Confirmed bar */
.confirmed-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(124, 92, 191, 0.08);
  border: 1px solid #c9b8e8;
  border-radius: 10px;
  padding: 0.65rem 1rem;
  font-size: 0.875rem;
  color: #3d2b6e;
}
.clear-btn {
  background: none;
  border: none;
  color: #9b6dd6;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0;
}
.clear-btn:hover { color: #6b3fa0; }

/* Skeleton */
.skeleton { pointer-events: none; }
.skeleton-img {
  aspect-ratio: 4 / 3;
  background: linear-gradient(90deg, #ede6fa 25%, #e0d4f5 50%, #ede6fa 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skeleton-line {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, #ede6fa 25%, #e0d4f5 50%, #ede6fa 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
.skeleton-line.short  { width: 45%; }
.skeleton-line.medium { width: 70%; }

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
