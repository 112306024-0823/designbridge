<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useImageField } from '@/composables/useImageField'
import designbridgeLogo from '../../asset/designbridge_logo.png'
import SidebarForm from '@/components/SidebarForm.vue'
import ResultPanel from '@/components/ResultPanel.vue'
import StyleSuggestions from '@/components/StyleSuggestions.vue'
import RefineCanvas from '@/components/RefineCanvas.vue'
import { API_BASE, apiUrl, mediaUrl } from '@/config/api'

const textPrompt = ref('')
const editScope = ref(0.6)
const selectedStyle = ref('auto')
const styleOptions = ref([{ label: '自動', value: 'auto' }])
const styleLoading = ref(false)
const styleError = ref('')
const manualImagePath  = ref('')
const noStyleReference = ref(false)
const outputAspect     = ref('auto')
const familyNeeds      = ref([])
const fengshuiRules    = ref([])
const styleMethod      = ref('ai_analysis')
const spaceImage    = useImageField()
const styleRefImage = useImageField()
const result = ref(null)
const loading = ref(false)
const error = ref('')
let currentRequestId = 0
const submitKey = ref(0)
const matchedStylePreview = ref(null)
const manualMaskPath = ref('')   // 手繪遮罩上傳後的伺服器路徑
const brushSize      = ref(32)
const drawMode       = ref('draw')
const refineCanvasRef = ref(null)
const styleRetrievalMode = ref('text-to-text')

// 模式：'design'（整體設計） | 'refine'（細部微調）
const mode = ref('design')
// 上次成功生成的圖，細部微調時作為基底
const lastGeneratedImage = ref(null)  // { path: string, url: string | null }

// 細部微調基底圖預覽：優先用上次生成圖，其次用已上傳的空間圖
const baseImagePreview = computed(() =>
  lastGeneratedImage.value?.url || spaceImage.preview || null
)
const baseImageLabel = computed(() =>
  lastGeneratedImage.value?.url ? '上次生成圖' : spaceImage.preview ? '上傳的空間圖' : ''
)

// 向量搜尋候選
const styleCandidates = ref([])
const candidatesLoading = ref(false)
const candidatesSearched = ref(false)
const confirmedStyle = ref(null)

// 只有在設計模式、無結果、無 loading、有候選時才顯示 StyleSuggestions
const showSuggestions = computed(() =>
  mode.value === 'design' &&
  !result.value && !loading.value && !styleRefImage.file &&
  (styleCandidates.value.length > 0 || candidatesLoading.value || candidatesSearched.value)
)

let searchTimer = null
async function fetchStyleCandidates() {
  if (styleRefImage.file) return
  const q = textPrompt.value.trim()
  const sid = selectedStyle.value !== 'auto' ? selectedStyle.value : ''
  if (!q && !sid) {
    styleCandidates.value = []
    candidatesSearched.value = false
    confirmedStyle.value = null
    matchedStylePreview.value = null
    return
  }

  candidatesLoading.value = true
  try {
    const res = await fetch(
      apiUrl(`/api/style-search?query=${encodeURIComponent(q)}&style_id=${encodeURIComponent(sid)}&top_k=10&retrieval_mode=${encodeURIComponent(styleRetrievalMode.value)}`)
    )
    if (res.ok) {
      const data = await res.json()
      const sorted = (Array.isArray(data) ? data : [])
        .slice()
        .sort((a, b) => (Number(b?.similarity ?? 0) - Number(a?.similarity ?? 0)))
        .slice(0, 10)
      styleCandidates.value = sorted
      matchedStylePreview.value = sorted[0]
        ? { image_url: sorted[0].image_url, style_name: sorted[0].style_name, similarity: sorted[0].similarity }
        : null
      if (confirmedStyle.value && !sorted.find(c => c.image_url === confirmedStyle.value.image_url)) {
        confirmedStyle.value = null
      }
    }
  } catch {}
  finally {
    candidatesLoading.value = false
    candidatesSearched.value = true
  }
}

function scheduleSearch() {
  clearTimeout(searchTimer)
  result.value = null
  styleCandidates.value = []
  candidatesSearched.value = false
  confirmedStyle.value = null
  matchedStylePreview.value = null
  searchTimer = setTimeout(fetchStyleCandidates, 600)
}

// 只在整體設計模式下觸發風格搜尋
watch([textPrompt, selectedStyle], () => {
  if (mode.value === 'design') scheduleSearch()
})

