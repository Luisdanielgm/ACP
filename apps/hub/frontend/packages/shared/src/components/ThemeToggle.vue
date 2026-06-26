<template>
  <div class="toggle-group">
    <button
      v-for="mode in modes"
      :key="mode.value"
      class="toggle-btn"
      :class="{ active: theme === mode.value }"
      @click="setTheme(mode.value)"
    >{{ mode.label }}</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme, type ThemeMode } from '../composables/useTheme'
import { useI18n, type Messages } from '../composables/useI18n'

const props = withDefaults(defineProps<{ messages?: Messages }>(), { messages: undefined })

const { theme, setTheme } = useTheme()

const defaultLabels: Record<ThemeMode, string> = { dark: 'Dark', light: 'Light', system: 'Auto' }

const modes = computed(() => ([
  { value: 'dark' as ThemeMode, label: props.messages ? tryT('theme_dark', 'Dark') : defaultLabels.dark },
  { value: 'light' as ThemeMode, label: props.messages ? tryT('theme_light', 'Light') : defaultLabels.light },
  { value: 'system' as ThemeMode, label: props.messages ? tryT('theme_system', 'Auto') : defaultLabels.system },
]))

function tryT(key: string, fallback: string): string {
  if (!props.messages) return fallback
  const { t } = useI18n(props.messages)
  return t(key)
}
</script>

<style scoped>
.toggle-group {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px;
  background: var(--toggle-bg);
}
.toggle-btn {
  background: transparent;
  color: var(--muted);
  border: 0;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.toggle-btn:hover { color: var(--ink, var(--text)); }
.toggle-btn.active { background: var(--ink, var(--text)); color: var(--bg); }
</style>
