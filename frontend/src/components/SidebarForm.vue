<script setup>
import ImageUpload from './ImageUpload.vue'

const textPrompt      = defineModel('textPrompt',      { default: '' })
const editScope       = defineModel('editScope',       { default: 0.6 })
const selectedStyle   = defineModel('selectedStyle',   { default: 'auto' })
const manualImagePath  = defineModel('manualImagePath',  { default: '' })
const showManualPath   = defineModel('showManualPath',   { default: false })
const noStyleReference = defineModel('noStyleReference', { default: false })
const mode             = defineModel('mode',             { default: 'design' })

defineProps({
  spaceImage:       { type: Object, required: true },
  styleRefImage:    { type: Object, required: true },
  styleOptions:     { type: Array,  default: () => [] },
  styleLoading:     { type: Boolean, default: false },
  styleError:          { type: String,  default: '' },
  matchedStylePreview: { type: Object,  default: null },
  baseImagePreview:    { type: String,  default: null },
  baseImageLabel:      { type: String,  default: '' },
  loading:             { type: Boolean, default: false },
  error:               { type: String,  default: '' },
})

defineEmits(['submit'])
</script>

<template>
  <div class="form">

    <!-- 1. 文字需求 -->
    <div class="field">
      <div class="field-label-row">
        <label class="field-label">✏️ 文字需求</label>
        <label class="toggle-label">
          <input
            type="checkbox"
            :checked="mode === 'refine'"
            @change="mode = $event.target.checked ? 'refine' : 'design'"
          />
          <span>細部微調</span>
        </label>
      </div>
      <textarea
        v-model="textPrompt"
        rows="5"
        :placeholder="mode === 'refine' ? '例如：把沙發換成藍色、窗簾改為白色薄紗' : '例如：客廳想要北歐風格，希望動線順暢'"
      />
    </div>

    <!-- 2. 原始空間圖片 -->
    <div class="field">
      <label class="field-label">
        {{ mode === 'refine' ? '空間圖片（細部微調基底）' : '原始空間圖片（Optional）' }}
      </label>
      <ImageUpload
        label="點擊上傳空間圖"
        icon="📁"
        :preview="spaceImage.preview"
        @change="spaceImage.onChange"
        @remove="spaceImage.remove"
      />
      <!-- 細部微調模式：顯示實際使用的基底圖 -->
      <div v-if="mode === 'refine' && baseImagePreview" class="base-image-box">
        <span class="base-image-label">目前基底圖：{{ baseImageLabel }}</span>
        <img :src="baseImagePreview" alt="基底圖" class="base-image-thumb" />
      </div>
      <div v-if="mode === 'refine' && !baseImagePreview" class="base-image-empty">
        尚無基底圖，請上傳空間圖片
      </div>
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

    <!-- 4. 風格選擇（整體設計模式） -->
    <template v-if="mode === 'design'">
      <div class="field">
        <label class="field-label">選擇裝潢風格</label>
        <select v-model="selectedStyle" :disabled="styleLoading">
          <option v-for="opt in styleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <div v-if="styleLoading" class="status-hint">載入中...</div>
        <div v-if="styleError" class="status-error">{{ styleError }}</div>
      </div>

      <!-- 5. 風格參考圖（整體設計模式） -->
      <div class="field">
        <div class="field-label-row">
          <label class="field-label">🎨 風格參考圖</label>
          <label class="toggle-label">
            <input type="checkbox" v-model="noStyleReference" />
            <span>不套用風格</span>
          </label>
        </div>
        <template v-if="!noStyleReference">
          <ImageUpload
            label="點擊上傳風格參考圖"
            icon="🖼️"
            hint="上傳想要的風格圖片，AI 會參考其色調與氛圍"
            :preview="styleRefImage.preview"
            @change="styleRefImage.onChange"
            @remove="styleRefImage.remove"
          />
          <div v-if="!styleRefImage.preview && matchedStylePreview?.image_url" class="matched-preview">
            <div class="matched-label">
              AI 依描述自動選取：<strong>{{ matchedStylePreview.style_name }}</strong>
              <span class="score">相似度 {{ (matchedStylePreview.similarity * 100).toFixed(0) }}%</span>
            </div>
            <img :src="`http://localhost:8000${matchedStylePreview.image_url}`" alt="風格參考圖" @error="$event.target.style.display='none'" />
          </div>
        </template>
        <div v-else class="no-style-hint">純文字 prompt 生圖，不套用風格參考圖</div>
      </div>
    </template>

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

/* 細部微調基底圖 */
.base-image-box {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin-top: 0.2rem;
}
.base-image-label {
  font-size: 0.75rem;
  color: #7c5cbf;
  font-weight: 600;
}
.base-image-thumb {
  width: 100%;
  max-height: 160px;
  object-fit: cover;
  border-radius: 8px;
  border: 1.5px solid #c9b8e8;
}
.base-image-empty {
  font-size: 0.78rem;
  color: #c0392b;
  background: #fff5f5;
  padding: 0.45rem 0.75rem;
  border-radius: 6px;
  border: 1px dashed #f5c6c6;
}

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

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.toggle-label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: #7c5cbf;
  cursor: pointer;
  font-weight: 600;
}
.toggle-label input[type='checkbox'] { accent-color: #7c5cbf; cursor: pointer; }
.no-style-hint {
  font-size: 0.78rem;
  color: #b0a0cc;
  padding: 0.5rem 0.75rem;
  background: rgba(180, 150, 230, 0.08);
  border-radius: 8px;
  border: 1px dashed #d4c4ef;
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
