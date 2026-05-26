<script setup>
import { ref } from 'vue'
import ImageUpload from './ImageUpload.vue'
import MaskEditor from './MaskEditor.vue'

const textPrompt      = defineModel('textPrompt',      { default: '' })
const editScope       = defineModel('editScope',       { default: 0.6 })
const selectedStyle   = defineModel('selectedStyle',   { default: 'auto' })
const manualImagePath  = defineModel('manualImagePath',  { default: '' })
const showManualPath   = defineModel('showManualPath',   { default: false })
const noStyleReference = defineModel('noStyleReference', { default: false })
const mode             = defineModel('mode',             { default: 'design' })
const outputAspect     = defineModel('outputAspect',     { default: 'auto' })
const brushSize        = defineModel('brushSize',        { default: 32 })
const drawMode         = defineModel('drawMode',         { default: 'draw' })
const familyNeeds      = defineModel('familyNeeds',      { default: () => [] })
const fengshuiRules    = defineModel('fengshuiRules',    { default: () => [] })
const styleMethod      = defineModel('styleMethod',      { default: 'ai_analysis' })

const showMaskEditor = ref(false)

const FAMILY_OPTIONS = [
  { value: 'children',    label: '有小孩' },
  { value: 'wheelchair',  label: '有輪椅使用者' },
  { value: 'pets',        label: '有寵物' },
]
const FENGSHUI_OPTIONS = [
  { value: 'bed_not_facing_door',       label: '床不對門' },
  { value: 'sofa_not_back_to_door',     label: '沙發不背門' },
  { value: 'desk_not_facing_window',    label: '書桌不背窗' },
]

function toggleFamilyNeed(value) {
  familyNeeds.value = familyNeeds.value.includes(value)
    ? familyNeeds.value.filter(v => v !== value)
    : [...familyNeeds.value, value]
}

function toggleFengshuiRule(value) {
  fengshuiRules.value = fengshuiRules.value.includes(value)
    ? fengshuiRules.value.filter(v => v !== value)
    : [...fengshuiRules.value, value]
}

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

defineEmits(['submit', 'mask-ready'])
</script>

