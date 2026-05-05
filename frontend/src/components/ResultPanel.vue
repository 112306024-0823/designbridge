<script setup>
defineProps({
  result:  { type: Object,  default: null },
  loading: { type: Boolean, default: false },
})
defineEmits(['refine'])
</script>

<template>
  <div class="panel">

    <!-- 空狀態 -->
    <div v-if="!result && !loading" class="placeholder">
      <div class="placeholder-icon">✏️</div>
      <h2>輸入設計需求</h2>
      <p>在左側填寫需求後，點擊執行工作流</p>
    </div>

    <!-- 載入中 -->
    <div v-if="loading" class="loading-state">
      <div class="loading-spinner"></div>
      <p>工作流執行中，請稍候...</p>
    </div>

    <!-- 結果 -->
    <div v-if="result" class="result">
      <div class="result-header">
        <h2>執行結果</h2>
        <div class="badges">
          <span class="badge green">✓ 成功</span>
          <span class="badge gray">⏱ {{ result.elapsed_time }}</span>
          <span class="badge blue">{{ result.routing_decision }}</span>
        </div>
      </div>

      <!-- 生成圖 -->
      <div v-if="result.generated_image_path" class="result-section">
        <h3>🖼 生成圖</h3>
        <img
          v-if="result.generated_image_url"
          :src="result.generated_image_url"
          alt="生成圖"
          class="generated-image"
        />
        <p class="path">{{ result.generated_image_path }}</p>
        <button class="refine-btn" @click="$emit('refine')">
          ✏️ 在此基礎上細部微調
        </button>
      </div>

      <!-- 結構化需求 -->
      <div v-if="result.structured_requirement" class="result-section">
        <h3>📋 結構化需求</h3>
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
            <span class="req-label">Edit Scope</span>
            <span class="req-value">{{ Number(result.structured_requirement.edit_scope.scope_value).toFixed(1) }}</span>
          </div>
        </div>
        <details class="json-details">
          <summary>完整 JSON</summary>
          <pre>{{ JSON.stringify(result.structured_requirement, null, 2) }}</pre>
        </details>
      </div>

      <!-- 風格參數 -->
      <div v-if="result.style_params" class="result-section style-section">
        <h3>🎨 套用風格參數</h3>
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
      <div v-else class="result-section style-section muted">
        <h3>🎨 套用風格參數</h3>
        <p class="muted-text">未載入聚合風格檔，將依文字需求與預設 prompt 生成。</p>
      </div>

      <!-- Evaluation Result -->
      <div v-if="result.evaluation_result" class="result-section">
        <h3>📊 Evaluation Result</h3>
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
.panel { flex: 1; display: flex; flex-direction: column; }

/* Placeholder */
.placeholder      { margin: auto; text-align: center; color: #b0a0cc; }
.placeholder-icon { font-size: 4rem; margin-bottom: 1rem; }
.placeholder h2   { font-size: 1.8rem; color: #5a3d8a; margin-bottom: 0.6rem; font-weight: 700; }
.placeholder p    { font-size: 0.95rem; color: #9880bb; }

/* Loading */
.loading-state { margin: auto; text-align: center; color: #a990d4; }
.loading-spinner {
  width: 52px; height: 52px;
  border: 4px solid #e0d4f5;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 1rem;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Result header */
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}
.result-header h2 { font-size: 1.5rem; color: #3d2b6e; }

.badges { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.badge  { padding: 0.25rem 0.75rem; border-radius: 99px; font-size: 0.8rem; font-weight: 600; }
.badge.green { background: #e6f6ec; color: #276749; }
.badge.gray  { background: rgba(255,255,255,0.7); color: #666; }
.badge.blue  { background: var(--primary-light); color: var(--primary); }

/* Result cards */
.result-section {
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(8px);
  border: 1px solid #d4c4ef;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}
.result-section h3 { font-size: 1rem; margin-bottom: 0.75rem; color: #3d2b6e; }

.generated-image {
  width: 100%;
  max-width: 640px;
  border-radius: 10px;
  margin-bottom: 0.6rem;
  border: 1px solid #d4c4ef;
  box-shadow: 0 8px 24px rgba(124, 92, 191, 0.2);
}
.path { font-size: 0.85rem; color: #a990d4; font-family: monospace; }

.refine-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.75rem;
  padding: 0.55rem 1.1rem;
  border: 1.5px solid #7c5cbf;
  border-radius: 8px;
  background: var(--primary-light);
  color: var(--primary);
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.refine-btn:hover {
  background: #ede0ff;
  border-color: #5a3d8a;
  color: #3d2b6e;
}

pre {
  background: rgba(240, 235, 251, 0.8);
  padding: 1rem;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 0.8rem;
  line-height: 1.6;
  color: #3d2b6e;
}

/* Requirement grid */
.req-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 0.75rem; margin-bottom: 0.75rem; }
.req-item { background: var(--primary-light); border-radius: 8px; padding: 0.6rem 0.8rem; display: flex; flex-direction: column; gap: 0.2rem; }
.req-label { font-size: 0.7rem; color: #a990d4; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.req-value { font-size: 0.875rem; color: #3d2b6e; font-weight: 600; }

/* Style section */
.style-section { border-color: #c9b8e8; }
.style-meta    { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 1rem; }
.style-badge   { background: var(--primary); color: white; padding: 0.2rem 0.7rem; border-radius: 99px; font-size: 0.78rem; font-weight: 700; }
.style-name    { font-size: 1rem; font-weight: 700; color: #3d2b6e; }
.style-strength { background: rgba(124,92,191,0.12); color: #7c5cbf; padding: 0.2rem 0.6rem; border-radius: 99px; font-size: 0.78rem; font-weight: 600; }

.color-swatches { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
.swatch-item    { display: flex; flex-direction: column; align-items: center; gap: 0.25rem; }
.swatch         { width: 40px; height: 40px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.08); box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
.swatch-label   { font-size: 0.65rem; color: #a990d4; font-weight: 600; text-transform: capitalize; }
.swatch-hex     { font-size: 0.65rem; color: #7c5cbf; font-family: monospace; }

.style-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 0.75rem; }
.tag { background: var(--primary-light); color: var(--primary); border: 1px solid #d4c4ef; padding: 0.15rem 0.6rem; border-radius: 99px; font-size: 0.75rem; font-weight: 500; }

.eval-feedback { font-size: 0.875rem; color: #b05520; background: #fff5ee; border: 1px solid #f0c8a0; border-radius: 8px; padding: 0.6rem 0.9rem; margin: 0.5rem 0; line-height: 1.5; }
.eval-scores   { display: flex; flex-direction: column; gap: 0.3rem; margin: 0.5rem 0; }
.score-row     { display: flex; justify-content: space-between; font-size: 0.85rem; padding: 0.25rem 0.5rem; background: var(--primary-light); border-radius: 6px; }
.score-key     { color: #7c5cbf; font-weight: 600; }
.score-val     { color: #3d2b6e; font-weight: 700; }
.eval-suggestions ul { margin: 0.3rem 0 0 1.2rem; padding: 0; font-size: 0.85rem; color: #5a3d8a; line-height: 1.7; }

.json-details { margin-top: 0.5rem; }
.json-details summary { cursor: pointer; font-size: 0.82rem; color: #7c5cbf; font-weight: 600; user-select: none; padding: 0.3rem 0; }
.json-details summary:hover { color: #5a3d8a; }

.style-section.muted { opacity: 0.65; }
.muted-text { font-size: 0.875rem; color: #a990d4; }
</style>
