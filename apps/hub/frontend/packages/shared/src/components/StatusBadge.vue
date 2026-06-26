<template>
  <span class="badge" :class="variant">
    <span class="dot"></span>
    <slot>{{ label }}</slot>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  variant?: 'success' | 'warning' | 'danger' | 'info' | 'muted'
  label?: string
}>()
</script>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  background: var(--chip-bg, rgba(255,255,255,0.05));
  border: 1px solid var(--chip-border, transparent);
  color: var(--muted);
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.success { color: var(--success, #10b981); }
.warning { color: var(--warning, #f59e0b); }
.danger { color: var(--danger, #ef4444); }
.info { color: var(--info, #8b5cf6); }
.muted { color: var(--muted, #8b94a7); }
</style>
