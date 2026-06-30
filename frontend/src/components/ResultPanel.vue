<script setup>
import { computed, ref } from 'vue'

const refExpanded = ref(true)

const props = defineProps({
  result:  { type: Object,  default: null },
  loading: { type: Boolean, default: false },
})

const spatialLevelColor = computed(() => {
  const level = props.result?.structured_requirement?.spatial_change_level
  if (level === 'major') return 'badge-red'
  if (level === 'minor') return 'badge-orange'
  return 'badge-teal'
})

const styleReferenceImageUrl = computed(() => {
  const result = props.result
  if (!result) return ''

  const fromStyleParams = result.style_params?.reference_image_url
  if (typeof fromStyleParams === 'string' && fromStyleParams.trim()) {
    return fromStyleParams
  }

  const fromControlNet = result.render_result?.controlnet_inputs?.style_reference_image
  if (typeof fromControlNet !== 'string' || !fromControlNet.trim()) {
    return ''
  }

  const normalized = fromControlNet.replace(/\\/g, '/')
  if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
    return normalized
  }
  if (normalized.startsWith('artifacts/')) {
    return `http://localhost:8000/${normalized}`
  }
  return ''
})
</script>

<template>
  <div class="panel">

    <!-- 空狀態 -->
    <div v-if="!result && !loading" class="placeholder">
      <div class="placeholder-inner">
        <div class="placeholder-icon">✦</div>
        <h2>描述你的理想空間</h2>
        <p>在左側輸入需求，AI 會理解你的設計偏好並生成設計方案</p>
        
      </div>
    </div>

    <!-- 載入中 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-ring">
        <div class="loading-spinner"></div>
        <div class="loading-mark">✦</div>
      </div>
      <p class="loading-title">AI 生成中</p>
      <p class="loading-sub">工作流執行中，通常需要 30–60 秒</p>
    </div>

    <!-- 結果 -->
    <div v-if="result" class="result">

      <!-- Header -->
      <div class="result-header">
        <div class="result-title-group">
          <h2>生成結果</h2>
          <div class="badges">
            <span class="badge green">✓ 成功</span>
            <span class="badge gray">{{ result.elapsed_time }}</span>
            <span class="badge purple">{{ result.routing_decision }}</span>
            <span
              v-if="result.structured_requirement?.spatial_change_level"
              :class="['badge', spatialLevelColor]"
            >depth: {{ result.structured_requirement.spatial_change_level }}</span>
          </div>
        </div>
      </div>

      <!-- 2D 平面圖 -->
      <div v-if="result.floor_plan_url" class="card card-floorplan">
        <h3 class="card-title">2D 平面配置圖</h3>
        <img :src="result.floor_plan_url" alt="2D 平面配置圖" class="floor-plan-img" />
      </div>

      <!-- 生成圖 + 風格參考圖 -->
      <div
        v-if="result.generated_image_path || styleReferenceImageUrl"
        :class="['image-row', { 'image-row--ref-collapsed': !refExpanded }]"
      >

        <!-- 生成圖 -->
        <div v-if="result.generated_image_path" class="img-slot img-hero">
          <img
            v-if="result.generated_image_url"
            :src="result.generated_image_url"
            alt="AI 生成設計圖"
            class="img-cover"
          />
          <div class="img-label-bottom">
            <span class="img-path">{{ result.generated_image_path }}</span>
          </div>
        </div>

        <!-- 風格參考圖 -->
        <div
          v-if="styleReferenceImageUrl"
          :class="['img-slot', 'img-ref', { 'img-ref--collapsed': !refExpanded }]"
        >
          <template v-if="refExpanded">
            <img
              :src="styleReferenceImageUrl"
              alt="風格參考圖"
              class="img-cover"
            />
            <div class="img-label-top">
              <span class="img-label-text">風格參考圖</span>
              <button class="collapse-btn" @click="refExpanded = false" title="收合">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
              </button>
            </div>
          </template>
          <div v-else class="collapsed-strip" @click="refExpanded = true" title="展開風格參考圖">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            <span class="strip-text">風格參考圖</span>
          </div>
        </div>

      </div>

      <!-- 結構化需求 -->
      <div v-if="result.structured_requirement" class="card">
        <h3 class="card-title">結構化需求</h3>
        <div class="req-grid">
          <div class="req-item" v-if="result.structured_requirement.meta?.room_type">
            <span class="req-label">房間類型</span>
            <span class="req-value">{{ result.structured_requirement.meta.room_type }}</span>
          </div>
          <div class="req-item" v-if="result.structured_requirement.meta?.design_goal">
            <span class="req-label">設計目標</span>
            <span class="req-value">{{ result.structured_requirement.meta.design_goal }}</span>
          </div>
          <div class="req-item" v-if="result.structured_requirement.style_preferences?.primary_style">
            <span class="req-label">主要風格</span>
            <span class="req-value">{{ result.structured_requirement.style_preferences.primary_style }}</span>
          </div>
          <div class="req-item" v-if="result.structured_requirement.edit_scope?.scope_value !== undefined">
            <span class="req-label">改動幅度</span>
            <span class="req-value">{{ Number(result.structured_requirement.edit_scope.scope_value).toFixed(1) }}</span>
          </div>
        </div>
        <details class="json-details">
          <summary>完整 JSON</summary>
          <pre>{{ JSON.stringify(result.structured_requirement, null, 2) }}</pre>
        </details>
      </div>

      <!-- 風格參數 -->
      <div v-if="result.style_params" class="card card-style">
        <h3 class="card-title">套用風格參數</h3>
        <div class="style-meta">
          <span class="style-badge">{{ result.style_params.style_profile_id || result.style_params.style_id }}</span>
          <span class="style-name">{{ result.style_params.style_profile_name || result.style_params.style_name }}</span>
          <span v-if="result.style_params.style_strength !== undefined" class="style-strength">
            強度 {{ result.style_params.style_strength }}
          </span>
        </div>
        <div v-if="result.style_params.visual_elements?.colors" class="color-swatches">
          <div v-for="(hex, role) in result.style_params.visual_elements.colors" :key="role" class="swatch-item">
            <div class="swatch" :style="{ background: hex }"></div>
            <span class="swatch-label">{{ role }}</span>
            <span class="swatch-hex">{{ hex }}</span>
          </div>
        </div>
        <div v-if="result.style_params.semantic_tags?.length" class="style-tags">
          <span v-for="tag in result.style_params.semantic_tags" :key="tag" class="tag">{{ tag }}</span>
        </div>
        <details class="json-details">
          <summary>完整 style_params JSON</summary>
          <pre>{{ JSON.stringify(result.style_params, null, 2) }}</pre>
        </details>
      </div>
      <div v-else-if="result.render_result?.generation_params?.gemini_style_description" class="card card-style">
        <h3 class="card-title">套用風格參數</h3>
        <div class="style-meta">
          <span class="style-badge">使用者上傳</span>
          <span class="style-name">Gemini 視覺分析</span>
        </div>
        <p class="gemini-desc">{{ result.render_result.generation_params.gemini_style_description }}</p>
      </div>
      <div v-else class="card card-muted">
        <h3 class="card-title">套用風格參數</h3>
        <p class="muted-text">未載入聚合風格檔，將依文字需求與預設 prompt 生成。</p>
      </div>


      <!-- Evaluation Result -->
      <div v-if="result.evaluation_result" class="result-section">
        <h3>Evaluation Result</h3>
        <div class="req-grid">
          <div class="req-item" v-if="result.evaluation_result.decision">
            <span class="req-label">Decision</span>
            <span class="req-value">{{ result.evaluation_result.decision }}</span>
          </div>
          <div class="req-item" v-if="result.evaluation_result.weighted_score !== undefined">
            <span class="req-label">Weighted Score</span>
            <span class="req-value">{{ result.evaluation_result.weighted_score }}</span>
          </div>
        </div>
        <div v-if="result.evaluation_result.feedback" class="eval-feedback">
          {{ result.evaluation_result.feedback }}
        </div>
        <div v-if="Object.keys(result.evaluation_result.scores || {}).length" class="eval-scores">
          <div v-for="(val, key) in result.evaluation_result.scores" :key="key" class="score-row">
            <span class="score-key">{{ key }}</span>
            <span class="score-val">{{ val }}</span>
          </div>
        </div>
        <div v-if="result.evaluation_result.suggestions?.length" class="eval-suggestions">
          <p class="req-label">Suggestions</p>
          <ul>
            <li v-for="(s, i) in result.evaluation_result.suggestions" :key="i">{{ s }}</li>
          </ul>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.panel { flex: 1; display: flex; flex-direction: column; min-width: 0; }

