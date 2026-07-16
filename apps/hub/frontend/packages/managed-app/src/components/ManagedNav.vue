<template>
  <a href="#main-content" class="skip-link">{{ t('skip_to_content') }}</a>
  <div class="route-announcer" role="status" aria-live="polite" aria-atomic="true">{{ routeAnnouncement }}</div>

  <div
    v-if="sidebarOpen"
    class="shell-overlay"
    aria-hidden="true"
    @click="closeSidebar"
  ></div>

  <aside
    class="shell-sidebar"
    :class="{ 'shell-sidebar-open': sidebarOpen, 'shell-sidebar-collapsed': sidebarCollapsed }"
    :aria-label="t('nav_menu')"
  >
    <div class="sidebar-head">
      <RouterLink to="/managed/ui/workspaces" class="brand">
        <span class="mark" aria-hidden="true"></span>
        <span class="brand-copy">
          <strong class="brand-title">{{ brandTitle }}</strong>
          <span class="brand-sub">{{ brandSub }}</span>
          <span v-if="user" class="brand-user" :title="t('role_' + user.role)">{{ user.email }}</span>
        </span>
      </RouterLink>
      <button class="sidebar-close" type="button" :aria-label="t('nav_close_menu')" @click="closeSidebar">
        &times;
      </button>
    </div>

    <button
      class="sidebar-collapse"
      type="button"
      :aria-label="t(sidebarCollapsed ? 'nav_expand_sidebar' : 'nav_collapse_sidebar')"
      :title="t(sidebarCollapsed ? 'nav_expand_sidebar' : 'nav_collapse_sidebar')"
      :aria-expanded="!sidebarCollapsed"
      @click="toggleCollapsed"
    >
      <RoomIcon :name="sidebarCollapsed ? 'chevron-right' : 'chevron-left'" :size="15" />
    </button>

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

    <div v-if="workspaceContext && !isSingleWorkspace" class="sidebar-section sidebar-context">
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
      <button
        class="footer-icon"
        type="button"
        :aria-label="t('nav_theme_toggle') + ': ' + theme"
        :title="t('nav_theme_toggle') + ': ' + theme"
        @click="cycleTheme"
      >
        <RoomIcon :name="themeIcon" :size="16" />
      </button>
      <button
        class="footer-icon footer-lang"
        type="button"
        :aria-label="t('nav_lang_toggle')"
        :title="t('nav_lang_toggle')"
        @click="toggleLocale"
      >
        {{ locale.toUpperCase() }}
      </button>
      <button
        class="footer-icon footer-logout"
        type="button"
        :aria-label="t('logout')"
        :title="t('logout')"
        @click="logout"
      >
        <RoomIcon name="power" :size="16" />
      </button>
    </div>
  </aside>

  <header class="shell-topbar">
    <div class="topbar-main">
      <button class="menu-button" type="button" :aria-label="sidebarOpen ? t('nav_close_menu') : t('nav_open_menu')" @click="toggleSidebar">
        <span></span>
        <span></span>
        <span></span>
      </button>
      <RouterLink
        v-if="backLink"
        :to="backLink.to"
        class="topbar-back"
        :aria-label="backLink.label"
        :title="backLink.label"
      >
        <RoomIcon name="arrow-left" :size="16" />
      </RouterLink>
      <div v-if="!isSessionRoute" class="topbar-copy">
        <span class="topbar-kicker">{{ pageKicker }}</span>
        <strong class="topbar-title">{{ pageTitle }}</strong>
        <Breadcrumbs />
      </div>
    </div>

    <!-- Session routes teleport the live room bar here (see RoomLive.vue). -->
    <div id="managed-topbar-session" class="topbar-session"></div>
  </header>

  <ToastContainer :dismiss-label="t('dismiss')" />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useTheme, type ThemeMode } from '@acp/shared'
import ToastContainer from './ToastContainer.vue'
import Breadcrumbs from './Breadcrumbs.vue'
import RoomIcon, { type RoomIconName } from './room/RoomIcon.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'

const SIDEBAR_COLLAPSED_KEY = 'acp_managed_sidebar_collapsed'

type NavItem = {
  to: string
  label: string
  icon: string
  visible: boolean
}

const route = useRoute()
const { isSingleWorkspace, user, logout } = useManagedAuth()
const { t, locale, setLocale } = useManagedI18n()
const { theme, setTheme } = useTheme()

const THEME_CYCLE: ThemeMode[] = ['dark', 'light', 'system']
const THEME_ICONS: Record<ThemeMode, RoomIconName> = {
  dark: 'moon',
  light: 'sun',
  system: 'monitor',
}

const themeIcon = computed(() => THEME_ICONS[theme.value])

function cycleTheme() {
  const next = THEME_CYCLE[(THEME_CYCLE.indexOf(theme.value) + 1) % THEME_CYCLE.length]
  setTheme(next)
}

function toggleLocale() {
  setLocale(locale.value === 'es' ? 'en' : 'es')
}

const isSessionRoute = computed(() => String(route.name ?? '') === 'session-detail')

const routeAnnouncement = ref('')
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(readCollapsedPreference())

function readCollapsedPreference(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
  } catch {
    return false
  }
}

function toggleCollapsed() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try {
    localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
  } catch {
    // Preference persistence is best-effort.
  }
}

watch(sidebarCollapsed, value => {
  document.body.classList.toggle('managed-sidebar-collapsed', value)
})

const backLink = computed(() => {
  if (String(route.name ?? '') !== 'session-detail') return null
  const slug = String(route.params.slug ?? '').trim()
  if (!slug) return null
  return {
    to: `/managed/ui/workspaces/${encodeURIComponent(slug)}`,
    label: t('session_back_to_sessions'),
  }
})

