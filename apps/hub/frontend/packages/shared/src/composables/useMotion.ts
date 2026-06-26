import { ref, watchEffect, onMounted } from 'vue'

export type MotionMode = 'auto' | 'full' | 'reduced' | 'off'

const STORAGE_KEY = 'acp_dashboard_motion'
const VALID_MODES: MotionMode[] = ['auto', 'full', 'reduced', 'off']

const motion = ref<MotionMode>('auto')

let initialized = false

function readStoredMotion(storageKey: string): MotionMode | null {
  try {
    const stored = localStorage.getItem(storageKey)
    if (stored && VALID_MODES.includes(stored as MotionMode)) {
      return stored as MotionMode
    }
  } catch {
    // Storage can be unavailable in hardened browser contexts.
  }
  return null
}

function persistMotion(storageKey: string, mode: MotionMode) {
  try {
    localStorage.setItem(storageKey, mode)
  } catch {
    // Ignore storage failures and keep the in-memory mode.
  }
}

export function useMotion(storageKey = STORAGE_KEY) {
  if (!initialized) {
    const stored = readStoredMotion(storageKey)
    if (stored) {
      motion.value = stored
    }
    initialized = true
  }

  function resolveEffectiveMode(trafficLevel?: string): MotionMode {
    if (motion.value !== 'auto') return motion.value
    if (trafficLevel === 'critical' || trafficLevel === 'high') return 'reduced'
    return 'full'
  }

  function applyMotion(trafficLevel?: string) {
    const effective = resolveEffectiveMode(trafficLevel)
    document.documentElement.dataset.motion = effective
  }

  onMounted(() => applyMotion())

  watchEffect(() => {
    persistMotion(storageKey, motion.value)
    applyMotion()
  })

  function setMotion(mode: MotionMode) {
    motion.value = mode
  }

  return { motion, setMotion, resolveEffectiveMode, applyMotion }
}
