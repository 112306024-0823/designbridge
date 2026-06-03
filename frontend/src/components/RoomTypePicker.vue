<script setup>
const props = defineProps({
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const ROOM_TYPES = [
  { value: 'living_room', label: '客廳',    icon: 'sofa' },
  { value: 'bedroom',     label: '臥室',    icon: 'bed' },
  { value: 'study',       label: '書房',    icon: 'book' },
  { value: 'kitchen',     label: '廚房',    icon: 'pot' },
  { value: 'bathroom',    label: '浴室',    icon: 'bath' },
  { value: 'whole',       label: '全室',    icon: 'plan' },
]

const ICON_ATTRS = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '1.75',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
}

function handleSelect(value) {
  emit('update:modelValue', props.modelValue === value ? '' : value)
}
</script>

<template>
  <div class="room-type-grid" role="listbox" aria-label="空間類型">
    <button
      v-for="opt in ROOM_TYPES"
      :key="opt.value"
      type="button"
      role="option"
      :aria-selected="modelValue === opt.value"
      :class="['room-type-card', { active: modelValue === opt.value }]"
      @click="handleSelect(opt.value)"
    >
      <span class="room-type-icon" aria-hidden="true">
        <!-- 客廳：沙發 -->
        <svg v-if="opt.icon === 'sofa'" v-bind="ICON_ATTRS">
          <path d="M20 9V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v3" />
          <path d="M2 11v5a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5a2 2 0 0 0-4 0v2H6v-2a2 2 0 0 0-4 0Z" />
          <path d="M4 18v2" />
          <path d="M20 18v2" />
          <path d="M12 4v5" />
        </svg>
        <!-- 臥室：雙人床 -->
        <svg v-else-if="opt.icon === 'bed'" v-bind="ICON_ATTRS">
          <path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8" />
          <path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4" />
          <path d="M12 4v6" />
          <path d="M2 18h20" />
        </svg>
        <!-- 書房：打開的書 -->
        <svg v-else-if="opt.icon === 'book'" v-bind="ICON_ATTRS">
          <path d="M12 7v14" />
          <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
        </svg>
        <!-- 廚房：湯鍋（含蒸氣） -->
        <svg v-else-if="opt.icon === 'pot'" v-bind="ICON_ATTRS">
          <path d="M2 12h20" />
          <path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-6" />
          <path d="m4 8 16-4" />
          <path d="m8.56 4.38 1.5 6" />
        </svg>
        <!-- 浴室：浴缸 -->
        <svg v-else-if="opt.icon === 'bath'" v-bind="ICON_ATTRS">
          <path d="M10 4 8 6" />
          <path d="M15 4 13 6" />
          <path d="M17 19v2" />
          <path d="M7 19v2" />
          <path d="M3 19h18" />
          <path d="M3 13h18v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6z" />
        </svg>
        <!-- 全室：平面配置 -->
        <svg v-else v-bind="ICON_ATTRS">
          <rect x="3" y="3" width="7" height="7" rx="1" />
          <rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" />
          <rect x="14" y="14" width="7" height="7" rx="1" />
          <path d="M10 6.5h4" />
          <path d="M6.5 10v4" />
        </svg>
      </span>
      <span class="room-type-label">{{ opt.label }}</span>
    </button>
  </div>
</template>

<style scoped>
.room-type-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.45rem;
}

.room-type-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  min-height: 76px;
  padding: 0.65rem 0.25rem 0.55rem;
  border: 1px solid #e5d9cc;
  border-radius: 12px;
  background: #fff;
  color: var(--primary);
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s, border-color 0.18s, color 0.18s, box-shadow 0.18s, transform 0.15s;
}

.room-type-card:hover:not(.active) {
  border-color: var(--primary-border);
  background: rgba(255, 250, 243, 0.95);
  transform: translateY(-1px);
}

.room-type-card.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
  box-shadow: var(--btn-shadow);
}

.room-type-card:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(var(--primary-rgb), 0.25);
}

.room-type-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
}

.room-type-icon svg {
  width: 100%;
  height: 100%;
}

.room-type-label {
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .room-type-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
