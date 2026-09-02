import { ref, computed } from 'vue'

// 模組層級的共享狀態：跨頁面（HomeView / FurnitureView）保留使用者已勾選的家具
const selectedFurniture = ref([])

function itemKey(item) {
  return item.id || item.url || `${item.name}__${item.category}`
}

function isSelected(item) {
  const key = itemKey(item)
  return selectedFurniture.value.some(f => itemKey(f) === key)
}

function toggle(item) {
  if (isSelected(item)) {
    const key = itemKey(item)
    selectedFurniture.value = selectedFurniture.value.filter(f => itemKey(f) !== key)
  } else {
    selectedFurniture.value = [
      ...selectedFurniture.value,
      {
        id: item.id,
        name: item.name,
        category: item.category,
        price: item.price,
        currency: item.currency,
        url: item.url,
        image_url: item.image_url,
      },
    ]
  }
}

function remove(item) {
  const key = itemKey(item)
  selectedFurniture.value = selectedFurniture.value.filter(f => itemKey(f) !== key)
}

function clear() {
  selectedFurniture.value = []
}

export function useFurnitureSelection() {
  return {
    selectedFurniture,
    selectedCount: computed(() => selectedFurniture.value.length),
    isSelected,
    toggle,
    remove,
    clear,
  }
}