// 切換到細部微調模式時，清除風格候選
watch(mode, (val) => {
  if (val === 'refine') {
    clearTimeout(searchTimer)
    styleCandidates.value = []
    confirmedStyle.value = null
    matchedStylePreview.value = null
  }
})

watch(() => styleRefImage.file, (newFile) => {
  if (newFile) {
    clearTimeout(searchTimer)
    styleCandidates.value = []
    candidatesSearched.value = false
    confirmedStyle.value = null
    matchedStylePreview.value = null
  } else {
    styleMethod.value = 'ai_analysis'
  }
})

async function waitForBackend(maxWaitMs = 120000, intervalMs = 2000) {
  const deadline = Date.now() + maxWaitMs
  while (Date.now() < deadline) {
    try {
      const ctrl = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), 4000)
      const res = await fetch(apiUrl('/api/health'), { signal: ctrl.signal })
      clearTimeout(timer)
      if (res.ok) return true
    } catch {
      /* backend still starting */
    }
    styleError.value = '等待後端啟動中…（請確認已執行 python -m uvicorn api:app）'
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

async function fetchStyleOptions() {
  styleLoading.value = true
  styleError.value = ''

  if (!(await waitForBackend())) {
    styleError.value = '無法連線後端，請確認伺服器是否已啟動（python -m uvicorn api:app）'
    styleLoading.value = false
    return
  }

  try {
    const res = await fetch(apiUrl('/api/style-profiles'))
    if (!res.ok) throw new Error('載入風格選項失敗')
    const data = await res.json()
    styleOptions.value = [
      { label: '自動', value: 'auto' },
      ...data.map(({ style_name, style_id }) => ({
        label: `${style_name} (${style_id})`,
        value: style_id,
      })),
    ]
    styleError.value = ''
  } catch {
    styleError.value = '無法載入風格選項，請稍後重試'
  } finally {
    styleLoading.value = false
  }
}

async function handleMaskReady(blob) {
  const file = new File([blob], 'mask.png', { type: 'image/png' })
  manualMaskPath.value = await uploadFile(file)
}

async function uploadFile(file) {
  const body = new FormData()
  body.append('file', file) 
  const res = await fetch(apiUrl('/api/upload-image'), { method: 'POST', body })
  if (!res.ok) throw new Error(`{res.status}`)
  return (await res.json()).path
}

