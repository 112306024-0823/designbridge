<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useImageField } from '@/composables/useImageField'
import designbridgeLogo from '../../asset/designbridge_logo.png'
import SidebarForm from '@/components/SidebarForm.vue'
import ResultPanel from '@/components/ResultPanel.vue'
import StyleSuggestions from '@/components/StyleSuggestions.vue'
import { API_BASE, apiUrl } from '@/config/api'

// ── Two-step state ────────────────────────────────────────────
const designStep   = ref(1)   // 1 = layout input, 2 = style + 3D
const floorPlanUrl  = ref('')
const floorPlanPath = ref('')
const sceneGraph    = ref(null)

// ── Step 1 form values ────────────────────────────────────────
const roomType       = ref('living_room')
const spaceSizePing  = ref(4)
const furnitureItems = ref([])
const extraPrompt    = ref('')
const familyNeeds    = ref([])
const fengshuiRules  = ref([])

// ── Step 2 form values ────────────────────────────────────────
const selectedStyle    = ref('auto')
const noStyleReference = ref(false)
const styleMethod      = ref('ai_analysis')
const styleRefImage    = useImageField()

// ── Style options ─────────────────────────────────────────────
const styleOptions  = ref([{ label: '自動', value: 'auto' }])
const styleLoading  = ref(false)
const styleError    = ref('')

// ── Candidates (step 2) ───────────────────────────────────────
const styleCandidates    = ref([])
const candidatesLoading  = ref(false)
const candidatesSearched = ref(false)
const confirmedStyle     = ref(null)
const matchedStylePreview = ref(null)

// ── Result / loading ──────────────────────────────────────────
const result  = ref(null)
const loading = ref(false)
const error   = ref('')
let currentRequestId = 0
const submitKey = ref(0)
const styleRetrievalMode = ref('text-to-text')

// Show StyleSuggestions only in step 2 before 3D result
const showSuggestions = computed(() =>
  designStep.value === 2 &&
  !result.value && !loading.value && !styleRefImage.file &&
  (styleCandidates.value.length > 0 || candidatesLoading.value || candidatesSearched.value)
)

// ── Style search ──────────────────────────────────────────────
let searchTimer = null
async function fetchStyleCandidates() {
  if (styleRefImage.file) return
  const q = extraPrompt.value.trim()
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
        .slice().sort((a, b) => Number(b?.similarity ?? 0) - Number(a?.similarity ?? 0)).slice(0, 10)
      styleCandidates.value = sorted
      matchedStylePreview.value = sorted[0]
        ? { image_url: sorted[0].image_url, style_name: sorted[0].style_name, similarity: sorted[0].similarity }
        : null
    }
  } catch {}
  finally { candidatesLoading.value = false; candidatesSearched.value = true }
}

function scheduleSearch() {
  clearTimeout(searchTimer)
  styleCandidates.value = []
  candidatesSearched.value = false
  confirmedStyle.value = null
  matchedStylePreview.value = null
  searchTimer = setTimeout(fetchStyleCandidates, 600)
}

watch([selectedStyle], () => { if (designStep.value === 2) scheduleSearch() })
watch(() => styleRefImage.file, (f) => {
  if (f) { clearTimeout(searchTimer); styleCandidates.value = []; candidatesSearched.value = false }
  else styleMethod.value = 'ai_analysis'
})

// ── Backend wait ──────────────────────────────────────────────
async function waitForBackend(maxWaitMs = 120000, intervalMs = 2000) {
  const deadline = Date.now() + maxWaitMs
  while (Date.now() < deadline) {
    try {
      const ctrl = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), 4000)
      const res = await fetch(apiUrl('/api/health'), { signal: ctrl.signal })
      clearTimeout(timer)
      if (res.ok) return true
    } catch {}
    styleError.value = '等待後端啟動中…（請確認已執行 python -m uvicorn api:app）'
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

async function fetchStyleOptions() {
  styleLoading.value = true
  styleError.value = ''
  if (!(await waitForBackend())) {
    styleError.value = '無法連線後端，請確認伺服器是否已啟動'
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
  } catch { styleError.value = '無法載入風格選項，請稍後重試' }
  finally { styleLoading.value = false }
}

async function uploadFile(file) {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(apiUrl('/api/upload-image'), { method: 'POST', body })
  if (!res.ok) throw new Error(`${res.status}`)
  return (await res.json()).path
}

