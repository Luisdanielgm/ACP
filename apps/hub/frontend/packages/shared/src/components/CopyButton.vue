<template>
  <button class="copy-btn" @click="copy(text)" :title="copied ? '✓' : label">
    {{ copied ? '✓' : label }}
  </button>
</template>

<script setup lang="ts">
import { useClipboard } from '../composables/useClipboard'

const props = withDefaults(defineProps<{ text: string; label?: string }>(), { label: 'Copy' })

const { copy, copied } = useClipboard()
</script>

<style scoped>
.copy-btn {
  background: var(--accent, #22d3ee);
  color: var(--button-ink, #000);
  border: none;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s;
  font-family: inherit;
}
.copy-btn:hover { opacity: 0.85; }
</style>
