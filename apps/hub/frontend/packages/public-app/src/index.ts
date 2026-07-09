export { default as SessionDashboardView } from './views/SessionDashboardView.vue'

export { default as AccessStrip } from './components/dashboard/AccessStrip.vue'
export { default as SessionSummary } from './components/dashboard/SessionSummary.vue'
export { default as SessionHealth } from './components/dashboard/SessionHealth.vue'
export { default as SquadMap } from './components/dashboard/SquadMap.vue'
export { default as MemberLanes } from './components/dashboard/MemberLanes.vue'
export { default as MemberRoster } from './components/dashboard/MemberRoster.vue'
export { default as EventTimeline } from './components/dashboard/EventTimeline.vue'
export { default as RawJsonPanel } from './components/dashboard/RawJsonPanel.vue'

export {
  useSessionDashboard,
  type UseSessionDashboardOptions,
  type DashboardContext,
  type AccessMode,
  type TimelineFilter,
} from './composables/useSessionDashboard'
