<template>
  <div class="toast-region" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        class="toast"
        :class="'toast-' + toast.type"
      >
        <span class="toast-icon" aria-hidden="true">
          <svg v-if="toast.type === 'success'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          <svg v-else-if="toast.type === 'error'" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        </span>
        <span class="toast-message">{{ toast.message }}</span>
        <button class="toast-dismiss" @click="dismiss(toast.id)" :aria-label="dismissLabel">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useToast } from '../composables/useToast'

defineProps<{ dismissLabel?: string }>()

const { toasts, dismiss, dismissLatest } = useToast()

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && toasts.value.length > 0) {
    dismissLatest()
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<style scoped>
.toast-region {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column-reverse;
  gap: 10px;
  pointer-events: none;
  max-width: 380px;
}
.toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-radius: var(--radius-lg);
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  box-shadow: var(--shadow-lg);
  font-size: 0.88rem;
  color: var(--text-1);
}
.toast-success {
  border-left: 3px solid var(--success);
  box-shadow: var(--shadow-lg), 0 0 30px var(--success-subtle);
}
.toast-error {
  border-left: 3px solid var(--danger);
  box-shadow: var(--shadow-lg), 0 0 30px var(--danger-subtle);
}
.toast-info {
  border-left: 3px solid var(--accent);
  box-shadow: var(--shadow-lg), 0 0 30px var(--accent-subtle);
}
.toast-icon {
  flex-shrink: 0;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  font-size: 0;
}
.toast-success .toast-icon {
  background: var(--success-subtle);
  color: var(--success);
}
.toast-error .toast-icon {
  background: var(--danger-subtle);
  color: var(--danger);
}
.toast-info .toast-icon {
  background: var(--accent-subtle);
  color: var(--accent);
}
.toast-message {
  flex: 1;
  min-width: 0;
  line-height: 1.5;
  font-weight: 500;
}
.toast-dismiss {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text-3);
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
  display: grid;
  place-items: center;
}
.toast-dismiss:hover {
  color: var(--text-1);
  background: var(--surface-2);
}
.toast-dismiss:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px var(--accent);
}

.toast-enter-active {
  transition: all 0.35s cubic-bezier(0.16, 1, 0.3, 1);
}
.toast-leave-active {
  transition: all 0.25s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(32px) scale(0.95);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(32px) scale(0.95);
}

@media (prefers-reduced-motion: reduce) {
  .toast-enter-active,
  .toast-leave-active {
    transition: none;
  }
}

@media (max-width: 480px) {
  .toast-region {
    bottom: 16px;
    right: 16px;
    left: 16px;
    max-width: none;
  }
}
</style>
