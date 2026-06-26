<template>
  <div
    class="skeleton-block"
    :class="[`skeleton-${variant}`, { 'skeleton-animated': animated }]"
    :style="{ width, height: h, borderRadius: radius }"
    role="presentation"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'line' | 'circle' | 'rect'
  width?: string
  h?: string
  radius?: string
  animated?: boolean
}>(), {
  variant: 'line',
  animated: true,
})
</script>

<style scoped>
.skeleton-block {
  background: var(--surface-2);
  flex-shrink: 0;
}
.skeleton-animated {
  background: linear-gradient(
    90deg,
    var(--surface-2) 25%,
    color-mix(in srgb, var(--surface-2) 50%, var(--surface-1)) 50%,
    var(--surface-2) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.6s ease-in-out infinite;
  position: relative;
  overflow: hidden;
}
.skeleton-animated::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent,
    color-mix(in srgb, var(--accent) 8%, transparent),
    transparent
  );
  animation: shimmer-accent 2s ease-in-out infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
@keyframes shimmer-accent {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
.skeleton-line {
  height: 14px;
  border-radius: var(--radius-sm);
  width: 100%;
}
.skeleton-circle {
  border-radius: 50%;
  width: 40px;
  height: 40px;
}
.skeleton-rect {
  border-radius: var(--radius-md);
  width: 100%;
  height: 100%;
}
@media (prefers-reduced-motion: reduce) {
  .skeleton-animated {
    animation: none;
  }
  .skeleton-animated::after {
    display: none;
  }
}
</style>
