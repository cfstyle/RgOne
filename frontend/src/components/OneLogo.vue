<script setup lang="ts">
withDefaults(
  defineProps<{
    size?: number | string
    color?: string
  }>(),
  {
    size: 20,
    color: 'currentColor'
  }
)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 32 32"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    class="one-brand-logo"
  >
    <!-- Google One 灵感：纯粹现代几何数字 "1" 结构 -->
    <!-- 1 的前置引导勾角与主立柱 (一体化圆润几何) -->
    <path
      d="M10.5 13.8L16.2 9.2C16.6 8.9 17.2 9.2 17.2 9.8V23.5"
      :stroke="color"
      stroke-width="3.8"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <!-- 1 的稳固底座横线 -->
    <path
      d="M11.5 23.5H21"
      :stroke="color"
      stroke-width="3.8"
      stroke-linecap="round"
    />
    <!-- 右上方灵动四芒智能微星 (象征 AI 算力与灵感互联) -->
    <path
      d="M24.5 6.5C24.5 8.16 23.16 9.5 21.5 9.5C23.16 9.5 24.5 10.84 24.5 12.5C24.5 10.84 25.84 9.5 27.5 9.5C25.84 9.5 24.5 8.16 24.5 6.5Z"
      :fill="color"
    />
  </svg>
</template>

<style scoped>
.one-brand-logo {
  display: inline-block;
  vertical-align: middle;
  flex-shrink: 0;
  transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1);
}

.one-brand-logo:hover {
  transform: scale(1.08);
}
</style>
