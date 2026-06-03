<script setup>
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue'])

const LIFESTYLE_OPTIONS = [
  { value: 'children',       label: '親子家庭', icon: 'family' },
  { value: 'pets',           label: '寵物友善', icon: 'paw' },
  { value: 'work_from_home', label: '在家工作', icon: 'laptop' },
  { value: 'elderly',        label: '長者同住', icon: 'elderly' },
  { value: 'likes_cooking',  label: '喜歡下廚', icon: 'cooking' },
  { value: 'likes_storage',  label: '喜歡收納', icon: 'storage' },
]

const ICON_ATTRS = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '1.75',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
}

function isSelected(value) {
  return props.modelValue.includes(value)
}

function toggle(value) {
  const next = isSelected(value)
    ? props.modelValue.filter(v => v !== value)
    : [...props.modelValue, value]
  emit('update:modelValue', next)
}
</script>

<template>
  <div class="lifestyle-grid" role="group" aria-label="生活型態">
    <button
      v-for="opt in LIFESTYLE_OPTIONS"
      :key="opt.value"
      type="button"
      :class="['lifestyle-card', { active: isSelected(opt.value) }]"
      :aria-pressed="isSelected(opt.value)"
      @click="toggle(opt.value)"
    >
      <span class="lifestyle-icon-wrap" aria-hidden="true">
        <!-- 親子家庭 -->
        <svg v-if="opt.icon === 'family'" v-bind="ICON_ATTRS">
          <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
          <circle cx="9" cy="7" r="4" />
          <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
          <path d="M16 3.13a4 4 0 0 1 0 7.75" />
        </svg>
        <!-- 寵物友善 -->
        <svg v-else-if="opt.icon === 'paw'" v-bind="ICON_ATTRS">
          <circle cx="11" cy="4" r="2" />
          <circle cx="18" cy="8" r="2" />
          <circle cx="20" cy="16" r="2" />
          <path d="M9 10a5 5 0 0 0-4 8 5 5 0 0 0 8-4" />
        </svg>
        <!-- 在家工作 -->
        <svg v-else-if="opt.icon === 'laptop'" v-bind="ICON_ATTRS">
          <path d="M20 16V7a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v9" />
          <path d="M2 17h20" />
        </svg>
        <!-- 長者同住 -->
        <svg v-else-if="opt.icon === 'elderly'" v-bind="ICON_ATTRS">
          <circle cx="12" cy="5" r="2" />
          <path d="M10 22v-5H8l2-6h4l2 6h-2v5" />
          <path d="M8 11h8" />
        </svg>
        <!-- 喜歡下廚 -->
        <svg v-else-if="opt.icon === 'cooking'" v-bind="ICON_ATTRS">
          <path d="M2 12h20" />
          <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-6" />
          <path d="m4 8 16-4" />
          <path d="m8.56 4.38 1.5 6" />
        </svg>
        <!-- 喜歡收納 -->
        <svg v-else v-bind="ICON_ATTRS">
          <path d="M21 8v13H3V8" />
          <path d="M1 8h22v3H1z" />
          <path d="M10 12v4" />
          <path d="M14 12v4" />
          <path d="M12 8V4" />
          <path d="M8 4h8" />
        </svg>
      </span>
      <span class="lifestyle-label">{{ opt.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.lifestyle-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.lifestyle-card {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.55rem 0.65rem;
  min-height: 52px;
  border: 1px solid #e8ddd0;
  border-radius: 12px;
  background: rgba(255, 252, 247, 0.95);
  color: var(--primary);
  font-family: inherit;
  cursor: pointer;
  text-align: left;
  transition: background 0.18s, border-color 0.18s, color 0.18s, box-shadow 0.18s;
}

.lifestyle-card:hover:not(.active) {
  border-color: var(--primary-border);
  background: #fff;
}

.lifestyle-card.active {
  background: var(--primary-subtle);
  border-color: var(--primary);
  box-shadow: 0 0 0 1px rgba(var(--primary-rgb), 0.12);
}

.lifestyle-card:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(var(--primary-rgb), 0.22);
}

.lifestyle-icon-wrap {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: rgba(var(--primary-rgb), 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lifestyle-card.active .lifestyle-icon-wrap {
  background: rgba(255, 255, 255, 0.55);
}

.lifestyle-icon-wrap svg {
  width: 18px;
  height: 18px;
}

.lifestyle-label {
  font-size: 0.88rem;
  font-weight: 600;
  color: #4a3018;
  line-height: 1.25;
}

.lifestyle-card.active .lifestyle-label {
  color: #3a2010;
}

@media (max-width: 520px) {
  .lifestyle-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
