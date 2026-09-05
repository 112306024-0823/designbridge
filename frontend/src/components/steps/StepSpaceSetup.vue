<script setup>
/**
 * Step 01 空間設定 — Figma MacBook Air - 10
 * 三欄：空間類型 / 預計擺放家具 / 空間大小，底下一顆「生成平面圖」。
 *
 * 設計稿沒畫、但會影響生成結果的欄位（自訂長寬、輸出長寬比、家具數量、
 * 家庭結構、風水）全部收進「進階設定」，不刪。
 */
import { ref, computed } from 'vue'
import { Icon } from '@iconify/vue'
import AdvancedPanel from '@/components/shell/AdvancedPanel.vue'
import { ROOM_OPTIONS, FURNITURE_BY_ROOM, furnitureIcon, furnitureLabel } from '@/config/furniture'
import {
  useDesignFlow, ASPECT_OPTIONS, FAMILY_OPTIONS, FENGSHUI_OPTIONS,
} from '@/composables/useDesignFlow'

const {
  planSource, roomType, roomTypeForPlan, spaceSizePing, customRoomW, customRoomD, outputAspect,
  furnitureItems, furnitureQty, extraPrompt, familyNeeds, fengshuiRules,
  loading, submitLayout, nextStep, scheduleSearch,
} = useDesignFlow()

const isSkip = computed(() => planSource.value === 'skip')

const availableFurniture = computed(() => FURNITURE_BY_ROOM[roomType.value] || [])

/* ── 房型 ── */
const customRoomInput = ref('')
const showCustomRoom = ref(false)
const roomChoices = computed(() => {
  // 自訂房型不在 ROOM_OPTIONS 裡，補一顆 chip 才看得到目前選的是它
  const known = ROOM_OPTIONS.some(o => o.value === roomType.value)
  return known ? ROOM_OPTIONS : [...ROOM_OPTIONS, { value: roomType.value, label: roomType.value }]
})

function pickRoom(value) {
  if (roomType.value === value) return
  roomType.value = value
  furnitureItems.value = []
  furnitureQty.value = {}
}
function applyCustomRoom() {
  const v = customRoomInput.value.trim()
  if (!v) return
  pickRoom(v)
  customRoomInput.value = ''
  showCustomRoom.value = false
}

/* ── 家具 ── */
const customFurnitureInput = ref('')
const showCustomFurniture = ref(false)

function toggleFurniture(value) {
  if (furnitureItems.value.includes(value)) {
    furnitureItems.value = furnitureItems.value.filter(v => v !== value)
    const q = { ...furnitureQty.value }; delete q[value]; furnitureQty.value = q
  } else {
    furnitureItems.value = [...furnitureItems.value, value]
    furnitureQty.value = { ...furnitureQty.value, [value]: 1 }
  }
}
function addCustomFurniture() {
  const val = customFurnitureInput.value.trim().toLowerCase().replace(/\s+/g, '_')
  if (val && !furnitureItems.value.includes(val)) {
    furnitureItems.value = [...furnitureItems.value, val]
    furnitureQty.value = { ...furnitureQty.value, [val]: 1 }
  }
  customFurnitureInput.value = ''
  showCustomFurniture.value = false
}
function removeFurniture(value) {
  furnitureItems.value = furnitureItems.value.filter(v => v !== value)
  const q = { ...furnitureQty.value }; delete q[value]; furnitureQty.value = q
}
function qtyOf(value) { return furnitureQty.value[value] || 1 }
function setQty(value, n) {
  furnitureQty.value = { ...furnitureQty.value, [value]: Math.max(1, Math.min(20, n)) }
}

/* 自訂家具不在 availableFurniture 裡，但要能看到並取消 */
const extraSelected = computed(
  () => furnitureItems.value.filter(v => !availableFurniture.value.some(o => o.value === v)),
)

/* ── 坪數 ↔ 自訂長寬連動（沿用舊 SidebarForm 的 @input 做法，避免兩個 watch 互咬）── */
function recalcRoomSide(filled, other) {
  if (!filled) return
  const totalM2 = spaceSizePing.value * 3.306
  other.value = Math.round((totalM2 / filled) * 10) / 10
}
function onCustomRoomWInput() { recalcRoomSide(customRoomW.value, customRoomD) }
function onCustomRoomDInput() { recalcRoomSide(customRoomD.value, customRoomW) }