/* ── Placeholder ── */
.placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2rem;
}
.placeholder-inner {
  text-align: center;
  max-width: 480px;
}
.placeholder-icon {
  width: 64px; height: 64px;
  background: linear-gradient(135deg, #f5e8d8, #e8d4b8);
  border-radius: 20px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem; color: var(--primary);
  margin: 0 auto 1.5rem;
  box-shadow: var(--shadow-md);
}
.placeholder-inner h2 {
  font-size: 1.6rem; font-weight: 800; color: var(--text-1);
  letter-spacing: -0.02em; margin-bottom: 0.5rem;
}
.placeholder-inner p { font-size: 0.9rem; color: var(--text-3); margin-bottom: 2rem; }

.example-prompts { text-align: left; }
.example-title { font-size: 0.72rem; font-weight: 600; color: var(--text-4); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.65rem; }
.example-chips { display: flex; flex-direction: column; gap: 0.5rem; }
.chip {
  padding: 0.55rem 0.9rem;
  background: rgba(255,255,255,0.75);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-md);
  font-size: 0.82rem; color: var(--text-2);
  line-height: 1.5;
  backdrop-filter: blur(6px);
}

/* ── Loading ── */
.loading-state {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 1rem;
}
.loading-ring {
  width: 64px; height: 64px; position: relative;
  margin-bottom: 0.5rem;
}
.loading-spinner {
  position: absolute; inset: 0;
  border: 3px solid rgba(180,140,100,0.25);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
.loading-mark {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; color: var(--primary);
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-title { font-size: 1.1rem; font-weight: 700; color: var(--text-1); margin: 0; }
.loading-sub   { font-size: 0.83rem; color: var(--text-3); margin: 0; }

/* ── Result ── */
.result { display: flex; flex-direction: column; gap: 1rem; }

.result-header { margin-bottom: 0.5rem; }
.result-title-group { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; }
.result-title-group h2 { font-size: 1.3rem; font-weight: 800; color: var(--text-1); letter-spacing: -0.02em; }

.badges { display: flex; gap: 0.4rem; flex-wrap: wrap; }
.badge  { padding: 0.2rem 0.65rem; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
.badge.green       { background: #e8f6ee; color: #276749; }
.badge.gray        { background: rgba(255,255,255,0.7); color: #666; border: 1px solid #e5e5e5; }
.badge.purple      { background: var(--primary-light); color: var(--primary); }
.badge.badge-teal  { background: #e0f4f1; color: #1a7a6b; }
.badge.badge-orange{ background: #fff3e0; color: #b45309; }
.badge.badge-red   { background: #fdecea; color: #b91c1c; }

/* ── Image Row ── */
.image-row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  max-width: 100%;
  overflow: hidden;
  position: relative;
}
.image-row--ref-collapsed { padding-right: 52px; }

.img-slot {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  flex-shrink: 0;
  min-width: 0;
}

/* Hero: takes all remaining space */
.img-hero {
  flex: 1;
  min-width: 0;
  overflow: auto;
}

/* Reference: fixed width, transitions on collapse */
.img-ref {
  width: 380px;
  max-width: 48%;
  transition: width 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.img-ref--collapsed {
  width: 44px;
  background: transparent;
  border-radius: 12px;
  overflow: visible;
}

/* Images fill slot with cover */
.img-cover {
  width: 100%;
  height: auto;
  max-width: 100%;
  max-height: 100%;
  display: block;
  object-fit: contain;
}

/* Bottom label — generated image path */
.img-label-bottom {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  padding: 10px 14px;
  background: linear-gradient(transparent, rgba(10, 5, 25, 0.55));
}
.img-path {
  font-size: 0.68rem;
  color: rgba(255, 255, 255, 0.62);
  font-family: monospace;
}

/* Top label — reference title + collapse button */
.img-label-top {
  position: absolute;
  top: 0; left: 0; right: 0;
  padding: 10px 12px;
  background: linear-gradient(rgba(10, 5, 25, 0.48), transparent);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.img-label-text {
  font-size: 0.7rem;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.88);
  letter-spacing: 0.05em;
}
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  background: rgba(255, 255, 255, 0.14);
  border: none;
  border-radius: 7px;
  cursor: pointer;
  color: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(6px);
  transition: background 0.15s;
  flex-shrink: 0;
}
.collapse-btn:hover { background: rgba(255, 255, 255, 0.28); }

/* Collapsed strip */
.collapsed-strip {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  height: 100%;
  width: 44px;
  border-radius: 12px;
  cursor: pointer;
  color: var(--text-4);
  background: rgba(255, 255, 255, 0.42);
  backdrop-filter: blur(8px);
  transition: background 0.15s, color 0.15s;
}
.collapsed-strip:hover {
  background: rgba(255, 255, 255, 0.72);
  color: var(--primary);
}
.strip-text {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.07em;
}

/* Desktop: collapsed strip floats (doesn't take layout width) */
@media (min-width: 769px) {
  .img-ref--collapsed { width: 0; }
  .img-ref--collapsed .collapsed-strip {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
  }
}

/* Responsive */
@media (max-width: 768px) {
  .image-row {
    flex-direction: column;
    height: auto;
    gap: 16px;
    overflow: visible;
  }
  .img-hero  { height: auto; }
  .img-ref   { width: 100%; max-width: 100%; height: auto; }
  .img-ref--collapsed { width: 100%; height: 44px; }
  .collapsed-strip {
    flex-direction: row;
    width: 100%;
    height: 44px;
  }
  .strip-text { writing-mode: unset; }
}

/* Cards */
.card {
  background: rgba(255,250,243,0.82);
  backdrop-filter: blur(8px);
  border: 1px solid #ddd0c0;
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
}
.card-style { border-color: var(--primary-border); }
.card-muted { opacity: 0.6; }

.card-title { font-size: 0.85rem; font-weight: 700; color: var(--text-2); margin-bottom: 0.9rem; letter-spacing: 0.01em; }

/* Requirement grid */
.req-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.65rem; margin-bottom: 0.75rem;
}
.req-item {
  background: var(--primary-light); border-radius: var(--radius-md);
  padding: 0.6rem 0.8rem; display: flex; flex-direction: column; gap: 0.2rem;
}
.req-label { font-size: 0.68rem; color: var(--text-3); font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.req-value { font-size: 0.85rem; color: var(--text-1); font-weight: 600; }

/* Style meta */
.style-meta    { display: flex; align-items: center; gap: 0.55rem; flex-wrap: wrap; margin-bottom: 0.9rem; }
.style-badge   { background: var(--primary); color: white; padding: 0.18rem 0.65rem; border-radius: 99px; font-size: 0.75rem; font-weight: 700; }
.style-name    { font-size: 0.95rem; font-weight: 700; color: var(--text-1); }
.style-strength { background: var(--primary-subtle); color: var(--primary); padding: 0.18rem 0.55rem; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }

.color-swatches { display: flex; gap: 0.65rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
.swatch-item    { display: flex; flex-direction: column; align-items: center; gap: 0.2rem; }
.swatch         { width: 36px; height: 36px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.07); box-shadow: var(--shadow-sm); }
.swatch-label   { font-size: 0.62rem; color: var(--text-3); font-weight: 600; text-transform: capitalize; }
.swatch-hex     { font-size: 0.62rem; color: var(--primary); font-family: monospace; }

.style-tags { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-bottom: 0.75rem; }
.tag { background: var(--primary-light); color: var(--primary); border: 1px solid var(--primary-border); padding: 0.12rem 0.55rem; border-radius: 99px; font-size: 0.72rem; font-weight: 500; }

.muted-text { font-size: 0.875rem; color: var(--text-3); }

.eval-feedback { font-size: 0.875rem; color: #b05520; background: #fff5ee; border: 1px solid #f0c8a0; border-radius: 8px; padding: 0.6rem 0.9rem; margin: 0.5rem 0; line-height: 1.5; }
.eval-scores   { display: flex; flex-direction: column; gap: 0.3rem; margin: 0.5rem 0; }
.score-row     { display: flex; justify-content: space-between; font-size: 0.85rem; padding: 0.25rem 0.5rem; background: var(--primary-light); border-radius: 6px; }
.score-key     { color: #8B5E3C; font-weight: 600; }
.score-val     { color: #5c3d24; font-weight: 700; }
.eval-suggestions ul { margin: 0.3rem 0 0 1.2rem; padding: 0; font-size: 0.85rem; color: #6b4a28; line-height: 1.7; }
.result-section { background: rgba(255,250,243,0.82); border: 1px solid #ddd0c0; border-radius: var(--radius-lg); padding: 1.25rem 1.5rem; }

.gemini-desc {
  font-size: 0.875rem;
  color: var(--text-2);
  line-height: 1.65;
  margin: 0;
}

.card-floorplan { border-color: #c5d8c0; background: rgba(240, 250, 240, 0.82); }
.floor-plan-img {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: var(--radius-md);
  border: 1px solid #c5d8c0;
}


.json-details { margin-top: 0.5rem; }
.json-details summary { cursor: pointer; font-size: 0.78rem; color: var(--primary); font-weight: 600; user-select: none; padding: 0.25rem 0; }
.json-details summary:hover { color: var(--primary-hover); }

pre {
  background: var(--primary-subtle);
  padding: 0.9rem 1rem;
  border-radius: var(--radius-md);
  overflow-x: auto;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--text-2);
  margin-top: 0.5rem;
}
</style>
