import { ref } from 'vue'

export interface Toast {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  function show(message: string, type: Toast['type'] = 'success', durationMs = 3000) {
    const id = nextId++
    toasts.value.push({ id, message, type })
    if (durationMs > 0) {
      setTimeout(() => dismiss(id), durationMs)
    }
    return id
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function dismissLatest() {
    if (toasts.value.length > 0) {
      dismiss(toasts.value[toasts.value.length - 1].id)
    }
  }

  return { toasts, show, dismiss, dismissLatest }
}