const singleWorkspaceHomePath = computed(() => {
  const slug = user.value?.default_workspace?.slug
  return slug ? `/managed/ui/workspaces/${encodeURIComponent(slug)}` : '/managed/ui/workspaces'
})

const brandTitle = computed(() => t(isSingleWorkspace.value ? 'app_brand_workspace' : 'app_brand_managed'))
const brandSub = computed(() => t(isSingleWorkspace.value ? 'workspace_control_kicker' : 'dash_kicker'))

const navItems = computed<NavItem[]>(() =>
  [
    {
      to: singleWorkspaceHomePath.value,
      label: t(isSingleWorkspace.value ? 'nav_workspace' : 'nav_workspaces'),
      icon: '01',
      visible: true,
    },
  ].filter(item => item.visible),
)

const pageTitle = computed(() => {
  const name = String(route.name ?? '')
  if (name === 'workspace-detail') return formatSlug(String(route.params.slug ?? '')) || t('nav_workspace')
  if (name === 'dashboard') return t('dash_workspace_title')
  if (name === 'workspaces') return t('my_workspaces_page_title')
  return t(isSingleWorkspace.value ? 'nav_workspace' : 'nav_workspaces')
})

const pageKicker = computed(() => {
  const name = String(route.name ?? '')
  if (name === 'workspace-detail') return t('workspace_kicker')
  if (name === 'dashboard') return t(isSingleWorkspace.value ? 'workspace_control_kicker' : 'dash_kicker')
  return t(isSingleWorkspace.value ? 'workspace_kicker' : 'workspace_surface_kicker')
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
  document.body.classList.toggle('managed-sidebar-collapsed', sidebarCollapsed.value)
})

onBeforeUnmount(() => {
  document.body.classList.remove('managed-shell')
  document.body.classList.remove('managed-sidebar-collapsed')
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
.brand-user {
  margin-top: 6px;
  font-size: 0.76rem;
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  flex-direction: row;
  align-items: center;
  gap: 8px;
}
.footer-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 12px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--text-2);
  cursor: pointer;
  transition: all var(--transition-fast);
}
.footer-icon:hover {
  color: var(--text-1);
  border-color: var(--accent-glow);
}
.footer-lang {
  font-size: 0.7rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}
.footer-logout:hover {
  color: var(--danger);
  border-color: var(--danger-glow);
}

.shell-topbar {
  position: fixed;
  top: 0;
  right: 0;
  left: 0;
  height: var(--managed-topbar-height, 56px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 8px 16px;
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
  width: 34px;
  height: 34px;
  display: inline-flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  padding: 0 8px;
  border-radius: 10px;
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
.topbar-session {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}
.topbar-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--text-2);
  text-decoration: none;
  transition: all var(--transition-fast);
}
.topbar-back:hover {
  border-color: var(--accent-glow);
  color: var(--text-1);
}
.topbar-back:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

.sidebar-close:hover,
.menu-button:hover {
  border-color: var(--accent-glow);
  color: var(--text-1);
  box-shadow: var(--shadow-sm);
}

.sidebar-link:focus-visible,
.context-card:focus-visible,
.footer-icon:focus-visible,
.sidebar-close:focus-visible,
.menu-button:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

:global(body.managed-shell) {
  --managed-sidebar-width: 264px;
  --managed-topbar-height: 56px;
}
:global(body.managed-shell main#main-content) {
  padding-top: var(--managed-topbar-height);
}

/* Collapse toggle: desktop-only affordance on the sidebar edge */
.sidebar-collapse {
  display: none;
  position: absolute;
  top: 30px;
  right: -14px;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border-radius: 999px;
  border: 1px solid var(--glass-border);
  background: var(--surface-1);
  color: var(--text-2);
  cursor: pointer;
  z-index: 2;
  transition: all var(--transition-fast);
}
.sidebar-collapse:hover {
  color: var(--text-1);
  border-color: var(--accent-glow);
}
.sidebar-collapse:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-subtle);
}

@media (min-width: 941px) {
  .shell-overlay {
    display: none;
  }
  .shell-sidebar {
    transform: translateX(0);
    transition: width var(--transition-spring);
  }
  .shell-topbar {
    left: var(--managed-sidebar-width);
    padding: 8px 20px;
    transition: left var(--transition-spring);
  }
  .menu-button,
  .sidebar-close {
    display: none;
  }
  .sidebar-collapse {
    display: inline-flex;
  }
  :global(body.managed-shell main#main-content) {
    padding-top: var(--managed-topbar-height);
    padding-left: var(--managed-sidebar-width);
    transition: padding-left var(--transition-spring);
  }
  :global(body.managed-shell.managed-sidebar-collapsed) {
    --managed-sidebar-width: 76px;
  }
  .shell-sidebar-collapsed {
    width: 76px;
    padding: 22px 12px 18px;
    align-items: center;
  }
  .shell-sidebar-collapsed .brand-copy,
  .shell-sidebar-collapsed .sidebar-label,
  .shell-sidebar-collapsed .sidebar-link-text,
  .shell-sidebar-collapsed .sidebar-context {
    display: none;
  }
  .shell-sidebar-collapsed .sidebar-head {
    justify-content: center;
  }
  .shell-sidebar-collapsed .sidebar-nav {
    align-items: center;
  }
  .shell-sidebar-collapsed .sidebar-link {
    padding: 8px;
    border-radius: 12px;
  }
  .shell-sidebar-collapsed .sidebar-footer {
    flex-direction: column;
    align-items: center;
  }
}

@media (max-width: 640px) {
  .shell-topbar {
    padding: 8px 12px;
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
