<template>
  <div class="toggle-group">
    <button
      class="toggle-btn"
      :class="{ active: locale === 'es' }"
      @click="setLocale('es')"
    >ES</button>
    <button
      class="toggle-btn"
      :class="{ active: locale === 'en' }"
      @click="setLocale('en')"
    >EN</button>
  </div>
</template>

<script setup lang="ts">
import { useI18n, type Messages } from '../composables/useI18n'

const props = defineProps<{ messages: Messages }>()
const { locale, setLocale } = useI18n(props.messages)
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
