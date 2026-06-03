<script setup>
import { ref, computed, onMounted } from 'vue'
import { useImageField } from '@/composables/useImageField'
import designbridgeLogo from '../../asset/designbridge_logo.svg'
import ResultPanel from '@/components/ResultPanel.vue'
import StyleSuggestions from '@/components/StyleSuggestions.vue'
import RefineCanvas from '@/components/RefineCanvas.vue'
import ImageUpload from '@/components/ImageUpload.vue'
import RoomTypePicker from '@/components/RoomTypePicker.vue'
import LifestylePicker from '@/components/LifestylePicker.vue'
import { API_BASE, apiUrl } from '@/config/api'

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────
const ROOM_TYPES = [
  { value: 'living_room', label: '客廳' },
  { value: 'bedroom',     label: '臥室' },
  { value: 'study',       label: '書房' },
  { value: 'kitchen',     label: '廚房' },
  { value: 'bathroom',    label: '浴室' },
  { value: 'whole',       label: '全室' },
]
const AREA_RANGES = [
  { value: '<10',   label: '< 10 坪' },
  { value: '10–20', label: '10–20 坪' },
  { value: '20–30', label: '20–30 坪' },
  { value: '30+',   label: '30+ 坪' },
]
const LIFESTYLE_OPTIONS = [
  { value: 'children',       label: '親子家庭' },
  { value: 'pets',           label: '寵物友善' },
  { value: 'work_from_home', label: '在家工作' },
  { value: 'elderly',        label: '長者同住' },
  { value: 'likes_cooking',  label: '喜歡下廚' },
  { value: 'likes_storage',  label: '喜歡收納' },
]
const FENGSHUI_OPTIONS = [
  { value: 'bed_not_facing_door',    label: '床不對門' },
  { value: 'sofa_not_back_to_door',  label: '沙發不背門' },
  { value: 'desk_not_facing_window', label: '書桌不背窗' },
]
const STYLE_METHODS = [
  { value: 'ai_analysis', label: 'AI 分析風格',  desc: 'Gemini 解析色調，注入 prompt' },
  { value: 'redux',       label: 'FLUX.1-Redux', desc: '以圖為主做風格遷移' },
  { value: 'ipadapter',   label: 'IP-Adapter',   desc: '文字定空間，圖像注入風格' },
]

// ─────────────────────────────────────────────
// Mode & Step
// ─────────────────────────────────────────────
const appMode    = ref('design')  // 'design' | 'refine'
const wizardStep = ref(1)         // 1–3

// ─────────────────────────────────────────────
// Step 1 — Space
// ─────────────────────────────────────────────
const roomType  = ref('')
const areaRange = ref('')
const spaceImage = useImageField()

// ─────────────────────────────────────────────
// Step 2 — Requirements
// ─────────────────────────────────────────────
const textPrompt    = ref('')
const familyNeeds   = ref([])
const fengshuiRules = ref([])

// ─────────────────────────────────────────────
// Step 2 — Style  (auto-search + optional category filter / upload override)
// ─────────────────────────────────────────────
const selectedStyle    = ref('auto')
const styleOptions     = ref([{ label: '自動', value: 'auto' }])
const styleLoading     = ref(false)
const styleError       = ref('')
const styleMethod      = ref('ai_analysis')
const styleCandidates  = ref([])
const candidatesLoading = ref(false)
const confirmedStyle   = ref(null)
const styleRefImage    = useImageField()

// ─────────────────────────────────────────────
// Generation & Result
// ─────────────────────────────────────────────
const outputAspect       = ref('auto')
const result             = ref(null)
const loading            = ref(false)
const error              = ref('')
let   currentRequestId   = 0
const submitKey          = ref(0)
const lastGeneratedImage = ref(null)   // { path, url }

// ─────────────────────────────────────────────
// Refine mode
// ─────────────────────────────────────────────
const refinePrompt   = ref('')
const brushSize      = ref(32)
const drawMode       = ref('draw')
const refineCanvasRef = ref(null)
const manualMaskPath  = ref('')

// ─────────────────────────────────────────────
// Computed
// ─────────────────────────────────────────────
const editScope = computed(() => spaceImage.file ? 0.5 : 0.7)

const noStyleReference = computed(() => !confirmedStyle.value && !styleRefImage.file)

const baseImagePreview = computed(() =>
  lastGeneratedImage.value?.url || spaceImage.preview || null
)

const hasStyleOverride = computed(() =>
  !!confirmedStyle.value || !!styleRefImage.file || selectedStyle.value !== 'auto'
)

const routingLabel = computed(() => {
  const r = result.value?.routing_decision
  return r === 'design' ? '整體設計' : r === 'design_adjuster' ? '局部微調' : ''
})

const step1Summary = computed(() => {
  const parts = []
  const rt = ROOM_TYPES.find(r => r.value === roomType.value)
  if (rt) parts.push(rt.label)
  if (areaRange.value) parts.push(areaRange.value + ' 坪')
  if (spaceImage.file) parts.push('已附空間照')
  return parts.join(' · ') || '（未填寫）'
})

const allConstraints = computed(() => {
  const allOpts = [...LIFESTYLE_OPTIONS, ...FENGSHUI_OPTIONS]
  return [...familyNeeds.value, ...fengshuiRules.value]
    .map(v => allOpts.find(o => o.value === v)?.label || v)
    .join('、')
})

const showAdvanced = ref(false)

