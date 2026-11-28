<script setup lang="ts">
import WorkbenchUsage from './WorkbenchUsage.vue'
import WorkbenchMcp from './WorkbenchMcp.vue'
import WorkbenchTiles from './WorkbenchTiles.vue'

defineProps<{ embed?: boolean }>()
</script>

<template>
  <div :class="['workbench', { 'workbench--compact': embed }]">
    <WorkbenchUsage :embed="embed" />
    <WorkbenchMcp :embed="embed" />
    <WorkbenchTiles :embed="embed" />
  </div>
</template>

<style scoped>
.workbench { display: grid; gap: 28px; min-width: 0; }
.workbench--compact { gap: 20px; }
</style>
