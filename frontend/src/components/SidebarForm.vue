<script setup>
import ImageUpload from './ImageUpload.vue'

const textPrompt      = defineModel('textPrompt',      { default: '' })
const editScope       = defineModel('editScope',       { default: 0.6 })
const modelType       = defineModel('modelType',       { default: 'sdxl' })
const selectedStyle   = defineModel('selectedStyle',   { default: 'auto' })
const manualImagePath = defineModel('manualImagePath', { default: '' })
const showManualPath  = defineModel('showManualPath',  { default: false })

defineProps({
  spaceImage:    { type: Object, required: true },
  styleRefImage: { type: Object, required: true },
  styleOptions:  { type: Array,  default: () => [] },
  styleLoading:  { type: Boolean, default: false },
  styleError:          { type: String,  default: '' },
  matchedStylePreview: { type: Object,  default: null },
  loading:             { type: Boolean, default: false },
  error:               { type: String,  default: '' },
})

defineEmits(['submit'])
</script>

<template>
  <div class="form">

    <!-- 1. 文字需求 -->
    <div class="field">
      <label class="field-label">✏️ 文字需求</label>
      <textarea v-model="textPrompt" rows="5" placeholder="例如：客廳想要北歐風格，希望動線順暢" />
    </div>

    <!-- 2. 原始空間圖片 -->
    <div class="field">
      <label class="field-label">原始空間圖片（Optional）</label>
      <ImageUpload
        label="點擊上傳空間圖"
        icon="📁"
        :preview="spaceImage.preview"
        @change="spaceImage.onChange"
        @remove="spaceImage.remove"
      />
      <div class="manual-path">
        <button type="button" class="toggle-btn" @click="showManualPath = !showManualPath">
          {{ showManualPath ? '收合手動輸入' : '進階：手動輸入圖片路徑' }}
        </button>
        <input
          v-if="showManualPath"
          v-model="manualImagePath"
          type="text"
          placeholder="本機圖片路徑"
          class="manual-input"
        />
      </div>
    </div>

    <!-- 3. 改動幅度 -->
    <div class="field">
      <label class="field-label">
        改動幅度
        <span class="value-badge">{{ editScope.toFixed(1) }}</span>
      </label>
      <input type="range" v-model.number="editScope" min="0" max="1" step="0.1" />
      <div class="range-hint"><span>局部微調</span><span>大幅改動</span></div>
    </div>

    <!-- 4. 生成模型 -->
    <div class="field">
      <label class="field-label">生成模型</label>
      <div class="radio-group">
        <label :class="{ active: modelType === 'sdxl' }">
          <input type="radio" v-model="modelType" value="sdxl" />
          <div><strong>SDXL</strong><small>穩定，1024px</small></div>
        </label>
        <label :class="{ active: modelType === 'sd' }">
          <input type="radio" v-model="modelType" value="sd" />
          <div><strong>SD 3.5 Medium</strong><small>高品質</small></div>
        </label>
        <label :class="{ active: modelType === 'flux' }">
          <input type="radio" v-model="modelType" value="flux" />
          <div><strong>Flux.1 Schnell</strong><small>快速生成</small></div>
        </label>
      </div>
    </div>

    <!-- 5. 風格選擇 -->
    <div class="field">
      <label class="field-label">選擇裝潢風格</label>
      <select v-model="selectedStyle" :disabled="styleLoading">
        <option v-for="opt in styleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
      </select>
      <div v-if="styleLoading" class="status-hint">載入中...</div>
      <div v-if="styleError" class="status-error">{{ styleError }}</div>
    </div>

    <!-- 6. 風格參考圖 -->
    <div class="field">
      <label class="field-label">🎨 風格參考圖（Optional）</label>
      <ImageUpload
        label="點擊上傳風格參考圖"
        icon="🖼️"
        hint="上傳想要的風格圖片，AI 會參考其色調與氛圍"
        :preview="styleRefImage.preview"
        @change="styleRefImage.onChange"
        @remove="styleRefImage.remove"
      />
      <!-- 無上傳圖時，顯示向量搜尋到的參考圖 -->
      <div v-if="!styleRefImage.preview && matchedStylePreview?.image_url" class="matched-preview">
        <div class="matched-label">
          AI 依描述自動選取：<strong>{{ matchedStylePreview.style_name }}</strong>
          <span class="score">相似度 {{ (matchedStylePreview.similarity * 100).toFixed(0) }}%</span>
        </div>
        <img :src="`http://localhost:8000${matchedStylePreview.image_url}`" alt="風格參考圖" @error="$event.target.style.display='none'" />
      </div>
    </div>

    <button class="submit-btn" @click="$emit('submit')" :disabled="loading">
      <span v-if="loading" class="spinner"></span>
      {{ loading ? '執行中...' : '▶ 執行工作流' }}
    </button>

    <p v-if="error" class="error">⚠️ {{ error }}</p>
  </div>