const styleSummary = computed(() => {
  if (styleRefImage.file) return '上傳的參考圖'
  if (confirmedStyle.value) return `AI 推薦：${confirmedStyle.value.style_name || '已選'}`
  if (selectedStyle.value !== 'auto') {
    const opt = styleOptions.value.find(o => o.value === selectedStyle.value)
    return opt?.label || selectedStyle.value
  }
  return '略過，不套用'
})

// ─────────────────────────────────────────────
// Wizard Navigation
// ─────────────────────────────────────────────
function setStep(n) {
  if (n === 2) {
    styleCandidates.value = []
    confirmedStyle.value  = null
    searchStyleCandidates()
  }
  wizardStep.value = n
}

const prevStep = () => wizardStep.value > 1 && setStep(wizardStep.value - 1)
const nextStep = () => wizardStep.value < 3 && setStep(wizardStep.value + 1)

// ─────────────────────────────────────────────
// Style Search (Step 2 — auto-search from Step 1 context)
// ─────────────────────────────────────────────
async function searchStyleCandidates(shuffle = false) {
  const parts = []
  const rt = ROOM_TYPES.find(r => r.value === roomType.value)
  if (rt) parts.push(rt.label)
  if (areaRange.value) parts.push(areaRange.value + '坪')
  if (textPrompt.value.trim()) parts.push(textPrompt.value.trim())
  const q = parts.join(' ')
  if (!q) return

  candidatesLoading.value = true
  confirmedStyle.value    = null
  try {
    const sid = selectedStyle.value !== 'auto' ? selectedStyle.value : ''
    const qs  = `/api/style-search?query=${encodeURIComponent(q)}&top_k=12&retrieval_mode=text-to-text${sid ? `&style_id=${encodeURIComponent(sid)}` : ''}`
    const res = await fetch(apiUrl(qs))
    if (res.ok) {
      const data = await res.json()
      let sorted = (Array.isArray(data) ? data : [])
        .sort((a, b) => Number(b?.similarity ?? 0) - Number(a?.similarity ?? 0))
      if (shuffle) sorted = [...sorted].sort(() => Math.random() - 0.5)
      styleCandidates.value = sorted.slice(0, 6)
    }
  } catch {}
  finally { candidatesLoading.value = false }
}

function onCategoryChange(styleId) {
  selectedStyle.value   = styleId
  confirmedStyle.value  = null
  styleCandidates.value = []
  searchStyleCandidates()
}

function onRecommendSimilar(candidate) {
  onCategoryChange(candidate.style_id)
}

function handleStyleRefImageChange(e) {
  styleRefImage.onChange(e)
  confirmedStyle.value = null
}

// ─────────────────────────────────────────────
// Backend helpers
// ─────────────────────────────────────────────
async function waitForBackend(maxWaitMs = 120000, intervalMs = 2000) {
  const deadline = Date.now() + maxWaitMs
  while (Date.now() < deadline) {
    try {
      const ctrl  = new AbortController()
      const timer = setTimeout(() => ctrl.abort(), 4000)
      const res   = await fetch(apiUrl('/api/health'), { signal: ctrl.signal })
      clearTimeout(timer)
      if (res.ok) return true
    } catch { /* still starting */ }
    styleError.value = '等待後端啟動中…（請確認已執行 uvicorn api:app）'
    await new Promise(r => setTimeout(r, intervalMs))
  }
  return false
}

async function fetchStyleOptions() {
  styleLoading.value = true
  styleError.value   = ''
  if (!(await waitForBackend())) {
    styleError.value   = '無法連線後端，請確認伺服器已啟動'
    styleLoading.value = false
    return
  }
  try {
    const res = await fetch(apiUrl('/api/style-profiles'))
    if (!res.ok) throw new Error()
    const data = await res.json()
    styleOptions.value = [
      { label: '自動', value: 'auto' },
      ...data.map(({ style_name, style_id }) => ({ label: style_name, value: style_id })),
    ]
    styleError.value = ''
  } catch {
    styleError.value = '無法載入風格選項，請稍後重試'
  } finally {
    styleLoading.value = false
  }
}

async function uploadFile(file) {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(apiUrl('/api/upload-image'), { method: 'POST', body })
  if (!res.ok) throw new Error(`${res.status}`)
  return (await res.json()).path
}

