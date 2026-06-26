<template>
  <a href="#main-content" class="skip-link">{{ t('skip_to_content') }}</a>
  <div class="route-announcer" role="status" aria-live="polite" aria-atomic="true">{{ routeAnnouncement }}</div>

  <div
    v-if="sidebarOpen"
    class="shell-overlay"
    aria-hidden="true"
    @click="closeSidebar"
  ></div>

  <aside class="shell-sidebar" :class="{ 'shell-sidebar-open': sidebarOpen }" :aria-label="t('nav_menu')">
    <div class="sidebar-head">
      <RouterLink to="/managed/ui/workspaces" class="brand">
        <span class="mark" aria-hidden="true"></span>
        <span class="brand-copy">
          <strong class="brand-title">ACP Managed</strong>
          <span class="brand-sub">{{ t('dash_kicker') }}</span>
        </span>
      </RouterLink>
      <button class="sidebar-close" type="button" :aria-label="t('nav_close_menu')" @click="closeSidebar">
        &times;
      </button>
    </div>

    <div class="sidebar-section">
      <p class="sidebar-label">{{ t('nav_menu') }}</p>
      <nav class="sidebar-nav" aria-label="Managed navigation">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="sidebar-link"
          :aria-current="isActive(item.to) ? 'page' : undefined"
          @click="closeSidebar"
        >
          <span class="sidebar-link-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="sidebar-link-text">{{ item.label }}</span>
        </RouterLink>
      </nav>
    </div>

    <div v-if="workspaceContext" class="sidebar-section sidebar-context">
      <p class="sidebar-label">{{ t('nav_current_workspace') }}</p>
      <RouterLink
        :to="workspaceContext.to"
        class="context-card"
        :aria-current="isActive(workspaceContext.to) ? 'page' : undefined"
        @click="closeSidebar"
      >
        <span class="context-kicker">{{ t('workspace_kicker') }}</span>
        <strong class="context-title">{{ workspaceContext.title }}</strong>
        <span class="context-body">{{ t('workspace_dashboard_body') }}</span>
      </RouterLink>
    </div>

    <div class="sidebar-footer">
      <div v-if="user" class="user-card" :title="user.email">
        <span class="user-card-label">{{ t('role_' + user.role) }}</span>
        <strong class="user-card-email">{{ user.email }}</strong>
      </div>
      <button class="ghost-button sidebar-logout" @click="logout" :aria-label="t('logout')">{{ t('logout') }}</button>
    </div>
  </aside>

  <header class="shell-topbar">
    <div class="topbar-main">
      <button class="menu-button" type="button" :aria-label="sidebarOpen ? t('nav_close_menu') : t('nav_open_menu')" @click="toggleSidebar">
        <span></span>
        <span></span>
        <span></span>
      </button>
      <div class="topbar-copy">
        <span class="topbar-kicker">{{ pageKicker }}</span>
        <strong class="topbar-title">{{ pageTitle }}</strong>
        <Breadcrumbs />
      </div>
    </div>

    <div class="topbar-actions">
      <ThemeToggle />
      <LangToggle :messages="messages" />
    </div>
  </header>

  <ToastContainer :dismiss-label="t('dismiss')" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { ThemeToggle, LangToggle } from '@acp/shared'
import ToastContainer from './ToastContainer.vue'
import Breadcrumbs from './Breadcrumbs.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n, messages } from '../i18n'

type NavItem = {
  to: string
  label: string
  icon: string
  visible: boolean
}

const route = useRoute()
const { isInstanceAdmin, user, logout } = useManagedAuth()
const { t } = useManagedI18n()

const routeAnnouncement = ref('')
const sidebarOpen = ref(false)

const navItems = computed<NavItem[]>(() =>
  [
    // D1: For instance_admin, "Admin" is the single canonical surface (it
    // contains create + list + search). The standalone "Dashboard" entry was
    // removed because it duplicated the same content.
    { to: '/managed/ui/workspaces', label: t('nav_workspaces'), icon: '01', visible: true },
    { to: '/managed/admin/workspaces/ui', label: t('nav_admin'), icon: '02', visible: isInstanceAdmin.value },
  ].filter(item => item.visible),
)

const pageTitle = computed(() => {
  const name = String(route.name ?? '')
  if (name === 'workspace-detail') return formatSlug(String(route.params.slug ?? '')) || t('nav_workspaces')
  if (name === 'admin-workspaces') return t('nav_admin')
  if (name === 'dashboard') return t(isInstanceAdmin.value ? 'dash_instance_title' : 'dash_workspace_title')
  if (name === 'workspaces') return t('my_workspaces_page_title')
  return t('nav_workspaces')
})

const pageKicker = computed(() => {
  const name = String(route.name ?? '')
  if (name === 'workspace-detail') return t('workspace_kicker')
  if (name === 'admin-workspaces') return t('admin_kicker')
  if (name === 'dashboard') return t('dash_kicker')
  return t('workspace_surface_kicker')
})

const workspaceContext = computed(() => {
  const slug = String(route.params.slug ?? '').trim()
  if (!slug) return null
  return {
    to: `/managed/ui/workspaces/${encodeURIComponent(slug)}`,
    title: formatSlug(slug),
  }
})

watch(
  () => route.fullPath,
  () => {
    routeAnnouncement.value = pageTitle.value
    sidebarOpen.value = false
  },
  { immediate: true },
)

onMounted(() => {
  document.body.classList.add('managed-shell')
})

