import { ref } from 'vue'

export function useClipboard() {
  const copied = ref(false)
  let timeout: ReturnType<typeof setTimeout> | null = null

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    copied.value = true
    if (timeout) clearTimeout(timeout)
    timeout = setTimeout(() => { copied.value = false }, 1500)
  }

  return { copy, copied }
}