function toggleIn(listRef, value) {
  listRef.value = listRef.value.includes(value)
    ? listRef.value.filter(v => v !== value)
    : [...listRef.value, value]
}

/**
 * 跳過家具排版，直接去渲染那一步。
 *
 * 進來才發現還沒想好要擺什麼家具是很常見的事，本來得退回入口重選「從零開始」，
 * 選過的房型與坪數也一起丟掉。這裡直接把路徑切成 skip：步驟表會跟著少一步，
 * 使用者填過的東西留著。
 */
function goSkipRender() {
  // 沒有文字描述時，風格推薦會拿房型當查詢字，而 roomTypeForPlan 平常是
  // generate-layout 回來才設定的；跳過排版就沒人設定它，要在這裡補，
  // 否則不管選哪個房型，推薦出來的都是預設「客廳」。
  roomTypeForPlan.value = roomType.value
  planSource.value = 'skip'
  scheduleSearch()
  nextStep()
}

function submit() {
  if (isSkip.value) {
    goSkipRender()
    return
  }
  submitLayout()
}
</script>

<template>
  <div class="space-setup">
    <div class="columns" :class="{ 'two-col': isSkip }">

      <!-- ── 空間類型 ── -->
      <section class="col">
        <h2 class="db-col-title">空間類型</h2>
        <div class="room-grid">
          <button
            v-for="opt in roomChoices" :key="opt.value"
            type="button"
            :class="['db-chip', 'db-chip--lg', { 'is-active': roomType === opt.value }]"
            @click="pickRoom(opt.value)"
          >{{ opt.label }}</button>
        </div>

        <div class="custom-slot">
          <button
            v-if="!showCustomRoom"
            type="button"
            class="db-chip db-chip--lg is-ghost"
            @click="showCustomRoom = true"
          >自訂</button>
          <div v-else class="custom-row">
            <input
              v-model="customRoomInput"
              class="db-input"
              placeholder="例如：和室、更衣室"
              @keydown.enter.prevent="applyCustomRoom"
              @keydown.esc="showCustomRoom = false"
            />
            <button type="button" class="add-btn" @click="applyCustomRoom">✓</button>
          </div>
        </div>
      </section>

      <!-- ── 預計擺放家具（不排家具模式不需要）── -->
      <section v-if="!isSkip" class="col">
        <h2 class="db-col-title">預計擺放家具</h2>
        <div class="furniture-list">
          <button
            v-for="opt in availableFurniture" :key="opt.value"
            type="button"
            :class="['db-chip', 'furniture-chip', { 'is-active': furnitureItems.includes(opt.value) }]"
            @click="toggleFurniture(opt.value)"
          >
            <Icon :icon="furnitureIcon(opt.value)" class="chip-icon" aria-hidden="true" />
            <span>{{ opt.label }}</span>
            <span v-if="furnitureItems.includes(opt.value) && qtyOf(opt.value) > 1" class="qty-badge">
              ×{{ qtyOf(opt.value) }}
            </span>
          </button>

          <!-- 自訂家具（設計稿有這顆 chip，但沒給輸入流程）-->
          <button
            v-if="!showCustomFurniture"
            type="button"
            class="db-chip furniture-chip is-ghost"
            @click="showCustomFurniture = true"
          >自訂</button>
          <div v-else class="custom-row">
            <input
              v-model="customFurnitureInput"
              class="db-input"
              placeholder="家具名稱（英文）"
              @keydown.enter.prevent="addCustomFurniture"
              @keydown.esc="showCustomFurniture = false"
            />
            <button type="button" class="add-btn" @click="addCustomFurniture">＋</button>
          </div>

          <!-- 自訂加進來的項目也要能看到／取消 -->
          <button
            v-for="v in extraSelected" :key="v"
            type="button"
            class="db-chip furniture-chip is-active"
            @click="removeFurniture(v)"
          >
            <Icon :icon="furnitureIcon(v)" class="chip-icon" aria-hidden="true" />
            <span>{{ furnitureLabel(v) }}</span>
            <span v-if="qtyOf(v) > 1" class="qty-badge">×{{ qtyOf(v) }}</span>
          </button>
        </div>
      </section>

      <!-- ── 空間大小 ── -->
      <section class="col col-size">
        <h2 class="db-col-title">空間大小</h2>
        <div class="ping-row">
          <span class="ping-word">約</span>
          <input
            v-model.number="spaceSizePing"
            type="number" min="1" max="100" step="0.5"
            class="db-input ping-input"
            placeholder="輸入"
          />
          <span class="ping-word">坪</span>
        </div>
        <p class="ping-hint">≈ {{ Math.round((spaceSizePing || 0) * 3.3) }} m²</p>

        <!-- 不排家具模式沒有家具欄，把描述放這裡才不會整卡空一半 -->
        <div v-if="isSkip" class="skip-desc">
          <label class="field-label" for="skip-prompt">描述你想要的樣式</label>
          <textarea
            id="skip-prompt"
            v-model="extraPrompt"
            class="db-textarea"
            rows="4"
            placeholder="例如：木質感、採光充足的明亮感…"
          />
        </div>
      </section>
    </div>

    <!-- ══ 進階設定 ══ -->
    <AdvancedPanel hint="長寬・比例・數量・家庭結構・風水">
      <div class="adv-grid">
        <div class="adv-field">
          <label class="field-label">自訂長寬（公尺，可留空）</label>
          <div class="pair">
            <input
              v-model.number="customRoomW" type="number" min="1" step="0.1"
              class="db-input" placeholder="長度（自動）" @input="onCustomRoomWInput"
            />
            <input
              v-model.number="customRoomD" type="number" min="1" step="0.1"
              class="db-input" placeholder="寬度（自動）" @input="onCustomRoomDInput"
            />
          </div>
          <p class="field-hint">填一邊，另一邊會依上面的坪數自動算</p>
        </div>

        <div class="adv-field">
          <label class="field-label" for="aspect">輸出圖片長寬比</label>
          <select id="aspect" v-model="outputAspect" class="db-input">
            <option v-for="opt in ASPECT_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>

        <div v-if="!isSkip" class="adv-field">
          <label class="field-label">額外需求（會一併影響家具排版）</label>
          <textarea
            v-model="extraPrompt" class="db-textarea" rows="2"
            placeholder="例如：留出輪椅動線、電視牆靠窗…"
          />
        </div>

        <div v-if="!isSkip && furnitureItems.length" class="adv-field adv-span">
          <label class="field-label">已選家具與數量</label>
          <div class="qty-list">
            <span v-for="item in furnitureItems" :key="item" class="qty-tag">
              {{ furnitureLabel(item) }}
              <button type="button" class="qty-btn" @click="setQty(item, qtyOf(item) - 1)">−</button>
              <span class="qty-num">{{ qtyOf(item) }}</span>
              <button type="button" class="qty-btn" @click="setQty(item, qtyOf(item) + 1)">＋</button>
              <button type="button" class="qty-remove" title="移除" @click="removeFurniture(item)">×</button>
            </span>
          </div>
        </div>

        <div class="adv-field">
          <label class="field-label">家庭結構</label>
          <div class="chip-row">
            <button
              v-for="opt in FAMILY_OPTIONS" :key="opt.value" type="button"
              :class="['db-chip', { 'is-active': familyNeeds.includes(opt.value) }]"
              @click="toggleIn(familyNeeds, opt.value)"
            >{{ opt.label }}</button>
          </div>
        </div>

        <div class="adv-field">
          <label class="field-label">風水需求</label>
          <div class="chip-row">
            <button
              v-for="opt in FENGSHUI_OPTIONS" :key="opt.value" type="button"
              :class="['db-chip', { 'is-active': fengshuiRules.includes(opt.value) }]"
              @click="toggleIn(fengshuiRules, opt.value)"
            >{{ opt.label }}</button>
          </div>
        </div>
      </div>
    </AdvancedPanel>

    <div class="actions">
      <button class="db-btn" :disabled="loading" @click="submit">
        {{ isSkip ? '下一步：描述你的空間' : '生成平面圖' }}
      </button>
      <button v-if="!isSkip" type="button" class="skip-link" :disabled="loading" @click="goSkipRender">
        還沒想好要擺什麼家具？跳過排版，直接生成渲染圖 →
      </button>
    </div>
  </div>
