<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path v-for="(d, index) in paths" :key="index" :d="d" />
  </svg>
</template>

<script lang="ts">
export type RoomIconName =
  | 'users'
  | 'inbox'
  | 'clock'
  | 'user-plus'
  | 'power'
  | 'pin'
  | 'folder'
  | 'send'
  | 'activity'
  | 'code'
  | 'arrow-left'
  | 'info'
  | 'download'
  | 'trash'
  | 'x'
  | 'upload'
  | 'list'
  | 'chevron-left'
  | 'chevron-right'
  | 'sun'
  | 'moon'
  | 'monitor'

const ICON_PATHS: Record<RoomIconName, string[]> = {
  users: [
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    'M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2',
    'M16 3.13a4 4 0 0 1 0 7.75',
    'M21 21v-2a4 4 0 0 0-3-3.85',
  ],
  inbox: [
    'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M3 13h5l2 3h4l2-3h5',
  ],
  clock: [
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
    'M12 7v5l3 3',
  ],
  'user-plus': [
    'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    'M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2',
    'M16 11h6',
    'M19 8v6',
  ],
  power: [
    'M7 6a8 8 0 1 0 10 0',
    'M12 4v8',
  ],
  pin: [
    'M8 4h8',
    'M10 4v5l-3 5h10l-3-5V4',
    'M12 14v6',
  ],
  folder: [
    'M5 4h4l3 3h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  ],
  send: [
    'M10 14L21 3',
    'M21 3l-6.5 18a0.55 0.55 0 0 1-1 0L10 14l-7-3.5a0.55 0.55 0 0 1 0-1L21 3',
  ],
  activity: [
    'M3 12h4l3 8 4-16 3 8h4',
  ],
  code: [
    'M7 8l-4 4 4 4',
    'M17 8l4 4-4 4',
  ],
  'arrow-left': [
    'M5 12h14',
    'M5 12l6 6',
    'M5 12l6-6',
  ],
  info: [
    'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
    'M12 8h.01',
    'M11 12h1v4h1',
  ],
  download: [
    'M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
    'M7 11l5 5 5-5',
    'M12 4v12',
  ],
  trash: [
    'M4 7h16',
    'M10 11v6',
    'M14 11v6',
    'M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12',
    'M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3',
  ],
  x: [
    'M18 6L6 18',
    'M6 6l12 12',
  ],
  upload: [
    'M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2',
    'M7 9l5-5 5 5',
    'M12 4v12',
  ],
  list: [
    'M9 6h11',
    'M9 12h11',
    'M9 18h11',
    'M5 6v.01',
    'M5 12v.01',
    'M5 18v.01',
  ],
  'chevron-left': [
    'M15 6l-6 6 6 6',
  ],
  'chevron-right': [
    'M9 6l6 6-6 6',
  ],
  sun: [
    'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
    'M12 3v2',
    'M12 19v2',
    'M3 12h2',
    'M19 12h2',
    'M5.6 5.6l1.4 1.4',
    'M17 17l1.4 1.4',
    'M18.4 5.6L17 7',
    'M7 17l-1.4 1.4',
  ],
  moon: [
    'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z',
  ],
  monitor: [
    'M5 4h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
    'M7 20h10',
    'M9 16v4',
    'M15 16v4',
  ],
}

</script>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: RoomIconName; size?: number }>(), {
  size: 16,
})

const paths = computed(() => ICON_PATHS[props.name] || [])
</script>