</template>

<style scoped>
.form  { display: flex; flex-direction: column; gap: 1.4rem; }
.field { display: flex; flex-direction: column; gap: 0.5rem; }

.field-label { font-size: 0.875rem; font-weight: 600; color: #3d2b6e; }

.value-badge {
  background: var(--primary-light);
  color: var(--primary);
  padding: 0.1rem 0.55rem;
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 700;
  margin-left: 0.4rem;
}

textarea {
  padding: 0.8rem;
  border: 1px solid #d4c4ef;
  border-radius: 8px;
  resize: vertical;
  font-size: 0.9rem;
  color: #333;
  line-height: 1.6;
  transition: border-color 0.2s;
  background: rgba(255,255,255,0.8);
}
textarea:focus { outline: none; border-color: var(--primary); background: #fff; }

input[type='range'] { width: 100%; accent-color: #7c5cbf; }
.range-hint { display: flex; justify-content: space-between; font-size: 0.75rem; color: #b0a0cc; }

.radio-group { display: flex; flex-direction: column; gap: 0.5rem; }
.radio-group label {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.9rem;
  border: 1px solid #d4c4ef;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: normal;
  background: rgba(255,255,255,0.7);
}
.radio-group label.active  { border-color: var(--primary); background: var(--primary-light); }
.radio-group label div     { display: flex; flex-direction: column; gap: 0.1rem; }
.radio-group strong        { font-size: 0.875rem; color: #2e1a5e; }
.radio-group small         { font-size: 0.75rem;  color: #a990d4; }

select {
  padding: 0.7rem;
  border: 1px solid #d4c4ef;
  border-radius: 8px;
  font-size: 0.95rem;
  background: rgba(255,255,255,0.8);
  color: #333;
  transition: border-color 0.2s;
}
select:focus { outline: none; border-color: var(--primary); background: #fff; }

.status-hint  { color: #a990d4; font-size: 0.9em; }
.status-error { color: #c0392b; font-size: 0.9em; }

.manual-path { display: flex; flex-direction: column; gap: 0.4rem; }
.toggle-btn  { background: none; border: none; color: #7c5cbf; cursor: pointer; font-size: 0.9em; padding: 0; text-align: left; }
.manual-input { width: 100%; padding: 0.5rem; border: 1px solid #d4c4ef; border-radius: 6px; font-size: 0.875rem; }

.submit-btn {
  padding: 1rem;
  background: linear-gradient(135deg, #7c5cbf, #9b6dd6);
  color: white;
  border: none;
  border-radius: 10px;
  font-size: 1.05rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
  letter-spacing: 0.03em;
  box-shadow: 0 4px 14px rgba(124, 92, 191, 0.4);
}
.submit-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #6b4faa, #8a5ec5);
  box-shadow: 0 6px 18px rgba(124, 92, 191, 0.5);
  transform: translateY(-1px);
}
.submit-btn:disabled {
  background: linear-gradient(135deg, #9b7ecb, #b49de0);
  opacity: 0.65; cursor: not-allowed; box-shadow: none; transform: none;
}

.spinner {
  width: 16px; height: 16px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error {
  color: #c0392b;
  font-size: 0.85rem;
  background: #fff5f5;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  border: 1px solid #f5c6c6;
}

.matched-preview {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.3rem;
}
.matched-preview img {
  width: 100%;
  max-height: 180px;
  object-fit: cover;
  border-radius: 8px;
  border: 1.5px solid #c9b8e8;
  display: block;
}
.matched-label {
  font-size: 0.78rem;
  color: #7c5cbf;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.score {
  background: var(--primary-light);
  color: var(--primary);
  padding: 0.05rem 0.45rem;
  border-radius: 99px;
  font-size: 0.75rem;
  font-weight: 600;
}
</style>
