<template>
  <button
    class="ui-btn"
    :class="[
      variant,
      size,
      {
        active,
        'active-invert': active && activeStyle === 'invert',
      },
    ]"
    :type="type"
    :disabled="disabled"
    @click="$emit('click', $event)"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'primary' | 'ghost' | 'danger-ghost' | 'trace-toggle' | 'filter-chip' | 'access-mode'
  size?: 'md' | 'sm' | 'xs'
  active?: boolean
  activeStyle?: 'accent' | 'invert'
  type?: 'button' | 'submit'
  disabled?: boolean
}>(), {
  variant: 'primary',
  size: 'md',
  activeStyle: 'accent',
  type: 'button',
})

defineEmits<{ click: [event: MouseEvent] }>()
</script>

<style scoped>
/* Base: bare `button` from DashboardView.vue / SessionDashboardView.vue (primary variant, md size) */
.ui-btn {
  border: 0;
  border-radius: 10px;
  padding: 9px 16px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  background: var(--accent);
  color: var(--button-ink);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.ui-btn:hover {
  background: var(--accent-hover);
  transform: translateY(-2px);
  /* NOTE: hardcoded glow shadow preserved verbatim from source (not tokenized) */
  box-shadow: 0 6px 20px rgba(133, 183, 235, 0.35);
}

/* .ghost from both views */
.ui-btn.ghost {
  background: var(--soft);
  color: var(--ink);
  border: 1px solid var(--line);
  box-shadow: none;
}
.ui-btn.ghost:hover {
  background: var(--trace-hover);
  border-color: var(--accent);
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}

/* .danger-ghost (SessionDashboardView only) — combined with .ghost in source
   (class="ghost danger-ghost"), so the resolved style is .ghost's base/hover
   with .danger-ghost overriding color/background/border-color only. The
   .ghost:hover transform + box-shadow are NOT overridden by .danger-ghost in
   the source, so they are preserved here too. Hardcoded hex preserved verbatim. */
.ui-btn.danger-ghost {
  background: var(--soft);
  color: #F0997B;
  border: 1px solid rgba(240, 153, 123, 0.3);
  box-shadow: none;
}
.ui-btn.danger-ghost:hover {
  background: rgba(240, 153, 123, 0.08);
  border-color: #F0997B;
  box-shadow: var(--shadow-glow);
  transform: translateY(-1px);
}

/* .trace-toggle (DashboardView only) — standalone family, NOT combined with .ghost.
   Distinct from ghost: no lift/glow on hover. Kept separate to avoid changing
   its hover behavior. */
.ui-btn.trace-toggle {
  background: none;
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: 11px;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
}
.ui-btn.trace-toggle:hover {
  color: var(--ink);
  border-color: var(--accent);
  transform: none;
  box-shadow: none;
}

/* .filter-chip pill toggle (both views, identical rule).
   .active = accent-fill recipe. */
.ui-btn.filter-chip {
  background: var(--soft);
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
}
.ui-btn.filter-chip:hover {
  color: var(--ink);
  border-color: var(--accent);
}
.ui-btn.filter-chip.active {
  background: var(--accent);
  color: var(--button-ink);
  border-color: var(--accent);
}

/* .access-mode-btn pill toggle (SessionDashboardView only).
   .active = invert-ink recipe (bg var(--ink), color var(--bg)). */
.ui-btn.access-mode {
  background: var(--soft);
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  box-shadow: none;
  cursor: pointer;
}
.ui-btn.access-mode:hover {
  background: var(--trace-hover);
  color: var(--ink);
  border-color: var(--hover-line);
  box-shadow: none;
  transform: none;
}
.ui-btn.access-mode.active-invert {
  background: var(--ink);
  color: var(--bg);
  border-color: var(--ink);
}

/* Size: sm = .compact-action (both views, identical rule) */
.ui-btn.sm {
  padding: 8px 14px;
  font-size: 11px;
  border-radius: 10px;
}

/* Size: xs = dominant pick is .member-action (SessionDashboardView).
   Deltas from other "small" call sites, applied per-call-site via extra
   classes kept on the migrated element (see view styles):
   - .summary-copy-btn: padding 6px 10px, font-size 10px, radius 999px, line-height 1
   - .raw-toggle: font-size 11px, padding 6px 14px, radius 999px */
.ui-btn.xs {
  padding: 6px 12px;
  font-size: 11px;
  border-radius: 8px;
}
</style>
