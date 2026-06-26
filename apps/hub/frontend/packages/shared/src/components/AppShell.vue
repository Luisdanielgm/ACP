<template>
  <div class="app-shell">
    <slot />
  </div>
</template>

<style scoped>
.app-shell {
  position: relative;
  z-index: 1;
  min-height: 100vh;
}
</style>
