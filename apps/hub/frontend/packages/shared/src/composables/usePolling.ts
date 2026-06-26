import { ref, onUnmounted } from 'vue'

export function usePolling(fn: () => Promise<void>, intervalMs = 2000) {
  const isActive = ref(false)
  let handle: ReturnType<typeof setInterval> | null = null

  function start() {
    stop()
    isActive.value = true
    handle = setInterval(async () => {
      try {
        await fn()
      } catch {
        // Polling continues even if a single call fails
      }
    }, intervalMs)
  }

  function stop() {
    if (handle !== null) {
      clearInterval(handle)
      handle = null
    }
    isActive.value = false
  }

  onUnmounted(stop)

  return { isActive, start, stop }
}
