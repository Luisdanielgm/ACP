<template>
  <nav v-if="crumbs.length > 0" class="breadcrumbs" :aria-label="t('breadcrumbs_label')">
    <ol>
      <li v-for="(crumb, index) in crumbs" :key="index">
        <RouterLink
          v-if="crumb.to && index < crumbs.length - 1"
          :to="crumb.to"
          class="breadcrumb-link"
        >
          {{ crumb.label }}
        </RouterLink>
        <span v-else class="breadcrumb-current" aria-current="page">
          {{ crumb.label }}
        </span>
        <span v-if="index < crumbs.length - 1" class="breadcrumb-separator" aria-hidden="true">/</span>
      </li>
    </ol>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'

interface Crumb {
  label: string
  to?: string
}

const route = useRoute()
const { isSingleWorkspace, user } = useManagedAuth()
const { t } = useManagedI18n()

function formatSlug(value: string): string {
  return value
    .split('-')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

const crumbs = computed<Crumb[]>(() => {
  const name = String(route.name ?? '')
  const slug = String(route.params.slug ?? '').trim()
  const sessionId = String(route.params.sessionId ?? '').trim()

  // Root crumb depends on the user's primary surface.
  const root: Crumb = isSingleWorkspace.value
    ? {
        label: t('nav_workspace'),
        to: user.value?.default_workspace?.slug
          ? `/managed/ui/workspaces/${encodeURIComponent(user.value.default_workspace.slug)}`
          : '/managed/ui/workspaces',
      }
    : { label: t('nav_workspaces'), to: '/managed/ui/workspaces' }

  // Routes where breadcrumbs are not meaningful or are self-evident.
  if (!name || name === 'login' || name === 'landing' || name === 'invitation') {
    return []
  }

  if (name === 'workspaces' || name === 'dashboard') {
    return [{ ...root }]
  }

  if (name === 'workspace-detail') {
    if (!slug || isSingleWorkspace.value) return []
    return [root, { label: formatSlug(slug) }]
  }

  if (name === 'session-live' || name === 'managed-session-dashboard') {
    const list: Crumb[] = [root]
    if (slug) {
      list.push({
        label: formatSlug(slug),
        to: `/managed/ui/workspaces/${encodeURIComponent(slug)}`,
      })
    }
    list.push({
      label: sessionId ? sessionId.slice(0, 8) + '…' : t('session_kicker'),
    })
    return list
  }

  return []
})
</script>

<style scoped>
.breadcrumbs {
  margin: 16px 0 12px;
  font-size: 0.82rem;
  color: var(--text-2);
}
.breadcrumbs ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.breadcrumbs li {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.breadcrumb-link {
  color: var(--text-2);
  text-decoration: none;
  padding: 2px 6px;
  border-radius: var(--radius-sm, 4px);
  transition: color var(--transition-fast), background var(--transition-fast);
}
.breadcrumb-link:hover,
.breadcrumb-link:focus-visible {
  color: var(--text-1);
  background: var(--surface-1);
  outline: none;
}
.breadcrumb-current {
  color: var(--text-1);
  font-weight: 600;
  padding: 2px 6px;
}
.breadcrumb-separator {
  color: var(--text-3, var(--text-2));
  opacity: 0.6;
}
</style>