onBeforeUnmount(() => {
  document.body.classList.remove('managed-shell')
})

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function closeSidebar() {
  sidebarOpen.value = false
}

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + '/')
}

function formatSlug(value: string): string {
  return value
    .split('-')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}
</script>

<style scoped>
.skip-link {
  position: absolute;
  top: -100%;
  left: 16px;
  z-index: 1000;
  padding: 8px 16px;
  background: var(--accent);
  color: var(--button-accent-text);
  border-radius: 0 0 8px 8px;
  font-weight: 600;
  font-size: 0.85rem;
  text-decoration: none;
  transition: top var(--transition-fast);
}
.skip-link:focus {
  top: 0;
}

.route-announcer {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.shell-overlay {
  position: fixed;
  inset: 0;
  background: rgba(8, 10, 20, 0.58);
  backdrop-filter: blur(6px);
  z-index: 109;
}

.shell-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: 264px;
  padding: 22px 18px 18px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  background: color-mix(in srgb, var(--surface-1) 88%, transparent);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-right: 1px solid var(--glass-border);
  box-shadow: 24px 0 60px rgba(0, 0, 0, 0.24);
  z-index: 120;
  transform: translateX(-100%);
  transition: transform var(--transition-spring);
}
.shell-sidebar-open {
  transform: translateX(0);
}

.sidebar-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--text-1);
  text-decoration: none;
  min-width: 0;
}
.mark {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: var(--accent);
  box-shadow: 0 0 18px var(--accent-glow);
  flex-shrink: 0;
}
.brand-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.brand-title {
  font-size: 1.06rem;
  letter-spacing: -0.02em;
}
.brand-sub {
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--text-3);
}
.sidebar-close {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--text-2);
  cursor: pointer;
  font-size: 1.2rem;
  line-height: 1;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sidebar-label {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 600;
}
.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  color: var(--text-2);
  text-decoration: none;
  border: 1px solid transparent;
  transition: all var(--transition-fast);
}
.sidebar-link:hover {
  background: var(--glass-bg);
  border-color: var(--glass-border);
  color: var(--text-1);
}
.sidebar-link[aria-current="page"] {
  background: linear-gradient(135deg, var(--accent-subtle), transparent 75%);
  border-color: var(--accent-glow);
  color: var(--text-1);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.14), 0 0 26px var(--accent-subtle);
}
.sidebar-link-icon {
  min-width: 28px;
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--accent);
  font-size: 0.66rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}
.sidebar-link-text {
  font-size: 0.92rem;
  font-weight: 600;
}

.sidebar-context {
  margin-top: 4px;
}
.context-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px;
  border-radius: 18px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  color: var(--text-1);
  text-decoration: none;
  transition: all var(--transition-fast);
}
.context-card:hover,
.context-card[aria-current="page"] {
  border-color: var(--accent-glow);
  box-shadow: 0 0 30px var(--accent-subtle);
}
.context-kicker {
  font-size: 0.68rem;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 700;
}
.context-title {
  font-size: 1rem;
}
.context-body {
  font-size: 0.84rem;
  color: var(--text-2);
  line-height: 1.45;
}

.sidebar-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.user-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 18px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
}
.user-card-label {
  font-size: 0.68rem;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 700;
}
.user-card-email {
  color: var(--text-1);
  font-size: 0.88rem;
  line-height: 1.4;
  word-break: break-word;
}

.shell-topbar {
  position: fixed;
  top: 0;
  right: 0;
  left: 0;
  height: 78px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 20px;
  background: color-mix(in srgb, var(--surface-1) 82%, transparent);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--glass-border);
  z-index: 110;
}
.topbar-main {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}
.menu-button {
  width: 44px;
  height: 44px;
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  padding: 0 11px;
  border-radius: 14px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  color: var(--text-1);
}
.menu-button span {
  display: block;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
}
.topbar-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar-kicker {
  font-size: 0.68rem;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  font-weight: 700;
}
.topbar-title {
  font-size: 1rem;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.ghost-button {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  color: var(--text-2);
  padding: 10px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 600;
  transition: all var(--transition-fast);
}
.ghost-button:hover,
.sidebar-close:hover,
.menu-button:hover {
  border-color: var(--accent-glow);
  color: var(--text-1);
  box-shadow: var(--shadow-sm);
}

.sidebar-link:focus-visible,
.context-card:focus-visible,
.ghost-button:focus-visible,
.sidebar-close:focus-visible,
.menu-button:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

:global(body.managed-shell) {
  --managed-sidebar-width: 264px;
}
:global(body.managed-shell main#main-content) {
  padding-top: 78px;
}

@media (min-width: 941px) {
  .shell-overlay {
    display: none;
  }
  .shell-sidebar {
    transform: translateX(0);
  }
  .shell-topbar {
    left: var(--managed-sidebar-width);
    padding: 16px 24px;
    justify-content: flex-end;
  }
  .menu-button,
  .sidebar-close {
    display: none;
  }
  .topbar-copy {
    display: none;
  }
  :global(body.managed-shell main#main-content) {
    padding-top: 78px;
    padding-left: var(--managed-sidebar-width);
  }
}

@media (max-width: 940px) {
  .topbar-actions {
    gap: 8px;
  }
}

@media (max-width: 640px) {
  .shell-topbar {
    padding: 12px 14px;
    height: 72px;
  }
  .shell-sidebar {
    width: min(88vw, 280px);
    padding: 18px 14px 14px;
  }
  .topbar-title {
    font-size: 0.92rem;
  }
}
</style>
