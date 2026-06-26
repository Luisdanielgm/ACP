<template>
  <div class="toggle-group">
    <button
      v-for="mode in modes"
      :key="mode"
      class="toggle-btn"
      :class="{ active: motion === mode }"
      @click="setMotion(mode)"
    >{{ labels[mode] }}</button>
  </div>
</template>

<script setup lang="ts">
import { useMotion, type MotionMode } from '../composables/useMotion'

const { motion, setMotion } = useMotion()

const modes: MotionMode[] = ['auto', 'full', 'reduced', 'off']
const labels: Record<MotionMode, string> = {
  auto: 'Auto',
  full: 'Full',
  reduced: 'Low',
  off: 'Off',
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