async function handleSubmit() {
  const hasText = textPrompt.value.trim()
  const hasStyle = selectedStyle.value !== 'auto'
  const hasImage = mode.value === 'refine'
    ? lastGeneratedImage.value?.path || spaceImage.file || manualImagePath.value.trim()
    : spaceImage.file || manualImagePath.value.trim()
  if (mode.value === 'refine' && !hasText) {
    error.value = '細部微調模式請輸入調整需求'
    return
  }
  if (!hasText && !hasStyle && !hasImage) {
    error.value = '請提供文字需求、風格選擇或圖片'
    return
  }
  const requestId = ++currentRequestId
  submitKey.value++
  error.value = ''
  result.value = null
  loading.value = true
  try {
    // 細部微調優先用上次生成圖（已在伺服器），否則才上傳空間圖
    const initial_image_path = (mode.value === 'refine' && lastGeneratedImage.value?.path)
      ? lastGeneratedImage.value.path
      : spaceImage.file
        ? await uploadFile(spaceImage.file)
        : manualImagePath.value.trim() || undefined

    let style_reference_image_path = undefined
    if (!noStyleReference.value) {
      if (styleRefImage.file) {
        style_reference_image_path = await uploadFile(styleRefImage.file)
      } else if (confirmedStyle.value?.image_url) {
        style_reference_image_path = confirmedStyle.value.image_url
      }
    }

    const res = await fetch(apiUrl('/api/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt: textPrompt.value,
        edit_scope: editScope.value,
        style_profile_id: !noStyleReference.value && selectedStyle.value !== 'auto'
          ? selectedStyle.value
          : !noStyleReference.value ? confirmedStyle.value?.style_id || undefined : undefined,
        initial_image_path,
        style_reference_image_path,
        no_style_reference: mode.value === 'refine' || noStyleReference.value,
        refine_mode: mode.value === 'refine',
        output_aspect: outputAspect.value,
        mask_image_path: manualMaskPath.value || undefined,
        style_retrieval_mode: styleRetrievalMode.value,
        family_needs: familyNeeds.value,
        fengshui_rules: fengshuiRules.value,
        style_method: styleMethod.value,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId === currentRequestId) {
      result.value = data
      // 每次成功生圖後更新基底圖（細部微調下一輪用）
      if (data.generated_image_path) {
        lastGeneratedImage.value = {
          path: data.generated_image_path,
          url: data.generated_image_url || null,
        }
      }
    }
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

function handleConfirmStyle(candidate) {
  confirmedStyle.value = candidate
}

function handleClearConfirmedStyle() {
  confirmedStyle.value = null
}

function handleChangeRetrievalMode(nextMode) {
  if (nextMode === styleRetrievalMode.value) return
  styleRetrievalMode.value = nextMode
  fetchStyleCandidates()
}

// ResultPanel 的「細部微調」按鈕觸發：切換模式並鎖定當前生圖為基底
function handleRefine() {
  mode.value = 'refine'
}

// refine 模式送出：從 RefineCanvas 取得遮罩後送 API
async function handleRefineSubmit() {
  if (!textPrompt.value.trim()) { error.value = '請輸入調整需求'; return }
  const requestId = ++currentRequestId
  error.value = ''
  result.value = null
  loading.value = true
  try {
    let mask_image_path
    const maskBlob = await refineCanvasRef.value?.getMaskBlob()
    if (maskBlob) {
      mask_image_path = await uploadFile(new File([maskBlob], 'mask.png', { type: 'image/png' }))
      manualMaskPath.value = mask_image_path
    }

    const initial_image_path = lastGeneratedImage.value?.path
      || (spaceImage.file ? await uploadFile(spaceImage.file) : manualImagePath.value.trim() || undefined)

    const res = await fetch(apiUrl('/api/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt: textPrompt.value,
        edit_scope: editScope.value,
        initial_image_path,
        no_style_reference: true,
        refine_mode: true,
        output_aspect: outputAspect.value,
        mask_image_path,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId === currentRequestId) {
      result.value = data
      if (data.generated_image_path) {
        lastGeneratedImage.value = {
          path: data.generated_image_path,
          url: data.generated_image_url || null,
        }
      }
    }
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

onMounted(fetchStyleOptions)
</script>

<template>
  <div class="page">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="logo">
          <img :src="designbridgeLogo" alt="DesignBridge" class="logo-img" />
        </div>

        <div class="mode-tabs">
          <button
            :class="['mode-tab', { active: mode === 'design' }]"
            @click="mode = 'design'"
          >
            裝潢圖生成
          </button>
          <button
            :class="['mode-tab', { active: mode === 'refine' }]"
            @click="mode = 'refine'"
          >
            細部編輯
          </button>
        </div>
      </div>

      <div class="sidebar-body">
      <SidebarForm
        v-model:textPrompt="textPrompt"
        v-model:editScope="editScope"
        v-model:selectedStyle="selectedStyle"
        v-model:noStyleReference="noStyleReference"
        v-model:mode="mode"
        v-model:outputAspect="outputAspect"
        v-model:brushSize="brushSize"
        v-model:drawMode="drawMode"
        v-model:familyNeeds="familyNeeds"
        v-model:fengshuiRules="fengshuiRules"
        v-model:styleMethod="styleMethod"
        :spaceImage="spaceImage"
        :styleRefImage="styleRefImage"
        :styleOptions="styleOptions"
        :styleLoading="styleLoading"
        :styleError="styleError"
        @retry-style-options="fetchStyleOptions"
        :matchedStylePreview="matchedStylePreview"
        :baseImagePreview="baseImagePreview"
        :baseImageLabel="baseImageLabel"
        :loading="loading"
        :error="error"
        @submit="mode === 'refine' ? handleRefineSubmit() : handleSubmit()"
        @mask-ready="handleMaskReady"
      />
      </div>
    </aside>

    <RouterLink to="/history" class="history-fab" title="歷史紀錄">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
    </RouterLink>

    <main class="content">
      <!-- 細部微調模式 -->
      <template v-if="mode === 'refine' && baseImagePreview">
        <!-- 生成中遮罩 -->
        <div v-if="loading" class="refine-loading">
          <div class="refine-spinner" />
          <span>AI 生成中...</span>
        </div>

        <!-- 生成結果（有結果時顯示，可繼續再次編輯） -->
        <div v-else-if="result?.generated_image_url" class="refine-result">
          <div class="refine-result-header">
            <span class="refine-result-label">生成結果</span>
            <button class="refine-continue-btn" @click="result = null">繼續編輯</button>
          </div>
          <img :src="result.generated_image_url" class="refine-result-img" alt="生成結果" />
        </div>

        <!-- 編輯畫布 -->
        <RefineCanvas
          v-else
          ref="refineCanvasRef"
          :imageUrl="baseImagePreview"
          :brushSize="brushSize"
          :drawMode="drawMode"
          class="refine-canvas-area"
        />
      </template>

      <!-- 整體設計：風格推薦 / 結果 -->
      <template v-else>
        <StyleSuggestions
          v-if="showSuggestions"
          :candidates="styleCandidates"
          :confirmed="confirmedStyle"
          :loading="candidatesLoading"
          :retrieval-mode="styleRetrievalMode"
          :api-base="API_BASE"
          @confirm="handleConfirmStyle"
          @clear="handleClearConfirmedStyle"
          @change-mode="handleChangeRetrievalMode"
        />
        <ResultPanel v-else :key="submitKey" :result="result" :loading="loading" @refine="handleRefine" />
      </template>
    </main>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  min-height: 100vh;
  background:
    radial-gradient(ellipse at 12% 20%, rgba(200, 160, 110, 0.18) 0%, transparent 48%),
    radial-gradient(ellipse at 88% 80%, rgba(160, 120, 80, 0.14) 0%, transparent 48%),
    linear-gradient(150deg, #fdf6ee 0%, #f5e8d8 45%, #ede0cf 100%);
}

/* ── Sidebar ── */
.sidebar {
  width: 500px;
  min-width: 420px;
  background: rgba(255, 248, 240, 0.88);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-right: 1px solid var(--surface-border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.refine-canvas-area {
  width: 100%;
  height: 100%;
  flex: 1;
}

/* 生成中 */
.refine-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  color: #8B5E3C;
  font-size: 0.95rem;
  font-weight: 600;
}
.refine-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(139, 94, 60, 0.2);
  border-top-color: #8B5E3C;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 生成結果 */
.refine-result {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  padding: 1.5rem;
  overflow-y: auto;
}
.refine-result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 720px;
}
.refine-result-label {
  font-size: 1rem;
  font-weight: 700;
  color: #5c3d24;
}
.refine-continue-btn {
  padding: 0.4rem 1rem;
  border: 1.5px solid #999;
  border-radius: 8px;
  background: transparent;
  color: #444;
  font-size: 0.82rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}
.refine-continue-btn:hover { background: #f0f0f0; border-color: #666; }
.refine-result-img {
  width: 100%;
  max-width: 720px;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.18);
  object-fit: contain;
}

.sidebar-header {
  padding: 1.75rem 2rem 1.25rem;
  border-bottom: 1px solid rgba(180, 140, 100, 0.14);
  flex-shrink: 0;
}

.mode-tabs {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.mode-tab {
  flex: 1;
  padding: 0.6rem 0;
  border: 2px solid #d8d8d8;
  border-radius: 12px;
  background: transparent;
  color: #444;
  font-size: 0.88rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s;
}
.mode-tab:hover:not(.active) {
  background: #f5f5f5;
  border-color: #bbb;
}
.mode-tab.active {
  background: linear-gradient(135deg, #8B5E3C 0%, #b07845 100%);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 14px rgba(139, 94, 60, 0.35);
}

.logo {
  margin-bottom: 0.25rem;
}

.logo-img {
  height: auto;
  width: 200px;
  display: block;
}

.history-fab {
  position: fixed;
  top: 1.25rem;
  right: 1.5rem;
  z-index: 100;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 248, 240, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(180, 140, 100, 0.35);
  box-shadow: 0 2px 10px rgba(139, 94, 60, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8B5E3C;
  text-decoration: none;
  transition: box-shadow 0.15s, background 0.15s, transform 0.15s;
}
.history-fab:hover {
  background: rgba(255, 248, 240, 1);
  box-shadow: 0 4px 16px rgba(139, 94, 60, 0.35);
  transform: scale(1.08);
}

.logo-tagline {
  font-size: 0.72rem;
  color: var(--text-3);
  font-weight: 500;
  margin: 0;
  padding-left: calc(30px + 0.55rem);
  letter-spacing: 0.01em;
}

.sidebar-body {
  flex: 1;
  padding: 1.5rem 2rem 2rem;
  overflow-y: auto;
}

/* ── Content ── */
.content {
  flex: 1;
  min-width: 0;
  padding: 2.5rem 3rem;
  display: flex;
  flex-direction: column;
}
</style>
