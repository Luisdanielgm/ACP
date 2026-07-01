<template>
  <div>
    <header>
      <ManagedNav />
    </header>
    <main id="main-content">
      <section class="panel">
        <span class="panel-kicker">{{ t('workspace_control_kicker') }}</span>
        <h1 class="panel-title">{{ t('dash_workspace_title') }}</h1>
        <p class="panel-sub">{{ t('loading') }}</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ManagedNav from '../components/ManagedNav.vue'
import { useManagedAuth } from '../composables/useManagedAuth'
import { useManagedI18n } from '../i18n'

const { requireAuth } = useManagedAuth()
const { t } = useManagedI18n()
const router = useRouter()

onMounted(async () => {
  const currentUser = await requireAuth()
  if (!currentUser) return
  if (currentUser.default_workspace?.slug) {
    await router.replace(`/managed/ui/workspaces/${encodeURIComponent(currentUser.default_workspace.slug)}`)
    return
  }
  await router.replace('/managed/ui/workspaces')
})
</script>

<style scoped>
.panel {
  max-width: 760px;
  margin: 32px auto;
  padding: 28px;
}
.panel-kicker {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--accent);
  font-weight: 600;
}
.panel-title {
  color: var(--text-1);
}
.panel-sub {
  color: var(--text-2);
}
</style>