</template>

<style scoped>
.space-setup { display: flex; flex-direction: column; }

.columns {
  display: grid;
  grid-template-columns: 1.15fr 1fr 1fr;
  gap: clamp(1.25rem, 3vw, 3rem);
  padding-bottom: 1.5rem;
}
.columns.two-col { grid-template-columns: 1fr 1.2fr; }

.col { min-width: 0; }
.col-size { display: flex; flex-direction: column; }

/* 空間類型：設計稿是 2 欄 */
.room-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.9rem 1.1rem;
}
.room-grid .db-chip { width: 100%; }

.custom-slot { margin-top: 0.9rem; }
.custom-slot .db-chip { width: calc(50% - 0.55rem); }

/* 家具：設計稿是單欄直排 */
.furniture-list {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  align-items: stretch;
}
.furniture-chip {
  justify-content: flex-start;
  gap: 0.55rem;
  padding: 0.55rem 1rem;
}
.chip-icon { font-size: 1.15rem; flex-shrink: 0; }

.qty-badge {
  margin-left: auto;
  font-family: var(--db-font-body);
  font-style: normal;
  font-size: 0.8rem;
  opacity: 0.9;
}

/* 設計稿把「自訂」畫成淡色（未啟用）樣子 */
.is-ghost { color: var(--db-muted); }
.is-ghost:hover { color: var(--db-text-soft); }