<template>
  <div class="form">

    <!-- 1. 文字需求 -->
    <div class="field">
      <label class="field-label">
        {{ mode === 'refine' ? '微調需求' : '描述你的空間需求' }}
      </label>
      <textarea
        v-model="textPrompt"
        rows="5"
        :placeholder="mode === 'refine'
          ? '例如：把沙發換成藍色布藝款式、窗簾改為白色薄紗'
          : '例如：開門回家的瞬間就能感到放鬆的客廳設計，喜歡北歐風、木質感...'"
      />
    </div>

    <!-- 2. 家庭結構特殊需求 -->
    <div class="field">
      <label class="field-label">家庭結構特殊需求 <span class="optional">選填</span></label>
      <div class="chip-group">
        <button
          v-for="opt in FAMILY_OPTIONS"
          :key="opt.value"
          type="button"
          :class="['chip', { active: familyNeeds.includes(opt.value) }]"
          @click="toggleFamilyNeed(opt.value)"
        >{{ opt.label }}</button>
      </div>
    </div>

    <!-- 3. 風水需求 -->
    <div class="field">
      <label class="field-label">風水需求 <span class="optional">選填</span></label>
      <div class="chip-group">
        <button
          v-for="opt in FENGSHUI_OPTIONS"
          :key="opt.value"
          type="button"
          :class="['chip', { active: fengshuiRules.includes(opt.value) }]"
          @click="toggleFengshuiRule(opt.value)"
        >{{ opt.label }}</button>
      </div>
    </div>

    <!-- divider -->
    <div class="divider"></div>

    <!-- 4. 原始空間圖片 -->
    <div class="field">
      <label class="field-label">
        {{ mode === 'refine' ? '空間圖片（細部微調基底）' : '原始空間圖片（Optional）' }}
      </label>
      <ImageUpload
        label="點擊或拖曳上傳"
        icon="📷"
        :preview="spaceImage.preview"
        @change="spaceImage.onChange"
        @remove="spaceImage.remove"
      />
      <!-- 細部微調：畫筆工具列 -->
      <div v-if="mode === 'refine'" class="brush-toolbar">
        <span class="brush-title">塗抹想修改的區域</span>
        <div class="brush-btns">
          <button
            :class="['brush-tool', { active: drawMode === 'draw' }]"
            type="button"
            @click="drawMode = 'draw'"
          >畫筆</button>
          <button
            :class="['brush-tool', { active: drawMode === 'erase' }]"
            type="button"
            @click="drawMode = 'erase'"
          >橡皮擦</button>
        </div>
        <label class="brush-size-label">
          筆刷 {{ brushSize }}px
          <input type="range" v-model.number="brushSize" min="5" max="120" step="5" class="brush-range" />
        </label>
      </div>

      <button type="button" class="toggle-btn" @click="showManualPath = !showManualPath">
        {{ showManualPath ? '收合' : '手動輸入路徑' }}
      </button>
      <input
        v-if="showManualPath"
        v-model="manualImagePath"
        type="text"
        placeholder="本機圖片路徑"
        class="manual-input"
      />
    </div>

    <!-- 3. 改動幅度（細部微調不顯示） -->
    <div v-if="mode === 'design'" class="field">
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

    <!-- 5. 輸出比例 -->
    <div class="field">
      <label class="field-label">輸出比例</label>
      <select v-model="outputAspect">
        <option value="auto">自動（依原圖比例）</option>
        <option value="1:1">1:1</option>
        <option value="4:3">4:3</option>
        <option value="3:4">3:4</option>
        <option value="16:9">16:9</option>
        <option value="9:16">9:16</option>
      </select>
    </div>

    <!-- divider -->
    <div class="divider"></div>

    <!-- 6. 風格參考圖 -->
    <div class="field">
      <div class="field-label-row">
        <label class="field-label">風格參考圖</label>
        <label class="toggle-label">
          <input type="checkbox" v-model="noStyleReference" />
          <span>不套用風格</span>
        </label>
      </div>
      <template v-if="!noStyleReference">
        <ImageUpload
          label="點擊或拖曳上傳"
          icon="🖼️"
          hint="上傳想要的風格圖片，AI 會參考其色調與氛圍"
          :preview="styleRefImage.preview"
          @change="styleRefImage.onChange"
          @remove="styleRefImage.remove"
        />
        <div v-if="styleRefImage.preview" class="radio-group style-method-group">
          <label :class="{ active: styleMethod === 'ai_analysis' }">
            <input type="radio" v-model="styleMethod" value="ai_analysis" />
            <div class="radio-content">
              <strong>AI 分析風格</strong>
              <small>Gemini 解析圖片色調，注入 prompt</small>
            </div>
          </label>
          <label :class="{ active: styleMethod === 'redux' }">
            <input type="radio" v-model="styleMethod" value="redux" />
            <div class="radio-content">
              <strong>FLUX.1-Redux</strong>
              <small>以圖為主直接做風格遷移</small>
            </div>
          </label>
          <label :class="{ active: styleMethod === 'ipadapter' }">
            <input type="radio" v-model="styleMethod" value="ipadapter" />
            <div class="radio-content">
              <strong>IP-Adapter</strong>
              <small>文字定空間類型，圖像注入風格</small>
            </div>
          </label>
        </div>
        <div v-if="!styleRefImage.preview && matchedStylePreview?.image_url" class="matched-preview">
          <div class="matched-label">
            AI 依描述自動選取：<strong>{{ matchedStylePreview.style_name }}</strong>
            <span class="score">{{ (matchedStylePreview.similarity * 100).toFixed(0) }}%</span>
          </div>
          <img
            :src="`http://localhost:8000${matchedStylePreview.image_url}`"
            alt="風格參考圖"
            @error="$event.target.style.display='none'"
          />
        </div>
      </template>
      <div v-else class="no-style-hint">純文字 prompt 生圖，不套用風格參考圖</div>
    </div>

  </template><!-- /mode === 'design' -->

    <!-- CTA -->
    <button class="submit-btn" @click="$emit('submit')" :disabled="loading">
      <span v-if="loading" class="spinner"></span>
      <span>{{ loading ? 'AI 生成中...' : '執行工作流' }}</span>
    </button>

    <p v-if="error" class="error-msg">{{ error }}</p>
  </div>

  <!-- 遮罩編輯器 Modal -->
  <MaskEditor
    v-if="showMaskEditor"
    :imageUrl="baseImagePreview"
    @confirm="blob => { $emit('mask-ready', blob); showMaskEditor = false }"
    @cancel="showMaskEditor = false"
  />
