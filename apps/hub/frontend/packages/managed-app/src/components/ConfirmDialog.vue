<template>
  <dialog
    ref="dialogRef"
    class="confirm-dialog"
    @cancel.prevent="onCancel"
  >
    <div class="confirm-content">
      <h3 class="confirm-title">{{ title }}</h3>
      <p class="confirm-body">{{ resourceName ? message.replace('{name}', resourceName) : message }}</p>
      <div v-if="requireTypeToConfirm" class="confirm-type-block">
        <label :for="confirmInputId" class="confirm-type-label">
          {{ typePromptText }}
        </label>
        <input
          :id="confirmInputId"
          ref="typeInputRef"
          v-model="typedValue"
          type="text"
          class="confirm-type-input"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          :aria-invalid="typedValue.length > 0 && !typedMatches"
        />
      </div>
      <div class="confirm-actions">
        <button class="confirm-cancel" @click="onCancel" ref="cancelRef">{{ cancelLabel }}</button>
        <button
          class="confirm-danger"
          @click="onConfirm"
          :disabled="requireTypeToConfirm && !typedMatches"
        >
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  open: boolean
  resourceName?: string
  /** When provided, the user must type this value to enable the confirm button. */
  requireTypedValue?: string
  /** Hint shown above the input, e.g. "Type the workspace slug to confirm: foo-bar". */
  typedPrompt?: string
}>(), {
  cancelLabel: 'Cancel',
})

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const dialogRef = ref<HTMLDialogElement | null>(null)
const cancelRef = ref<HTMLButtonElement | null>(null)
const typeInputRef = ref<HTMLInputElement | null>(null)
const typedValue = ref('')
const confirmInputId = `confirm-type-input-${Math.random().toString(36).slice(2, 8)}`

const requireTypeToConfirm = computed(() =>
  typeof props.requireTypedValue === 'string' && props.requireTypedValue.trim().length > 0,
)
const typedMatches = computed(() =>
  requireTypeToConfirm.value && typedValue.value.trim() === String(props.requireTypedValue).trim(),
)
const typePromptText = computed(() => {
  if (props.typedPrompt && props.typedPrompt.trim()) return props.typedPrompt
  return `Type "${props.requireTypedValue}" to confirm:`
})

watch(() => props.open, async (isOpen) => {
  const dialog = dialogRef.value
  if (!dialog) return
  if (isOpen && !dialog.open) {
    typedValue.value = ''
    dialog.showModal()
    await nextTick()
    if (requireTypeToConfirm.value) {
      typeInputRef.value?.focus()
    } else {
      cancelRef.value?.focus()
    }
  } else if (!isOpen && dialog.open) {
    dialog.close()
  }
})

function onConfirm() {
  if (requireTypeToConfirm.value && !typedMatches.value) {
    typeInputRef.value?.focus()
    return
  }
  emit('confirm')
}

function onCancel() {
  emit('cancel')
}
</script>

<style scoped>
.confirm-dialog {
  border: none;
  border-radius: var(--radius-xl);
  padding: 0;
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  color: var(--text-1);
  max-width: 420px;
  width: calc(100% - 32px);
  box-shadow: var(--shadow-lg), 0 0 60px var(--danger-subtle);
  border: 1px solid var(--glass-border);
  animation: dialog-enter var(--transition-spring);
}
@keyframes dialog-enter {
  from {
    opacity: 0;
    transform: scale(0.92) translateY(12px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}
.confirm-dialog::backdrop {
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.confirm-content {
  padding: 28px;
  display: grid;
  gap: 16px;
}
.confirm-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.02em;
}
.confirm-body {
  margin: 0;
  font-size: 0.9rem;
  color: var(--text-2);
  line-height: 1.6;
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
}
.confirm-cancel {
  padding: 10px 18px;
  background: var(--surface-2);
  color: var(--text-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.86rem;
  font-weight: 500;
  transition: all var(--transition-fast);
}
.confirm-cancel:hover {
  background: var(--surface-1);
  border-color: var(--text-3);
  transform: translateY(-1px);
}
.confirm-danger {
  padding: 10px 18px;
  background: var(--danger);
  color: var(--button-danger-text);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.86rem;
  font-weight: 600;
  transition: all var(--transition-fast);
  box-shadow: 0 4px 12px var(--danger-subtle);
}
.confirm-danger:hover {
  opacity: 0.9;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px var(--danger-glow);
}
.confirm-cancel:focus-visible,
.confirm-danger:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.confirm-danger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}
.confirm-type-block {
  display: grid;
  gap: 6px;
}
.confirm-type-label {
  font-size: 0.82rem;
  color: var(--text-2);
  line-height: 1.45;
}
.confirm-type-input {
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-1);
  color: var(--text-1);
  font-size: 0.9rem;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, monospace);
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}
.confirm-type-input:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}
.confirm-type-input[aria-invalid='true'] {
  border-color: var(--danger);
}
</style>
