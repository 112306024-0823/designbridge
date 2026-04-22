<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { useImageField } from '@/composables/useImageField'
import SidebarForm from '@/components/SidebarForm.vue'
import ResultPanel from '@/components/ResultPanel.vue'
import StyleSuggestions from '@/components/StyleSuggestions.vue'

const API_BASE = 'http://localhost:8000'

const textPrompt = ref('')
const editScope = ref(0.6)
const modelType = ref('flux')
const selectedStyle = ref('auto')
const styleOptions = ref([{ label: '自動', value: 'auto' }])
const styleLoading = ref(false)
const styleError = ref('')
const manualImagePath = ref('')
const showManualPath = ref(false)
const spaceImage    = useImageField()
const styleRefImage = useImageField()
const result = ref(null)
const loading = ref(false)
const error = ref('')
let currentRequestId = 0  // 用來丟棄過時的回應
const submitKey = ref(0)  // 每次 submit 遞增，強制 ResultPanel 重新掛載
const matchedStylePreview = ref(null)

// 向量搜尋候選
const styleCandidates = ref([])
const candidatesLoading = ref(false)
const confirmedStyle = ref(null)  // 使用者選中的候選

// 只有在無結果、無 loading、有候選時才顯示 StyleSuggestions
const showSuggestions = computed(() =>
  !result.value && !loading.value && (styleCandidates.value.length > 0 || candidatesLoading.value)
)

let searchTimer = null
async function fetchStyleCandidates() {
  if (styleRefImage.file) return
  const q = textPrompt.value.trim()
  const sid = selectedStyle.value !== 'auto' ? selectedStyle.value : ''
  if (!q && !sid) {
    styleCandidates.value = []
    confirmedStyle.value = null
    matchedStylePreview.value = null
    return
  }

  candidatesLoading.value = true
  try {
    const res = await fetch(`${API_BASE}/api/style-search?query=${encodeURIComponent(q)}&style_id=${encodeURIComponent(sid)}&top_k=3`)
    if (res.ok) {
      const data = await res.json()
      styleCandidates.value = data
      // 用第一筆更新 sidebar 預覽，不再重複呼叫 API
      matchedStylePreview.value = data[0]
        ? { image_url: data[0].image_url, style_name: data[0].style_name, similarity: data[0].similarity }
        : null
      // 若已確認的那張不在新結果裡就清除
      if (confirmedStyle.value && !data.find(c => c.image_url === confirmedStyle.value.image_url)) {
        confirmedStyle.value = null
      }
    }
  } catch { /* 靜默失敗 */ }
  finally { candidatesLoading.value = false }
}

function scheduleSearch() {
  clearTimeout(searchTimer)
  result.value = null  // 開始新搜尋時清除舊結果，讓候選區可見
  searchTimer = setTimeout(fetchStyleCandidates, 600)
}

watch([textPrompt, selectedStyle], scheduleSearch)

async function fetchStyleOptions(retries = 5, delayMs = 1500) {
  styleLoading.value = true
  styleError.value = ''
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(`${API_BASE}/api/style-profiles`)
      if (!res.ok) throw new Error('載入風格選項失敗')
      const data = await res.json()
      styleOptions.value = [
        { label: '自動', value: 'auto' },
        ...data.map(({ style_name, style_id }) => ({
          label: `${style_name} (${style_id})`,
          value: style_id,
        })),
      ]
      styleLoading.value = false
      return
    } catch (e) {
      if (attempt < retries) {
        await new Promise(r => setTimeout(r, delayMs))
      } else {
        styleError.value = '無法連線後端，請確認伺服器是否已啟動'
      }
    }
  }
  styleLoading.value = false
}

async function uploadFile(file) {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${API_BASE}/api/upload-image`, { method: 'POST', body })
  if (!res.ok) throw new Error(`{res.status}`)
  return (await res.json()).path
}

async function handleSubmit() {
  const hasText = textPrompt.value.trim()
  const hasStyle = selectedStyle.value !== 'auto'
  const hasImage = spaceImage.file || manualImagePath.value.trim()
  if (!hasText && !hasStyle && !hasImage) {
    error.value = '請提供文字需求、風格選擇或圖片'
    return
  }
  const requestId = ++currentRequestId  // 每次提交拿到唯一 ID
  submitKey.value++
  error.value = ''
  result.value = null
  loading.value = true
  try {
    const initial_image_path = spaceImage.file
      ? await uploadFile(spaceImage.file)
      : manualImagePath.value.trim() || undefined

    // 優先用使用者手動上傳的風格參考圖；其次用向量搜尋確認的候選圖
    let style_reference_image_path = undefined
    if (styleRefImage.file) {
      style_reference_image_path = await uploadFile(styleRefImage.file)
    } else if (confirmedStyle.value?.image_url) {
      style_reference_image_path = confirmedStyle.value.image_url
    }

    const res = await fetch(`${API_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt: textPrompt.value,
        edit_scope: editScope.value,
        model_type: modelType.value,
        style_profile_id: selectedStyle.value !== 'auto'
          ? selectedStyle.value
          : confirmedStyle.value?.style_id || undefined,
        initial_image_path,
        style_reference_image_path,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    if (requestId === currentRequestId) result.value = data  // 丟棄過時回應
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
      <div class="logo">
        
        <span class="logo-text">DesignBridge</span>
      </div>

      <SidebarForm
        v-model:textPrompt="textPrompt"
        v-model:editScope="editScope"
        v-model:modelType="modelType"
        v-model:selectedStyle="selectedStyle"
        v-model:manualImagePath="manualImagePath"
        v-model:showManualPath="showManualPath"
        :spaceImage="spaceImage"
        :styleRefImage="styleRefImage"
        :styleOptions="styleOptions"
        :styleLoading="styleLoading"
        :styleError="styleError"
        :matchedStylePreview="matchedStylePreview"
        :loading="loading"
        :error="error"
        @submit="handleSubmit"
      />
    </aside>

    <main class="content">
      <StyleSuggestions
        v-if="showSuggestions"
        :candidates="styleCandidates"
        :confirmed="confirmedStyle"
        :loading="candidatesLoading"
        @confirm="confirmedStyle = $event"
        @clear="confirmedStyle = null"
      />
      <ResultPanel v-else :key="submitKey" :result="result" :loading="loading" />
    </main>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  min-height: 100vh;
  font-family: 'Segoe UI', sans-serif;
  background:
    radial-gradient(ellipse at 20% 30%, rgba(180, 150, 230, 0.18) 0%, transparent 55%),
    radial-gradient(ellipse at 80% 70%, rgba(140, 110, 210, 0.14) 0%, transparent 55%),
    linear-gradient(135deg, #f3eeff 0%, #ede6fa 40%, #e6dff5 100%);
}

.sidebar {
  width: 400px;
  min-width: 400px;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(12px);
  border-right: 1px solid rgba(180, 150, 230, 0.3);
  padding: 2rem;
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
.logo-icon { font-size: 1.7rem; }
.logo-sub  { color: #a990d4; font-size: 0.85rem; margin-bottom: 1rem; }

.content {
  flex: 1;
  padding: 3rem 4rem;
  display: flex;
  flex-direction: column;
}

.content{
  padding-left: 0;
  padding-right: 0;
}
</style>
