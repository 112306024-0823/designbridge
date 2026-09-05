<script setup>
import { ref } from 'vue'

/**
 * 設計稿的白卡容不下舊版側欄的全部欄位，但那些欄位（長寬比、自訂長寬、家庭結構、
 * 風水、風格參考圖、styleMethod…）都是實際會影響生成結果的參數，不能刪。
 * 統一收進這個預設摺疊的區塊：第一眼維持設計稿的乾淨，進階使用者展開就拿得到全部。
 */
defineProps({
  title: { type: String, default: '進階設定' },
  hint:  { type: String, default: '' },
})

const open = ref(false)
</script>

<template>
  <div class="advanced">
    <button type="button" class="toggle" :aria-expanded="open" @click="open = !open">
      <span class="toggle-text">{{ title }}</span>
      <span v-if="hint && !open" class="toggle-hint">{{ hint }}</span>
      <svg class="arrow" :class="{ open }" width="16" height="16" viewBox="0 0 24 24"
        fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
    <div v-show="open" class="body">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.advanced {
  border-top: 1px solid #ececec;
  margin-top: 0.5rem;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.85rem 0.25rem;
  border: none;
  background: none;
  color: var(--db-text-soft);
  font-family: var(--db-font-display);
  font-style: italic;
  font-size: 1.05rem;
  cursor: pointer;
}
.toggle:hover { color: var(--db-text); }

.toggle-hint {
  font-family: var(--db-font-body);
  font-style: normal;
  font-size: 0.82rem;
  color: var(--db-placeholder);
}

.arrow {
  margin-left: auto;
  transition: transform 0.2s;
}
.arrow.open { transform: rotate(180deg); }

.body {
  display: grid;
  gap: 1.25rem;
  padding: 0.25rem 0.25rem 1.25rem;
}
</style>