// ─────────────────────────────────────────────
// Generate Design (Wizard Step 4)
// ─────────────────────────────────────────────
async function handleGenerate() {
  const requestId = ++currentRequestId
  submitKey.value++
  error.value  = ''
  result.value = null
  loading.value = true

  // Prefix prompt with spatial context
  const ctxParts = []
  const rt = ROOM_TYPES.find(r => r.value === roomType.value)
  if (rt) ctxParts.push(rt.label)
  if (areaRange.value) ctxParts.push(areaRange.value + '坪')
  const fullPrompt = ctxParts.length
    ? `[${ctxParts.join('，')}] ${textPrompt.value}`
    : textPrompt.value

  try {
    const initial_image_path = spaceImage.file
      ? await uploadFile(spaceImage.file)
      : undefined

    let style_reference_image_path
    if (styleRefImage.file)
      style_reference_image_path = await uploadFile(styleRefImage.file)
    else if (confirmedStyle.value?.image_url)
      style_reference_image_path = confirmedStyle.value.image_url

    const style_profile_id = selectedStyle.value !== 'auto' ? selectedStyle.value : undefined

    const res = await fetch(apiUrl('/api/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt:             fullPrompt,
        edit_scope:              editScope.value,
        style_profile_id,
        initial_image_path,
        style_reference_image_path,
        no_style_reference:      noStyleReference.value,
        refine_mode:             false,
        output_aspect:           outputAspect.value,
        style_retrieval_mode:    'text-to-text',
        family_needs:            familyNeeds.value,
        fengshui_rules:          fengshuiRules.value,
        style_method:            styleMethod.value,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId === currentRequestId) {
      result.value = data
      if (data.generated_image_path) {
        lastGeneratedImage.value = {
          path: data.generated_image_path,
          url:  data.generated_image_url || null,
        }
      }
    }
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

// ─────────────────────────────────────────────
// Refine Submit (Inpaint)
// ─────────────────────────────────────────────
async function handleRefineSubmit() {
  if (!refinePrompt.value.trim()) { error.value = '請輸入調整需求'; return }
  const requestId = ++currentRequestId
  error.value  = ''
  result.value = null
  loading.value = true
  try {
    let mask_image_path
    const maskBlob = await refineCanvasRef.value?.getMaskBlob()
    if (maskBlob) {
      mask_image_path      = await uploadFile(new File([maskBlob], 'mask.png', { type: 'image/png' }))
      manualMaskPath.value = mask_image_path
    }
    const initial_image_path = lastGeneratedImage.value?.path
      || (spaceImage.file ? await uploadFile(spaceImage.file) : undefined)

    const res = await fetch(apiUrl('/api/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt:        refinePrompt.value,
        edit_scope:         0.25,
        initial_image_path,
        no_style_reference: true,
        refine_mode:        true,
        output_aspect:      'auto',
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
          url:  data.generated_image_url || null,
        }
      }
    }
  } catch (e) {
    if (requestId === currentRequestId) error.value = e.message
  } finally {
    if (requestId === currentRequestId) loading.value = false
  }
}

// ─────────────────────────────────────────────
// Misc helpers
// ─────────────────────────────────────────────
function enterRefineMode() {
  if (!lastGeneratedImage.value?.url && !spaceImage.preview) return
  appMode.value = 'refine'
  result.value  = null
  error.value   = ''
}

function exitRefineMode() {
  appMode.value = 'design'
  wizardStep.value = 3
  error.value = ''
}

function toggleFengshuiRule(v) {
  const i = fengshuiRules.value.indexOf(v)
  i === -1 ? fengshuiRules.value.push(v) : fengshuiRules.value.splice(i, 1)
}

onMounted(fetchStyleOptions)
</script>

<template>
  <div class="page">

    <!-- ════════════════════════════════ SIDEBAR ════════════════════════════════ -->
    <aside class="sidebar">

      <!-- ── Header ── -->
      <div class="sidebar-header">
        <div class="logo">
          <img :src="designbridgeLogo" alt="DesignBridge" class="logo-img" />
          <p class="logo-tagline">AI 室內設計助手</p>
        </div>
      </div>

      <!-- ═══════════════════════ DESIGN WIZARD ═══════════════════════ -->
      <template v-if="appMode === 'design'">

        <!-- Scrollable Step content -->
        <div class="sidebar-body">

          <!-- ─── Step 1 — Space & Requirements ─── -->
          <div v-show="wizardStep === 1" class="step-content">

            <div class="field">
              <label class="field-label">空間類型</label>
              <RoomTypePicker v-model="roomType" />
            </div>

            <div class="field">
              <label class="field-label">坪數</label>
              <div class="chip-group">
                <button
                  v-for="opt in AREA_RANGES" :key="opt.value"
                  type="button"
                  :class="['chip', { active: areaRange === opt.value }]"
                  @click="areaRange = areaRange === opt.value ? '' : opt.value"
                >{{ opt.label }}</button>
              </div>
            </div>

            <div class="field">
              <label class="field-label">
                設計需求
                <span class="badge-required">建議必填</span>
              </label>
              <textarea
                v-model="textPrompt"
                rows="3"
                placeholder="例如：回家就想放鬆的客廳，喜歡北歐風、木質感與暖色調，希望有充足的收納空間..."
              />
            </div>

            <div class="field">
              <label class="field-label">
                空間照片
                <span class="badge-optional">選填</span>
              </label>
              <ImageUpload
                label="點擊或拖曳上傳"
                icon="📷"
                hint="有照片可保留格局；無照片將依描述從頭想像"
                :preview="spaceImage.preview"
                @change="spaceImage.onChange"
                @remove="spaceImage.remove"
              />
            </div>

            <div class="advanced-wrapper">
              <button
                type="button"
                class="advanced-toggle"
                :aria-expanded="showAdvanced"
                @click="showAdvanced = !showAdvanced"
              >
                <span class="advanced-toggle-main">
                  <span class="advanced-toggle-title">進階設定</span>
                  <span class="badge-optional">選填</span>
                </span>
                <span class="advanced-toggle-right">
                  <span
                    v-if="!showAdvanced && allConstraints"
                    class="advanced-summary-text"
                  >{{ allConstraints }}</span>
                  <span
                    v-else-if="!showAdvanced"
                    class="advanced-summary-muted"
                  >生活型態、風水</span>
                  <svg
                    class="advanced-arrow"
                    :class="{ open: showAdvanced }"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </span>
              </button>

              <div v-show="showAdvanced" class="advanced-panel">
                <div class="field">
                  <label class="field-label field-label--sub">
                    生活型態
                    <span class="badge-optional">可多選</span>
                  </label>
                  <LifestylePicker v-model="familyNeeds" />
                </div>

                <div class="field">
                  <label class="field-label field-label--sub">風水需求</label>
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
              </div>
            </div>
          </div>

          <!-- ─── Step 2 — Style Reference ─── -->
          <div v-show="wizardStep === 2" class="step-content">
            

            <!-- Upload your own reference image -->
            <div class="upload-section">
              <p class="upload-section-label">上傳自己的參考圖</p>
              <ImageUpload
                label="點擊或拖曳上傳"
                icon="🖼️"
                hint="AI 會參考其色調與氛圍，覆蓋右側推薦"
                :preview="styleRefImage.preview"
                @change="handleStyleRefImageChange"
                @remove="styleRefImage.remove"
              />
              <div v-if="styleRefImage.file" class="field" style="margin-top:0.75rem">
                <label class="field-label">套用方式</label>
                <div class="method-list">
                  <label
                    v-for="m in STYLE_METHODS" :key="m.value"
                    :class="['method-item', { active: styleMethod === m.value }]"
                  >
                    <input type="radio" v-model="styleMethod" :value="m.value" />
                    <div class="method-text">
                      <strong>{{ m.label }}</strong>
                      <small>{{ m.desc }}</small>
                    </div>
                  </label>
                </div>
              </div>
            </div>

            <p class="step-footer-hint">不需要風格參考？直接點「下一步」略過</p>
          </div>

          <!-- ─── Step 3 — Confirm ─── -->
          <div v-show="wizardStep === 3" class="step-content">
            <p class="step-title">確認並生成</p>

            <div class="summary-card">
              <div class="summary-row">
                <span class="summary-label">空間</span>
                <span class="summary-value">{{ step1Summary }}</span>
              </div>
              <div class="summary-row">
                <span class="summary-label">需求</span>
                <span class="summary-value summary-clamp">{{ textPrompt || '（未填寫）' }}</span>
              </div>
              <div v-if="allConstraints" class="summary-row">
                <span class="summary-label">進階偏好</span>
                <span class="summary-value">{{ allConstraints }}</span>
              </div>
              <div class="summary-row">
                <span class="summary-label">風格</span>
                <span class="summary-value">{{ styleSummary }}</span>
              </div>
            </div>

            <div class="field">
              <label class="field-label">輸出比例</label>
              <div class="chip-group">
                <button
                  v-for="opt in [
                    { value: 'auto',  label: '自動' },
                    { value: '1:1',   label: '1:1' },
                    { value: '4:3',   label: '4:3' },
                    { value: '3:4',   label: '3:4' },
                    { value: '16:9',  label: '16:9' },
                    { value: '9:16',  label: '9:16' },
                  ]"
                  :key="opt.value"
                  type="button"
                  class="chip"
                  :class="{ active: outputAspect === opt.value }"
                  @click="outputAspect = opt.value"
                >{{ opt.label }}</button>
              </div>
            </div>
          </div>

        </div><!-- /sidebar-body -->

        <!-- Wizard Navigation -->
        <div class="wizard-nav">
          <p v-if="error && wizardStep === 3" class="error-msg">{{ error }}</p>
          <div class="nav-btns">
            <button
              v-if="wizardStep > 1"
              type="button"
              class="nav-back"
              @click="prevStep"
            >← 上一步</button>
            <button
              v-if="wizardStep < 3"
              type="button"
              class="nav-next"
              @click="nextStep"
            >下一步 →</button>
            <button
              v-if="wizardStep === 3"
              type="button"
              class="submit-btn"
              :disabled="loading"
              @click="handleGenerate"
            >
              <span v-if="loading" class="spinner"></span>
              {{ loading ? 'AI 生成中...' : '生成設計圖' }}
            </button>
          </div>
        </div>

      </template><!-- /design wizard -->

      <!-- ═══════════════════════ REFINE MODE ═══════════════════════ -->
      <template v-else>
        <div class="sidebar-body">
          <button type="button" class="refine-back" @click="exitRefineMode">← 返回設計流程</button>
          <p class="step-title" style="padding-top:0.25rem">指定區域修改</p>
          <p class="step-desc">塗抹右側畫布中想修改的區域，輸入需求後生成</p>

          <div class="field">
            <label class="field-label">
              空間圖片
              <span v-if="lastGeneratedImage" class="badge-optional">已附上次生成圖</span>
            </label>
            <div v-if="lastGeneratedImage?.url" class="base-thumb">
              <img :src="lastGeneratedImage.url" alt="基底圖" />
              <span class="base-thumb-label">上次生成圖</span>
            </div>
            <ImageUpload
              v-else
              label="上傳空間圖片（必填）"
              icon="📷"
              :preview="spaceImage.preview"
              @change="spaceImage.onChange"
              @remove="spaceImage.remove"
            />
          </div>

          <div class="field">
            <label class="field-label">
              調整需求
              <span class="badge-required">必填</span>
            </label>
            <textarea
              v-model="refinePrompt"
              rows="4"
              placeholder="例如：把沙發換成藍色布藝款式，窗簾改為白色薄紗..."
            />
          </div>

          <div v-if="baseImagePreview" class="field">
            <label class="field-label">畫筆工具</label>
            <div class="brush-toolbar">
              <div class="brush-btns">
                <button :class="['brush-tool', { active: drawMode === 'draw' }]"  type="button" @click="drawMode = 'draw'">畫筆</button>
                <button :class="['brush-tool', { active: drawMode === 'erase' }]" type="button" @click="drawMode = 'erase'">橡皮擦</button>
              </div>
              <label class="brush-size-label">
                筆刷 {{ brushSize }}px
                <input type="range" v-model.number="brushSize" min="5" max="120" step="5" class="brush-range" />
              </label>
            </div>
          </div>
        </div>

        <div class="wizard-nav">
          <p v-if="error" class="error-msg">{{ error }}</p>
          <div class="nav-btns">
            <button
              type="button"
              class="submit-btn"
              :disabled="loading || !baseImagePreview"
              @click="handleRefineSubmit"
            >
              <span v-if="loading" class="spinner"></span>
              {{ loading ? 'AI 生成中...' : '開始修改' }}
            </button>
          </div>
        </div>
      </template>

    </aside><!-- /sidebar -->

    <!-- History FAB -->
    <RouterLink to="/history" class="history-fab" title="歷史紀錄">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <polyline points="12 6 12 12 16 14"/>
      </svg>
      <span class="history-fab-label">歷史紀錄</span>
    </RouterLink>

    <!-- ════════════════════════════ RIGHT CONTENT ════════════════════════════ -->
    <main class="content">

      <!-- ── Refine mode ── -->
      <template v-if="appMode === 'refine'">
        <div v-if="loading" class="state-center">
          <div class="spinner-lg"></div>
          <span class="state-label">AI 生成中...</span>
        </div>
        <div v-else-if="result?.generated_image_url" class="refine-result-area">
          <div class="refine-result-hd">
            <span class="result-label">生成結果</span>
            <button class="continue-btn" @click="result = null">繼續編輯</button>
          </div>
          <img :src="result.generated_image_url" class="refine-result-img" alt="生成結果" />
        </div>
        <RefineCanvas
          v-else-if="baseImagePreview"
          ref="refineCanvasRef"
          :imageUrl="baseImagePreview"
          :brushSize="brushSize"
          :drawMode="drawMode"
          class="refine-canvas-fill"
        />
        <div v-else class="state-center">
          <div class="ph-icon">✦</div>
          <h3 class="ph-title">在左側上傳空間圖片</h3>
          <p class="ph-desc">上傳後，在畫布上塗抹想修改的區域，輸入需求即可生成</p>
        </div>
      </template>

      <!-- ── Design mode ── -->
      <template v-else>

        <!-- Step 1: preview or hint -->
        <template v-if="wizardStep === 1">
          <div v-if="spaceImage.preview" class="space-preview-wrap">
            <img :src="spaceImage.preview" class="space-preview-img" alt="空間預覽" />
            <span class="space-preview-label">空間照片預覽</span>
          </div>
          <div v-else class="state-center">
            <div class="ph-icon">🏠</div>
            <h3 class="ph-title">填寫空間資訊與需求</h3>
            <p class="ph-desc">選擇空間類型、坪數，輸入設計需求，並可選填空間照片、家庭與風水條件</p>
          </div>
        </template>

        <!-- Step 2: style selection -->
        <template v-else-if="wizardStep === 2">
          <!-- Upload override: show the uploaded image as reference preview -->
          <div v-if="styleRefImage.file" class="upload-ref-wrap">
            <img :src="styleRefImage.preview" class="upload-ref-img" alt="風格參考圖" />
            <span class="upload-ref-label">自訂風格參考圖</span>
          </div>
          <!-- Default: show AI-recommended suggestions grid -->
          <StyleSuggestions
            v-else
            :candidates="styleCandidates"
            :confirmed="confirmedStyle"
            :loading="candidatesLoading"
            :api-base="API_BASE"
            :style-options="styleOptions"
            :selected-style="selectedStyle"
            :show-rebatch="styleCandidates.length > 0 && !styleRefImage.file"
            :rebatch-loading="candidatesLoading"
            @confirm="confirmedStyle = $event"
            @clear="confirmedStyle = null"
            @filter-change="onCategoryChange"
            @rebatch="searchStyleCandidates(true)"
            @recommend-similar="onRecommendSimilar"
          />
        </template>

        <!-- Step 3: confirm + result -->
        <template v-else>
          <div class="result-outer">
            <ResultPanel :key="submitKey" :result="result" :loading="loading" />
            <div v-if="result?.generated_image_url" class="post-result-bar">
              <div v-if="routingLabel" class="routing-chip">
                AI 判斷：{{ routingLabel }}
              </div>
              <button type="button" class="refine-action-btn" @click="enterRefineMode">
                指定區域修改 →
              </button>
            </div>
          </div>
        </template>

      </template>

    </main>
  </div>
</template>

<style scoped>
/* ─────────────────── Layout ─────────────────── */
.page {
  display: flex;
  min-height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 12% 20%, rgba(200, 160, 110, 0.18) 0%, transparent 48%),
    radial-gradient(ellipse at 88% 80%, rgba(160, 120, 80, 0.14) 0%, transparent 48%),
    linear-gradient(150deg, #fdf6ee 0%, #f5e8d8 45%, #ede0cf 100%);
}

/* ─────────────────── Sidebar ─────────────────── */
.sidebar {
  width: 580px;
  min-width: 480px;
  height: 100dvh;
  background: rgba(255, 250, 244, 0.96);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: none;
  border-radius: 0 28px 28px 0;
  box-shadow:
    6px 0 24px rgba(160, 110, 60, 0.10),
    2px 0 6px rgba(160, 110, 60, 0.07);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: sticky;
  top: 0;
  flex-shrink: 0;
  z-index: 2;
}

.sidebar-header {
  padding: 1.1rem 1.5rem 0.85rem;
  border-bottom: 1px solid rgba(180, 140, 100, 0.14);
  flex-shrink: 0;
}

.logo { margin-bottom: 0.65rem; }
.logo-img { width: 160px; height: auto; display: block; }
.logo-tagline {
  margin: 0.25rem 0 0;
  padding-left: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
  color: #a07850;
  letter-spacing: 0.02em;
}

.refine-back {
  align-self: flex-start;
  padding: 0.45rem 0.75rem;
  border: 1.5px solid var(--primary-border);
  border-radius: 8px;
  background: transparent;
  color: var(--primary);
  font-size: 0.82rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s;
}
.refine-back:hover {
  background: var(--primary-subtle);
  border-color: var(--primary);
}

/* ─────────────────── Sidebar Body ─────────────────── */
.sidebar-body {
  flex: 1;
  min-height: 0;
  padding: 0.9rem 1.5rem 0.75rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

/* ─────────────────── Step Content ─────────────────── */
.step-content { display: flex; flex-direction: column; gap: 0.85rem; }

.step-title {
  font-size: 1.15rem;
  font-weight: 800;
  color: #4a2e14;
  letter-spacing: -0.01em;
  margin: 0;
}
.step-desc {
  font-size: 0.88rem;
  color: #a07850;
  margin: -0.6rem 0 0;
}

/* ─────────────────── Field ─────────────────── */
.field { display: flex; flex-direction: column; gap: 0.5rem; }

.field-label {
  font-size: 1.08rem;
  font-weight: 700;
  color: #4a3018;
  display: flex;
  align-items: center;
  gap: 0.45rem;
  letter-spacing: -0.01em;
}

.badge-optional {
  font-size: 0.8rem;
  font-weight: 500;
  color: #a07850;
  background: rgba(139, 94, 60, 0.08);
  padding: 0.12rem 0.5rem;
  border-radius: 99px;
}
.badge-required {
  font-size: 0.8rem;
  font-weight: 600;
  color: #b07030;
  background: rgba(176, 112, 48, 0.1);
  padding: 0.12rem 0.5rem;
  border-radius: 99px;
}

/* Textarea */
textarea {
  padding: 0.7rem 0.9rem;
  border: 1.5px solid #ddd0c0;
  border-radius: 10px;
  resize: none;
  font-size: 0.98rem;
  font-family: inherit;
  color: #3a2010;
  line-height: 1.6;
  transition: border-color 0.18s, box-shadow 0.18s;
  background: rgba(255, 250, 243, 0.75);
}
textarea:focus {
  outline: none;
  border-color: #8B5E3C;
  background: #fffaf5;
  box-shadow: 0 0 0 3px rgba(139, 94, 60, 0.09);
}
textarea::placeholder { color: #c8a882; }

/* Select */
select {
  padding: 0.65rem 0.9rem;
  border: 1.5px solid #ddd0c0;
  border-radius: 10px;
  font-size: 0.95rem;
  font-family: inherit;
  background: rgba(255, 250, 243, 0.75);
  color: #3a2010;
  cursor: pointer;
  transition: border-color 0.18s;
  appearance: auto;
}
select:focus { outline: none; border-color: #8B5E3C; background: #fffaf5; }

/* Chips */
.chip-group { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.chip {
  padding: 0.48rem 1rem;
  border: 1.5px solid #d0c0a8;
  border-radius: 99px;
  font-size: 0.96rem;
  font-family: inherit;
  font-weight: 500;
  color: #6b4a28;
  background: rgba(255, 250, 243, 0.8);
  cursor: pointer;
  transition: all 0.15s;
  line-height: 1.4;
}
.chip:hover { border-color: #a07850; color: #3a2010; }
.chip.active {
  border-color: transparent;
  background: var(--btn-gradient);
  color: #fff;
  font-weight: 600;
  box-shadow: var(--btn-shadow);
}

/* ─────────────────── Advanced settings ─────────────────── */
.advanced-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 0.15rem;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  width: 100%;
  padding: 0.7rem 0.9rem;
  border: 1.5px solid #e5d9cc;
  border-radius: 12px;
  background: rgba(255, 252, 247, 0.95);
  color: #5c4030;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s, border-color 0.18s, box-shadow 0.18s;
  text-align: left;
}

.advanced-toggle:hover {
  border-color: var(--primary-border);
  background: #fff;
}

.advanced-toggle[aria-expanded="true"] {
  border-color: var(--primary-border);
  background: #fff;
  box-shadow: 0 2px 10px rgba(168, 135, 104, 0.1);
  border-bottom-left-radius: 0;
  border-bottom-right-radius: 0;
}

.advanced-toggle-main {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-shrink: 0;
}

.advanced-toggle-title {
  font-size: 1rem;
  font-weight: 700;
  color: #4a3018;
}

.advanced-toggle-right {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  min-width: 0;
  flex: 1;
  justify-content: flex-end;
}

.advanced-summary-text {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 220px;
}

.advanced-summary-muted {
  font-size: 0.78rem;
  color: #a07850;
  white-space: nowrap;
}

.advanced-arrow {
  flex-shrink: 0;
  color: #a07850;
  transition: transform 0.22s ease;
}

.advanced-arrow.open {
  transform: rotate(180deg);
}

.advanced-panel {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  padding: 0.85rem 0.9rem 0.95rem;
  border: 1.5px solid var(--primary-border);
  border-top: none;
  border-radius: 0 0 12px 12px;
  background: rgba(255, 252, 247, 0.6);
}

.field-label--sub {
  font-size: 0.98rem;
}

/* Status */
.status-hint  { font-size: 0.88rem; color: #a07850; }
.status-error-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.status-error { font-size: 0.88rem; color: #c0392b; flex: 1; }
.retry-btn {
  flex-shrink: 0;
  padding: 0.22rem 0.6rem;
  border: 1px solid #e0b4b4;
  border-radius: 6px;
  background: #fff5f5;
  color: #c0392b;
  font-size: 0.73rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
}
.retry-btn:hover:not(:disabled) { background: #ffe8e8; }
.retry-btn:disabled { opacity: 0.55; cursor: not-allowed; }

/* ─────────────────── Style Status Block (Step 2) ─────────────────── */
.style-status-block {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.75rem 0.9rem;
  background: rgba(139, 94, 60, 0.05);
  border: 1px solid #d4c0a8;
  border-radius: 10px;
  min-height: 2.8rem;
}

@keyframes spin-auto { to { transform: rotate(360deg); } }
.auto-spinner {
  width: 16px; height: 16px;
  border: 2px solid #d4c0a8;
  border-top-color: #8B5E3C;
  border-radius: 50%;
  animation: spin-auto 0.7s linear infinite;
  flex-shrink: 0;
}
.auto-status-icon { font-size: 1rem; flex-shrink: 0; }
.auto-status-text { font-size: 0.88rem; color: #6b4a28; }
.auto-status-text.muted { color: #a07850; }

/* Confirmed card (thumbnail) */
.confirmed-card {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
}
.confirmed-thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: 6px;
  border: 1.5px solid #c8a882;
  flex-shrink: 0;
}
.confirmed-info { flex: 1; min-width: 0; }
.confirmed-meta { display: block; font-size: 0.72rem; color: #a07850; }
.confirmed-name { display: block; font-size: 0.9rem; font-weight: 700; color: #3a2010; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.confirmed-clear {
  background: none;
  border: none;
  color: #a07850;
  cursor: pointer;
  font-size: 0.9rem;
  padding: 0.2rem;
  line-height: 1;
  flex-shrink: 0;
  border-radius: 50%;
  transition: color 0.15s, background 0.15s;
}
.confirmed-clear:hover { color: #8B5E3C; background: rgba(139,94,60,0.1); }

/* Rebatch */

/* Upload section in Step 2 sidebar */
.upload-section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding-top: 0.25rem;
}
.upload-section-label {
  font-size: 1.08rem;
  font-weight: 700;
  color: #4a3018;
  margin: 0;
  letter-spacing: -0.01em;
}

/* Step footer hint */
.step-footer-hint {
  font-size: 0.82rem;
  color: #b09070;
  text-align: center;
  margin: 0;
}

/* Style method */
.method-field { margin-top: 0.25rem; }
.method-list { display: flex; flex-direction: column; gap: 0.35rem; }
.method-item {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.5rem 0.75rem;
  border: 1.5px solid #ddd0c0;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.18s;
  background: rgba(255, 250, 243, 0.65);
}
.method-item:hover { border-color: #a07850; }
.method-item.active { border-color: #8B5E3C; background: rgba(139, 94, 60, 0.06); }
.method-item input[type='radio'] { accent-color: #8B5E3C; flex-shrink: 0; }
.method-text { display: flex; flex-direction: column; gap: 0.05rem; }
.method-text strong { font-size: 0.92rem; font-weight: 700; color: #3a2010; }
.method-text small  { font-size: 0.78rem; color: #a07850; }

/* ─────────────────── Step 4 Summary ─────────────────── */
.summary-card {
  background: rgba(255, 250, 243, 0.85);
  border: 1.5px solid #d4c0a8;
  border-radius: 12px;
  padding: 0.9rem 1.05rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.summary-row { display: flex; gap: 0.75rem; align-items: flex-start; }
.summary-label {
  font-size: 0.78rem;
  font-weight: 700;
  color: #a07850;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  margin-top: 0.1rem;
  min-width: 28px;
}
.summary-value { font-size: 0.92rem; color: #3a2010; font-weight: 500; flex: 1; line-height: 1.5; }
.summary-clamp {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ─────────────────── Wizard Nav ─────────────────── */
.wizard-nav {
  flex-shrink: 0;
  padding: 0.6rem 1.5rem 1rem;
  background: linear-gradient(to top, rgba(255, 248, 240, 1) 60%, rgba(255, 248, 240, 0));
  border-top: 1px solid rgba(180, 140, 100, 0.1);
}
.nav-btns { display: flex; gap: 0.5rem; }

.nav-back {
  padding: 0.75rem 1.2rem;
  border: 1.5px solid var(--primary-border);
  border-radius: 10px;
  background: transparent;
  color: var(--primary);
  font-size: 0.95rem;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s;
  white-space: nowrap;
}
.nav-back:hover { background: var(--primary-subtle); border-color: var(--primary); }

.nav-next {
  flex: 1;
  padding: 0.75rem 1rem;
  border: none;
  border-radius: 10px;
  background: var(--btn-gradient);
  color: #fff;
  font-size: 0.97rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s;
  box-shadow: var(--btn-shadow);
}
.nav-next:hover:not(:disabled) {
  background: var(--btn-gradient-hover);
  transform: translateY(-1px);
  box-shadow: var(--btn-shadow-hover);
}

.submit-btn {
  flex: 1;
  padding: 0.8rem 1rem;
  background: var(--btn-gradient);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-size: 1.02rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  transition: all 0.2s;
  box-shadow: var(--btn-shadow);
}
.submit-btn:hover:not(:disabled) {
  background: var(--btn-gradient-hover);
  transform: translateY(-1px);
  box-shadow: var(--btn-shadow-hover);
}
.submit-btn:active:not(:disabled) { transform: translateY(0); }
.submit-btn:disabled { opacity: 0.58; cursor: not-allowed; box-shadow: none; transform: none; }

.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.75s linear infinite;
  flex-shrink: 0;
}
@keyframes spin { to { transform: rotate(360deg); } }

.error-msg {
  font-size: 0.9rem;
  color: #c0392b;
  background: #fff5f5;
  padding: 0.45rem 0.75rem;
  border-radius: 8px;
  border: 1px solid #f5c6c6;
  margin-bottom: 0.5rem;
}

/* ─────────────────── Refine Sidebar ─────────────────── */
.base-thumb {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  border: 1.5px solid #d4c0a8;
}
.base-thumb img { width: 100%; height: 130px; object-fit: cover; display: block; }
.base-thumb-label {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  padding: 0.4rem 0.65rem;
  background: linear-gradient(transparent, rgba(10, 5, 0, 0.5));
  font-size: 0.7rem;
  font-weight: 600;
  color: rgba(255,255,255,0.85);
}

.brush-toolbar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.6rem 0.75rem;
  background: rgba(0,0,0,0.03);
  border: 1.5px solid #ddd;
  border-radius: 10px;
}
.brush-btns { display: flex; gap: 0.4rem; }
.brush-tool {
  flex: 1;
  padding: 0.32rem 0;
  border: 1.5px solid #ccc;
  border-radius: 8px;
  background: #fff;
  color: #555;
  font-size: 0.78rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.brush-tool.active {
  background: var(--btn-gradient);
  color: #fff;
  border-color: transparent;
}
.brush-size-label {
  font-size: 0.73rem;
  color: #555;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.brush-range { width: 110px; accent-color: #1c1c1e; cursor: pointer; }

/* ─────────────────── History FAB ─────────────────── */
.history-fab {
  position: fixed;
  top: 1.25rem;
  right: 1.5rem;
  z-index: 100;
  height: 36px;
  padding: 0 0.9rem;
  gap: 0.4rem;
  border-radius: 99px;
  background: rgba(255, 248, 240, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(180, 140, 100, 0.35);
  box-shadow: 0 2px 10px rgba(139, 94, 60, 0.2);
  display: flex; align-items: center; justify-content: center;
  color: #8B5E3C;
  text-decoration: none;
  transition: all 0.15s;
}
.history-fab:hover { background: rgba(255, 248, 240, 1); box-shadow: 0 4px 16px rgba(139, 94, 60, 0.35); transform: translateY(-1px); }
.history-fab-label { font-size: 0.82rem; font-weight: 700; white-space: nowrap; }

/* ─────────────────── Right Content ─────────────────── */
.content {
  flex: 1;
  min-width: 0;
  padding: 2rem 2.5rem;
  display: flex;
  flex-direction: column;
}

/* ─────────────────── State Center (placeholder) ─────────────────── */
.state-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  text-align: center;
  padding: 2rem;
}
.ph-icon {
  width: 64px; height: 64px;
  background: linear-gradient(135deg, #f5e8d8, #e8d4b8);
  border-radius: 20px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.6rem;
  margin-bottom: 0.5rem;
  box-shadow: 0 4px 16px rgba(139, 94, 60, 0.15);
}
.ph-title {
  font-size: 1.35rem;
  font-weight: 800;
  color: #3a2010;
  letter-spacing: -0.02em;
  margin: 0;
}
.ph-desc {
  font-size: 0.88rem;
  color: #a07850;
  max-width: 420px;
  line-height: 1.6;
  margin: 0;
}
.state-label { font-size: 0.95rem; font-weight: 600; color: #8B5E3C; }
.spinner-lg {
  width: 44px; height: 44px;
  border: 3px solid rgba(139, 94, 60, 0.2);
  border-top-color: #8B5E3C;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* ─────────────────── Space Preview ─────────────────── */
.space-preview-wrap {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  min-height: 0;
}
.space-preview-img {
  width: 100%;
  max-height: calc(100vh - 7rem);
  object-fit: contain;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.14);
}
.space-preview-label {
  font-size: 0.75rem;
  color: #a07850;
  font-weight: 600;
  letter-spacing: 0.03em;
}

/* ─────────────────── Upload Ref Preview (Step 2) ─────────────────── */
.upload-ref-wrap {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  min-height: 0;
}
.upload-ref-img {
  width: 100%;
  max-height: calc(100vh - 7rem);
  object-fit: contain;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.14);
}
.upload-ref-label {
  font-size: 0.75rem;
  color: #a07850;
  font-weight: 600;
  letter-spacing: 0.03em;
}

/* ─────────────────── Refine mode right ─────────────────── */
.refine-canvas-fill { flex: 1; width: 100%; min-height: 0; }

.refine-result-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
  overflow-y: auto;
}
.refine-result-hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 760px;
}
.result-label { font-size: 1rem; font-weight: 700; color: #4a2e14; }
.continue-btn {
  padding: 0.38rem 0.9rem;
  border: 1.5px solid #c0c0c0;
  border-radius: 8px;
  background: transparent;
  color: #555;
  font-size: 0.8rem;
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}
.continue-btn:hover { background: #f0f0f0; }
.refine-result-img {
  width: 100%;
  max-width: 760px;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.16);
}

/* ─────────────────── Step 4 / Result ─────────────────── */
.result-outer {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  min-height: 0;
  overflow-y: auto;
}
.post-result-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.1rem 0;
}
.routing-chip {
  padding: 0.28rem 0.8rem;
  background: rgba(139, 94, 60, 0.1);
  border: 1px solid rgba(139, 94, 60, 0.25);
  border-radius: 99px;
  font-size: 0.78rem;
  font-weight: 600;
  color: #8B5E3C;
}
.refine-action-btn {
  margin-left: auto;
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: 10px;
  background: var(--btn-gradient);
  color: #fff;
  font-size: 0.9rem;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.18s;
  box-shadow: var(--btn-shadow);
}
.refine-action-btn:hover {
  background: var(--btn-gradient-hover);
  transform: translateY(-1px);
  box-shadow: var(--btn-shadow-hover);
}
</style>