.custom-row { display: flex; gap: 0.4rem; }
.custom-row .db-input { min-width: 0; }
.add-btn {
  flex-shrink: 0;
  width: 42px;
  border: none;
  border-radius: 6px;
  background: var(--db-accent);
  color: var(--db-on-accent);
  font-size: 1rem;
  cursor: pointer;
}
.add-btn:hover { background: var(--db-accent-deep); }

/* 空間大小 */
.ping-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
}
.ping-word {
  font-family: var(--db-font-display);
  font-style: italic;
  font-size: 1.5rem;
  color: var(--db-text);
}
.ping-input {
  width: 160px;
  height: 68px;
  border-radius: 0;
  text-align: center;
  font-size: 1.5rem;
}
.ping-hint {
  margin: 0.65rem 0 0;
  text-align: center;
  font-size: 0.85rem;
  color: var(--db-text-soft);
}

.skip-desc { margin-top: 1.75rem; }

/* 進階設定內部 */
.adv-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1.25rem 1.5rem;
}
.adv-span { grid-column: 1 / -1; }
.pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }

.field-label {
  display: block;
  margin-bottom: 0.45rem;
  font-size: 0.88rem;
  font-weight: 500;
  color: var(--db-text-soft);
}
.field-hint {
  margin: 0.4rem 0 0;
  font-size: 0.78rem;
  color: var(--db-placeholder);
}

.chip-row { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.chip-row .db-chip { font-size: 0.92rem; padding: 0.4rem 0.9rem; }

.qty-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.qty-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.5rem 0.3rem 0.75rem;
  border-radius: var(--db-radius-pill);
  background: var(--db-chip-soft);
  font-size: 0.88rem;
}
.qty-btn {
  width: 22px; height: 22px;
  border: none; border-radius: 50%;
  background: #fff;
  color: var(--db-text);
  cursor: pointer;
  line-height: 1;
}
.qty-btn:hover { background: var(--db-accent); color: var(--db-on-accent); }
.qty-num { min-width: 1.1em; text-align: center; font-variant-numeric: tabular-nums; }
.qty-remove {
  border: none; background: none; cursor: pointer;
  color: var(--db-placeholder); font-size: 1rem; line-height: 1;
}
.qty-remove:hover { color: var(--db-danger); }

.actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.9rem;
  padding-top: 1.5rem;
}
.actions .db-btn { min-width: 337px; }

.skip-link {
  border: none;
  background: none;
  padding: 0;
  color: var(--db-text-soft);
  font-family: var(--db-font-body);
  font-size: 0.86rem;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.skip-link:hover:not(:disabled) { color: var(--db-text); }
.skip-link:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 900px) {
  .columns,
  .columns.two-col { grid-template-columns: 1fr; }
  .actions .db-btn { min-width: 0; width: 100%; }
}
</style>
