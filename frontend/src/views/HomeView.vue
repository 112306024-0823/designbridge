<script setup>
import { ref } from 'vue'

const textPrompt = ref('')
const editScope = ref(0.6)
const modelType = ref('sdxl')
const imageFile = ref(null)
const imagePreview = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref('')

function handleImageChange(e) {
  const file = e.target.files[0]
  if (!file) return
  imageFile.value = file
  imagePreview.value = URL.createObjectURL(file)
}

function removeImage() {
  imageFile.value = null
  imagePreview.value = ''
}

async function handleSubmit() {
  if (!textPrompt.value.trim()) {
    error.value = '請輸入文字需求'
    return
  }
  error.value = ''
  result.value = null
  loading.value = true

  try {
    const response = await fetch('http://localhost:8000/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt: textPrompt.value,
        edit_scope: editScope.value,
        model_type: modelType.value,
      }),
    })
    if (!response.ok) throw new Error(`伺服器錯誤：${response.status}`)
    result.value = await response.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <!-- 側欄 -->
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-icon">🏠</span>
        <span class="logo-text">DesignBridge</span>
      </div>
      <p class="logo-sub">室內設計 AI 助理</p>

      <div class="form">
        <!-- 文字需求 -->
        <div class="field">
          <label>✏️文字需求</label>
          <textarea
            v-model="textPrompt"
            rows="5"
            placeholder="例如：客廳想要北歐風格，希望動線順暢"
          />
        </div>

        <!-- 改動幅度 -->
        <div class="field">
          <label>
            改動幅度
            <span class="value-badge">{{ editScope.toFixed(1) }}</span>
          </label>
          <input type="range" v-model.number="editScope" min="0" max="1" step="0.1" />
          <div class="range-hint">
            <span>局部微調</span>
            <span>大幅改動</span>
          </div>
        </div>

        <!-- 模型選擇 -->
        <div class="field">
          <label>生成模型</label>
          <div class="radio-group">
            <label :class="{ active: modelType === 'sdxl' }">
              <input type="radio" v-model="modelType" value="sdxl" />
              <div>
                <strong>SDXL</strong>
                <small>穩定，1024px</small>
              </div>
            </label>
            <label :class="{ active: modelType === 'sd' }">
              <input type="radio" v-model="modelType" value="sd" />
              <div>
                <strong>SD 3.5 Medium</strong>
                <small>高品質</small>
              </div>
            </label>
            <label :class="{ active: modelType === 'flux' }">
              <input type="radio" v-model="modelType" value="flux" />
              <div>
                <strong>Flux.1 Schnell</strong>
                <small>快速生成</small>
              </div>
            </label>
          </div>
        </div>

        <!-- 圖片上傳 -->
        <div class="field">
          <label>參考圖片（可選）</label>
          <div v-if="imagePreview" class="image-preview">
            <img :src="imagePreview" alt="預覽" />
            <button class="remove-btn" @click="removeImage">✕</button>
          </div>
          <label v-else class="upload-area">
            <input type="file" accept="image/*" @change="handleImageChange" hidden />
            <span class="upload-icon">📁</span>
            <span>點擊上傳圖片</span>
            <small>JPG、PNG、WebP</small>
          </label>
        </div>

        <button class="submit-btn" @click="handleSubmit" :disabled="loading">
          <span v-if="loading" class="spinner"></span>
          {{ loading ? '執行中...' : '▶ 執行工作流' }}
        </button>

        <p v-if="error" class="error">⚠️ {{ error }}</p>
      </div>
    </aside>

    <!-- 主內容區 -->
    <main class="content">
      <div v-if="!result && !loading" class="placeholder">
        <div class="placeholder-icon">✏️</div>
        <h2>輸入設計需求</h2>
        <p>在左側填寫需求後，點擊執行工作流</p>
        <div class="flow-diagram">
          
        </div>
      </div>

      <div v-if="loading" class="loading-state">
        <div class="loading-spinner"></div>
        <p>工作流執行中，請稍候...</p>
      </div>

      <div v-if="result" class="result">
        <div class="result-header">
          <h2>執行結果</h2>
          <div class="badges">
            <span class="badge green">✓ 成功</span>
            <span class="badge gray">⏱ {{ result.elapsed_time }}</span>
            <span class="badge blue">{{ result.routing_decision }}</span>
          </div>
        </div>

        <div v-if="result.generated_image_path" class="result-section">
          <h3>🖼 生成圖</h3>
          <p class="path">{{ result.generated_image_path }}</p>
        </div>

        <div v-if="result.structured_requirement" class="result-section">
          <h3>📋 結構化需求</h3>
          <pre>{{ JSON.stringify(result.structured_requirement, null, 2) }}</pre>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
/* 淡紫主題色 */
:root {
  --primary: #7c5cbf;
  --primary-light: #f0ebfb;
  --primary-hover: #6347a8;
  --primary-border: #c9b8e8;
}

