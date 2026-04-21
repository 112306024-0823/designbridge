<script setup>
import { ref, onMounted, watch } from 'vue'
import { useImageField } from '@/composables/useImageField'
import SidebarForm from '@/components/SidebarForm.vue'
import ResultPanel from '@/components/ResultPanel.vue'

const API_BASE = 'http://localhost:8000'


const textPrompt = ref('')
const editScope = ref(0.6)
const modelType = ref('sdxl')
const selectedStyle = ref('auto')
const styleOptions = ref([{ label: '自動', value: 'auto' }])
const styleLoading = ref(false)
const styleError = ref('')
const manualImagePath = ref('')
const showManualPath = ref(false)
const spaceImage    = useImageField()   // 原始空間圖片
const styleRefImage = useImageField()   // 風格參考圖
const result = ref(null)
const loading = ref(false)
const error = ref('')
const matchedStylePreview = ref(null)  // { image_url, style_name, similarity }

let previewTimer = null
async function fetchStylePreview() {
  if (styleRefImage.file) return  // 使用者已上傳，不蓋掉
  const q = textPrompt.value.trim()
  const sid = selectedStyle.value !== 'auto' ? selectedStyle.value : ''
  if (!q && !sid) { matchedStylePreview.value = null; return }
  try {
    const res = await fetch(`${API_BASE}/api/style-preview?query=${encodeURIComponent(q)}&style_id=${encodeURIComponent(sid)}`)
    if (res.ok) matchedStylePreview.value = await res.json()
  } catch { /* 靜默失敗 */ }
}
function schedulePreview() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(fetchStylePreview, 500)
}

watch([textPrompt, selectedStyle], schedulePreview)

async function fetchStyleOptions() {
  styleLoading.value = true
  styleError.value = ''
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
  } catch (e) {
    styleError.value = e.message || '載入風格選項失敗'
  } finally {
    styleLoading.value = false
  }
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
  error.value = ''
  result.value = null
  loading.value = true
  try {
    const initial_image_path = spaceImage.file
      ? await uploadFile(spaceImage.file)
      : manualImagePath.value.trim() || undefined
    const style_reference_image_path = styleRefImage.file
      ? await uploadFile(styleRefImage.file)
      : undefined
    const res = await fetch(`${API_BASE}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text_prompt: textPrompt.value,
        edit_scope: editScope.value,
        model_type: modelType.value,
        style_profile_id: selectedStyle.value !== 'auto' ? selectedStyle.value : undefined,
        initial_image_path,
        style_reference_image_path,
      }),
    })
    if (!res.ok) throw new Error(`${res.status}`)
    result.value = await res.json()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
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
      <ResultPanel :result="result" :loading="loading" />
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
</style>