// ── Step 1: generate layout ───────────────────────────────────
async function handleSubmitLayout() {
  if (!furnitureItems.value.length && !extraPrompt.value.trim()) {
    error.value = '請至少選擇一件家具或輸入描述'
    return
  }
  const requestId = ++currentRequestId
  error.value = ''
  loading.value = true
  result.value = null
  try {
    const res = await fetch(apiUrl('/api/generate-layout'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_type:       roomType.value,
        space_size_ping: spaceSizePing.value,
        furniture_list:  furnitureItems.value,
        text_prompt:     extraPrompt.value,
        family_needs:    familyNeeds.value,
        fengshui_rules:  fengshuiRules.value,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId !== currentRequestId) return
    floorPlanUrl.value  = data.floor_plan_url || ''
    floorPlanPath.value = data.floor_plan_path || ''
    sceneGraph.value    = data.scene_graph || null
    designStep.value = 2
    // trigger style candidates search based on extraPrompt
    if (extraPrompt.value.trim()) scheduleSearch()
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

// ── Step 2: generate 3D render ────────────────────────────────
async function handleSubmit3D() {
  const requestId = ++currentRequestId
  submitKey.value++
  error.value = ''
  result.value = null
  loading.value = true
  try {
    let style_reference_image_path
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
        text_prompt:               extraPrompt.value,
        edit_scope:                1.0,
        style_profile_id:          !noStyleReference.value && selectedStyle.value !== 'auto'
          ? selectedStyle.value
          : !noStyleReference.value ? confirmedStyle.value?.style_id || undefined : undefined,
        style_reference_image_path,
        no_style_reference:        noStyleReference.value,
        refine_mode:               false,
        output_aspect:             'auto',
        style_method:              styleMethod.value,
        floor_plan_path:           floorPlanPath.value || undefined,
        scene_graph:               sceneGraph.value || undefined,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId === currentRequestId) result.value = data
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

function handleConfirmStyle(candidate) { confirmedStyle.value = candidate }
function handleClearConfirmedStyle()   { confirmedStyle.value = null }
function handleChangeRetrievalMode(nextMode) {
  if (nextMode === styleRetrievalMode.value) return
  styleRetrievalMode.value = nextMode
  fetchStyleCandidates()
}

function resetToStep1() {
  designStep.value = 1
  floorPlanUrl.value = ''
  floorPlanPath.value = ''
  sceneGraph.value = null
  result.value = null
  error.value = ''
  styleCandidates.value = []
  candidatesSearched.value = false
  confirmedStyle.value = null
  matchedStylePreview.value = null
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
      </div>

      <div class="sidebar-body">
        <SidebarForm
          :designStep="designStep"
          :floorPlanUrl="floorPlanUrl"
          v-model:roomType="roomType"
          v-model:spaceSizePing="spaceSizePing"
          v-model:furnitureItems="furnitureItems"
          v-model:extraPrompt="extraPrompt"
          v-model:familyNeeds="familyNeeds"
          v-model:fengshuiRules="fengshuiRules"
          v-model:selectedStyle="selectedStyle"
          v-model:noStyleReference="noStyleReference"
          v-model:styleMethod="styleMethod"
          :styleRefImage="styleRefImage"
          :styleOptions="styleOptions"
          :styleLoading="styleLoading"
          :styleError="styleError"
          :matchedStylePreview="matchedStylePreview"
          :loading="loading"
          :error="error"
          @submit-layout="handleSubmitLayout"
          @submit-3d="handleSubmit3D"
          @retry-style-options="fetchStyleOptions"
        />
      </div>
    </aside>

    <RouterLink to="/history" class="history-fab" title="歷史紀錄">
      <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
      </svg>
    </RouterLink>

    <main class="content">

      <!-- Step 1: empty / loading -->
      <template v-if="designStep === 1">
        <div v-if="loading" class="center-state">
          <div class="loading-ring"><div class="loading-spinner"></div><div class="loading-mark">✦</div></div>
          <p class="loading-title">生成 2D 平面圖中</p>
          <p class="loading-sub">AI 計算家具配置，通常約 10 秒</p>
        </div>
        <div v-else class="placeholder">
          <div class="placeholder-inner">
            <div class="placeholder-icon">📐</div>
            <h2>設計你的空間</h2>
            <p>在左側填入坪數與預計擺放的家具，AI 會先生成 2D 平面配置圖，再進入風格選取與 3D 渲染</p>
          </div>
        </div>
      </template>

      <!-- Step 2 content -->
      <template v-else>

        <!-- Loading 3D -->
        <div v-if="loading" class="center-state">
          <div class="loading-ring"><div class="loading-spinner"></div><div class="loading-mark">✦</div></div>
          <p class="loading-title">生成 3D 渲染圖中</p>
          <p class="loading-sub">AI 將 2D 平面圖轉換為立體室內透視，通常約 30–60 秒</p>
        </div>

        <!-- 3D result -->
        <ResultPanel v-else-if="result" :key="submitKey" :result="result" :loading="false" />

        <!-- Between step 1 and 2: show floor plan + style suggestions -->
        <template v-else>
          <!-- Floor plan big preview -->
          <div v-if="floorPlanUrl" class="floor-plan-hero">
            <div class="fp-hero-label">
              <span>2D 平面配置圖</span>
              <button class="back-btn" @click="resetToStep1">← 重新規劃</button>
            </div>
            <img :src="floorPlanUrl" alt="2D 平面配置圖" class="fp-hero-img" />
            <p class="fp-hero-hint">在左側選擇風格，點選「生成 3D 渲染圖」</p>
          </div>

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
        </template>

      </template>

    </main>
  </div>
</template>

<style scoped>
.page {
  display: flex; min-height: 100vh;
  background:
    radial-gradient(ellipse at 12% 20%, rgba(200,160,110,0.18) 0%, transparent 48%),
    radial-gradient(ellipse at 88% 80%, rgba(160,120,80,0.14) 0%, transparent 48%),
    linear-gradient(150deg, #fdf6ee 0%, #f5e8d8 45%, #ede0cf 100%);
}

/* ── Sidebar ── */
.sidebar {
  width: 500px; min-width: 420px;
  background: rgba(255,248,240,0.88);
  backdrop-filter: blur(18px);
  border-right: 1px solid var(--surface-border);
  display: flex; flex-direction: column; overflow-y: auto;
}
.sidebar-header {
  padding: 1.75rem 2rem 1.25rem;
  border-bottom: 1px solid rgba(180,140,100,0.14);
  flex-shrink: 0;
}
.sidebar-body { flex: 1; padding: 1.5rem 2rem 2rem; overflow-y: auto; }
.logo-img { height: auto; width: 200px; display: block; }

/* ── Content ── */
.content {
  flex: 1; min-width: 0; padding: 2.5rem 3rem;
  display: flex; flex-direction: column;
}

/* ── Center states ── */
.center-state, .placeholder {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 1rem;
}
.placeholder-inner { text-align: center; max-width: 480px; }
.placeholder-icon {
  width: 64px; height: 64px;
  background: linear-gradient(135deg, #f5e8d8, #e8d4b8);
  border-radius: 20px; display: flex; align-items: center; justify-content: center;
  font-size: 1.8rem; margin: 0 auto 1.5rem;
}
.placeholder-inner h2 { font-size: 1.6rem; font-weight: 800; color: var(--text-1); margin-bottom: 0.5rem; }
.placeholder-inner p  { font-size: 0.9rem; color: var(--text-3); line-height: 1.65; }

/* ── Loading ── */
.loading-ring { width: 64px; height: 64px; position: relative; margin-bottom: 0.5rem; }
.loading-spinner {
  position: absolute; inset: 0;
  border: 3px solid rgba(180,140,100,0.25);
  border-top-color: var(--primary); border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
.loading-mark {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 1.2rem; color: var(--primary);
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-title { font-size: 1.1rem; font-weight: 700; color: var(--text-1); margin: 0; }
.loading-sub   { font-size: 0.83rem; color: var(--text-3); margin: 0; }

/* ── Floor plan hero ── */
.floor-plan-hero {
  display: flex; flex-direction: column; gap: 0.75rem;
  max-width: 640px; width: 100%; margin: 0 auto;
}
.fp-hero-label {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 0.85rem; font-weight: 700; color: var(--text-2);
}
.back-btn {
  background: none; border: 1.5px solid #ccc; border-radius: 8px;
  padding: 0.3rem 0.8rem; font-size: 0.78rem; font-family: inherit;
  color: #666; cursor: pointer; transition: all 0.15s;
}
.back-btn:hover { border-color: #999; color: #333; }
.fp-hero-img {
  width: 100%; border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.12);
  border: 1px solid #ddd;
}
.fp-hero-hint { font-size: 0.8rem; color: var(--text-3); text-align: center; margin-top: 0.25rem; }

/* ── FAB ── */
.history-fab {
  position: fixed; top: 1.25rem; right: 1.5rem; z-index: 100;
  width: 40px; height: 40px; border-radius: 50%;
  background: rgba(255,248,240,0.92); backdrop-filter: blur(12px);
  border: 1px solid rgba(180,140,100,0.35);
  box-shadow: 0 2px 10px rgba(139,94,60,0.2);
  display: flex; align-items: center; justify-content: center;
  color: #8B5E3C; text-decoration: none; transition: all 0.15s;
}
.history-fab:hover { background: rgba(255,248,240,1); transform: scale(1.08); }
</style>