</template>

<style scoped>
.form { display: flex; flex-direction: column; gap: 1.25rem; }

.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(180,150,230,0.2), transparent);
  margin: 0.1rem 0;
}

/* Field */
.field { display: flex; flex-direction: column; gap: 0.45rem; }

.field-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-2);
  letter-spacing: 0.01em;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.optional {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-4);
  background: var(--primary-subtle);
  padding: 0.1rem 0.45rem;
  border-radius: 99px;
}

.value-badge {
  background: var(--primary-light);
  color: var(--primary);
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
  font-size: 0.75rem;
  font-weight: 700;
  margin-left: auto;
}

/* Textarea */
textarea {
  padding: 0.85rem 1rem;
  border: 1.5px solid #ddd4f0;
  border-radius: var(--radius-md);
  resize: vertical;
  font-size: 0.875rem;
  font-family: inherit;
  color: var(--text-1);
  line-height: 1.65;
  transition: border-color 0.18s, box-shadow 0.18s;
  background: rgba(255,255,255,0.75);
}
textarea:focus {
  outline: none;
  border-color: var(--primary);
  background: #fff;
  box-shadow: 0 0 0 3px rgba(124,92,191,0.1);
}
textarea::placeholder { color: var(--text-4); }

/* Range */
input[type='range'] { width: 100%; accent-color: var(--primary); cursor: pointer; }
.range-hint { display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-4); }

/* Radio group */
.radio-group { display: flex; flex-direction: column; gap: 0.4rem; }
.radio-group label {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.6rem 0.85rem;
  border: 1.5px solid #ddd4f0;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.18s;
  background: rgba(255,255,255,0.65);
}
.radio-group label:hover { border-color: var(--primary-border); background: rgba(255,255,255,0.9); }
.radio-group label.active { border-color: var(--primary); background: var(--primary-light); }
.radio-group input[type='radio'] { accent-color: var(--primary); flex-shrink: 0; }
.radio-content { display: flex; flex-direction: column; gap: 0.05rem; }
.radio-content strong { font-size: 0.83rem; font-weight: 600; color: var(--text-1); }
.radio-content small  { font-size: 0.72rem; color: var(--text-3); }

/* Select */
select {
  padding: 0.65rem 0.85rem;
  border: 1.5px solid #ddd4f0;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-family: inherit;
  background: rgba(255,255,255,0.75);
  color: var(--text-1);
  cursor: pointer;
  transition: border-color 0.18s;
  appearance: auto;
}
select:focus { outline: none; border-color: var(--primary); background: #fff; }

.status-hint  { font-size: 0.8rem; color: var(--text-3); }
.status-error { font-size: 0.8rem; color: #c0392b; }

/* Manual path */

.brush-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--primary);
}

