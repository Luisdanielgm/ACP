import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'landing',
    component: () => import('../views/LandingView.vue'),
  },
  {
    path: '/downloads',
    name: 'downloads',
    component: () => import('../views/DownloadsView.vue'),
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('../views/DashboardView.vue'),
  },
  {
    path: '/dashboard/session',
    name: 'session-dashboard',
    component: () => import('../views/SessionDashboardView.vue'),
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