* {
  box-sizing: border-box;
}

.page {
  display: flex;
  min-height: 100vh;
  font-family: 'Segoe UI', sans-serif;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(180, 150, 230, 0.18) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 70%, rgba(140, 110, 210, 0.14) 0%, transparent 55%),
    linear-gradient(135deg, #f3eeff 0%, #ede6fa 40%, #e6dff5 100%);
}

/* 側欄 */
.sidebar {
  width: 400px;
  min-width: 400px;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(180, 150, 230, 0.3);
  padding: 2rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow-y: auto;
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 1.7rem;
  font-weight: 900;
  color: #6b3fa0;
  letter-spacing: -0.02em;
}

.logo-icon {
  font-size: 1.7rem;
}

.logo-sub {
  color: #a990d4;
  font-size: 0.85rem;
  margin-bottom: 1.5rem;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 1.4rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.field > label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #3d2b6e;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.value-badge {
  background: var(--primary-light);
  color: var(--primary);
  padding: 0.1rem 0.55rem;
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 700;
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

textarea:focus {
  outline: none;
  border-color: var(--primary);
  background: #fff;
}

input[type='range'] {
  width: 100%;
  accent-color: #7c5cbf;
}

.range-hint {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #b0a0cc;
}

/* 模型選擇 */
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

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

.radio-group label.active {
  border-color: var(--primary);
  background: var(--primary-light);
}

.radio-group label div {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.radio-group strong {
  font-size: 0.875rem;
  color: #2e1a5e;
}

.radio-group small {
  font-size: 0.75rem;
  color: #a990d4;
}

/* 圖片上傳 */
.upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  padding: 1.5rem;
  border: 2px dashed #c9b8e8;
  border-radius: 8px;
  cursor: pointer;
  color: #a990d4;
  font-size: 0.85rem;
  transition: all 0.2s;
  font-weight: normal !important;
  background: rgba(255,255,255,0.5);
}

.upload-area:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--primary-light);
}

.upload-icon {
  font-size: 1.6rem;
}

.image-preview {
  position: relative;
  border-radius: 8px;
  overflow: hidden;
}

.image-preview img {
  width: 100%;
  max-height: 200px;
  object-fit: cover;
  border-radius: 8px;
  display: block;
}

.remove-btn {
  position: absolute;
  top: 0.4rem;
  right: 0.4rem;
  background: rgba(0,0,0,0.5);
  color: white;
  border: none;
  border-radius: 99px;
  width: 1.6rem;
  height: 1.6rem;
  cursor: pointer;
  font-size: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.error {
  color: #c0392b;
  font-size: 0.85rem;
  background: #fff5f5;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  border: 1px solid #f5c6c6;
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
  opacity: 0.65;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

/* 主內容區 */
.content {
  flex: 1;
  padding: 3rem 4rem;
  display: flex;
  flex-direction: column;
}

.placeholder {
  margin: auto;
  text-align: center;
  color: #b0a0cc;
}

.placeholder-icon {
  font-size: 4rem;
  margin-bottom: 1rem;
}

.placeholder h2 {
  font-size: 1.8rem;
  color: #5a3d8a;
  margin-bottom: 0.6rem;
  font-weight: 700;
}

.placeholder p {
  font-size: 0.95rem;
  margin-bottom: 2.5rem;
  color: #9880bb;
}

.flow-diagram {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.flow-step {
  background: rgba(255,255,255,0.7);
  border: 1px solid #d4c4ef;
  border-radius: 10px;
  padding: 0.6rem 1.2rem;
  font-size: 0.875rem;
  color: var(--primary);
  backdrop-filter: blur(4px);
}

.flow-arrow {
  color: #c9b8e8;
  font-size: 1.2rem;
}

/* Loading */
.loading-state {
  margin: auto;
  text-align: center;
  color: #a990d4;
}

.loading-spinner {
  width: 52px;
  height: 52px;
  border: 4px solid #e0d4f5;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 1rem;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.4);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  display: inline-block;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 結果 */
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.result-header h2 {
  font-size: 1.5rem;
  color: #3d2b6e;
}

.badges {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.badge {
  padding: 0.25rem 0.75rem;
  border-radius: 99px;
  font-size: 0.8rem;
  font-weight: 600;
}

.badge.green { background: #e6f6ec; color: #276749; }
.badge.gray  { background: rgba(255,255,255,0.7); color: #666; }
.badge.blue  { background: var(--primary-light); color: var(--primary); }

.result-section {
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(8px);
  border: 1px solid #d4c4ef;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.result-section h3 {
  font-size: 1rem;
  margin-bottom: 0.75rem;
  color: #3d2b6e;
}

.path {
  font-size: 0.85rem;
  color: #a990d4;
  font-family: monospace;
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
</style>