.brush-toolbar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.65rem 0.75rem;
  background: var(--primary-subtle);
  border: 1.5px solid var(--primary-border);
  border-radius: var(--radius-md);
}
.brush-btns {
  display: flex;
  gap: 0.4rem;
}
.brush-tool {
  flex: 1;
  padding: 0.35rem 0;
  border: 1.5px solid var(--primary-border);
  border-radius: 8px;
  background: #fff;
  color: var(--primary);
  font-size: 0.8rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.brush-tool.active {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.brush-size-label {
  font-size: 0.75rem;
  color: var(--primary);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brush-range {
  width: 120px;
  accent-color: var(--primary);
  cursor: pointer;
}

.mask-btn {
  padding: 0.45rem 0.85rem;
  border: 1.5px dashed var(--primary-border);
  border-radius: var(--radius-md);
  background: var(--primary-subtle);
  color: var(--primary);
  font-size: 0.8rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
  text-align: left;
}
.mask-btn:hover { background: var(--primary-light); border-style: solid; }

.toggle-btn {
  background: none; border: none;
  color: var(--primary); cursor: pointer;
  font-size: 0.78rem; font-family: inherit;
  padding: 0; text-align: left;
  opacity: 0.7;
}
.toggle-btn:hover { opacity: 1; }
.manual-input {
  width: 100%; padding: 0.5rem 0.75rem;
  border: 1.5px solid #ddd4f0; border-radius: var(--radius-sm);
  font-size: 0.83rem; font-family: inherit; color: var(--text-1);
  background: rgba(255,255,255,0.75);
}
.manual-input:focus { outline: none; border-color: var(--primary); }

/* Style toggle */
.field-label-row { display: flex; align-items: center; justify-content: space-between; }
.toggle-label {
  display: flex; align-items: center; gap: 0.35rem;
  font-size: 0.75rem; color: var(--primary); cursor: pointer; font-weight: 600;
}
.toggle-label input[type='checkbox'] { accent-color: var(--primary); cursor: pointer; }

.no-style-hint {
  font-size: 0.78rem; color: var(--text-3);
  padding: 0.55rem 0.75rem;
  background: var(--primary-subtle);
  border-radius: var(--radius-md);
  border: 1px dashed var(--primary-border);
}

/* Style method toggle (compact) */
.style-method-group { margin-top: 0.25rem; }
.style-method-group label { padding: 0.45rem 0.75rem; }
.style-method-group .radio-content strong { font-size: 0.8rem; }
.style-method-group .radio-content small  { font-size: 0.68rem; }

/* Matched preview */
.matched-preview { display: flex; flex-direction: column; gap: 0.4rem; margin-top: 0.15rem; }
.matched-preview img {
  width: 100%; max-height: 160px; object-fit: cover;
  border-radius: var(--radius-md); border: 1.5px solid var(--primary-border);
  display: block;
  cursor: zoom-in;
}
.matched-preview img:focus-visible {
  outline: 3px solid rgba(124, 92, 191, 0.25);
  outline-offset: 3px;
  border-radius: var(--radius-md);
}
.matched-label {
  font-size: 0.75rem; color: var(--primary);
  display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;
}
.score {
  background: var(--primary-light); color: var(--primary);
  padding: 0.05rem 0.4rem; border-radius: 99px; font-size: 0.7rem; font-weight: 600;
}

/* Chips */
.chip-group { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.chip {
  padding: 0.35rem 0.75rem;
  border: 1.5px solid #ddd4f0;
  border-radius: 99px;
  font-size: 0.8rem;
  font-family: inherit;
  font-weight: 500;
  color: var(--text-2);
  background: rgba(255,255,255,0.7);
  cursor: pointer;
  transition: all 0.15s;
  line-height: 1.4;
}
.chip:hover { border-color: var(--primary-border); background: rgba(255,255,255,0.95); color: var(--primary); }
.chip.active {
  border-color: var(--primary);
  background: linear-gradient(135deg, #7c5cbf 0%, #a06edb 100%);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(124,92,191,0.35);
}

/* Submit */
.submit-btn {
  margin-top: 0.25rem;
  padding: 0.9rem 1rem;
  background: linear-gradient(135deg, #7c5cbf 0%, #a06edb 100%);
  color: white;
  border: none;
  border-radius: var(--radius-lg);
  font-size: 0.95rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
  letter-spacing: 0.02em;
  box-shadow: 0 4px 16px rgba(124, 92, 191, 0.38);
}
.submit-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(124, 92, 191, 0.48);
}
.submit-btn:active:not(:disabled) { transform: translateY(0); }
.submit-btn:disabled {
  opacity: 0.6; cursor: not-allowed; box-shadow: none; transform: none;
}

.spinner {
  width: 15px; height: 15px;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-msg {
  font-size: 0.82rem; color: #c0392b;
  background: #fff5f5; padding: 0.55rem 0.8rem;
  border-radius: var(--radius-sm); border: 1px solid #f5c6c6;
}
</style>
