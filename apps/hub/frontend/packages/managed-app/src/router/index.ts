import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'landing',
    component: () => import('@acp/public-app/views/LandingView.vue'),
  },
  {
    path: '/managed',
    redirect: '/managed/login',
  },
  {
    path: '/managed/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
  },
  {
    path: '/managed/dashboard',
    name: 'dashboard',
    // The standalone "instance dashboard" view was retired in favor of the
    // admin workspaces surface, which already contains the create form, the
    // workspace list, and search. Workspace admins go to their own list.
    component: () => import('../views/ManagedDashboardView.vue'),
    beforeEnter: async (_to, _from, next) => {
      try {
        const { fetchMe } = await import('../api/managed')
        const me = await fetchMe()
        if (!me) {
          return next()
        }
        if (me.role === 'instance_admin') {
          return next({ path: '/managed/admin/workspaces/ui', replace: true })
        }
        return next({ path: '/managed/ui/workspaces', replace: true })
      } catch {
        // Not authenticated; let the view's own requireAuth handle the redirect.
      }
      next()
    },
  },
  {
    path: '/managed/dashboard/session',
    name: 'managed-session-dashboard',
    component: () => import('../views/SessionLiveView.vue'),
  },
  {
    path: '/managed/ui/workspaces',
    name: 'workspaces',
    component: () => import('../views/WorkspaceListView.vue'),
  },
  {
    path: '/managed/ui/workspaces/:slug',
    name: 'workspace-detail',
    component: () => import('../views/WorkspaceDetailView.vue'),
  },
  {
    path: '/managed/ui/workspaces/:slug/sessions',
    name: 'workspace-sessions',
    redirect: to => ({ name: 'workspace-detail', params: { slug: String(to.params.slug ?? '') } }),
  },
  {
    path: '/managed/ui/workspaces/:slug/sessions/:sessionId',
    name: 'session-detail',
    redirect: to => ({
      name: 'session-live',
      params: {
        slug: String(to.params.slug ?? ''),
        sessionId: String(to.params.sessionId ?? ''),
      },
    }),
  },
  {
    path: '/managed/ui/workspaces/:slug/sessions/:sessionId/live',
    name: 'session-live',
    component: () => import('../views/SessionLiveView.vue'),
  },
  {
    path: '/managed/admin/workspaces/ui',
    name: 'admin-workspaces',
    component: () => import('../views/WorkspaceAdminView.vue'),
  },
  {
    path: '/managed/invitations/:token',
    name: 'invitation',
    component: () => import('../views/InvitationView.vue'),
  },
  {
    path: '/downloads',
    name: 'downloads',
    component: () => import('@acp/public-app/views/DownloadsView.vue'),
  },
  {
    path: '/dashboard',
    redirect: '/managed/login',
  },
  {
    path: '/dashboard/session',
    redirect: '/managed/login',
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/managed/login',
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
