import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export type ThemeMode = 'light' | 'dark'
export type LayoutContext = 'admin' | 'portal'
export type DensityMode = 'comfortable' | 'compact'

export interface ThemePreset {
  id: string
  key: string
  name: string
  hex: string
  category: string
  description: string
  lowChroma?: boolean
  monochrome?: boolean
}

export type SeedPreset = ThemePreset

/**
 * 锁定全站唯一定制主题：Studio 极简 · 极简工程 (#1F1F1F)
 */
export const THEME_PRESETS: ThemePreset[] = [
  {
    id: 'studio-monochrome',
    key: 'studio-monochrome',
    name: 'Studio 极简',
    hex: '#1F1F1F',
    category: '极简工程',
    description: 'AI Studio 控制台纯白微阴影极简工程风',
    monochrome: true
  }
]

export const SEED_PRESETS = THEME_PRESETS

const THEME_STORAGE_KEY = 'm3-theme'
const SEED_STORAGE_KEY = 'm3-seed-color'
const CONTEXT_STORAGE_KEY = 'm3-layout-context'
const DENSITY_STORAGE_KEY = 'm3-density'

const safeStorage = {
  getItem: (key: string): string | null => {
    try {
      return typeof window !== 'undefined' && window.localStorage ? window.localStorage.getItem(key) : null
    } catch {
      return null
    }
  },
  setItem: (key: string, value: string): void => {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        window.localStorage.setItem(key, value)
      }
    } catch {
      // 容错静默
    }
  }
}

export const useThemeStore = defineStore('theme', () => {
  const currentTheme = ref<ThemeMode>('light')
  const seedColor = ref<string>('#1F1F1F')
  const layoutContext = ref<LayoutContext>('admin')
  const density = ref<DensityMode>('comfortable')

  const isDark = computed(() => currentTheme.value === 'dark')

  /**
   * Studio 极简 (#1F1F1F) 固化设计系统 Tokens
   */
  const applyM3Theme = (_seedHex: string, dark: boolean) => {
    try {
      const root = typeof document !== 'undefined' ? document.documentElement : null
      if (!root) return

      const monoTokens: Record<string, string> = dark
        ? {
            // 深色模式 (Dark Mode)
            '--md-sys-color-primary': '#E8EAED',
            '--md-sys-color-on-primary': '#1F1F1F',
            '--md-sys-color-primary-container': '#2A2B2D',
            '--md-sys-color-on-primary-container': '#E8EAED',
            '--md-sys-color-inverse-primary': '#1F1F1F',

            '--md-sys-color-secondary': '#9AA0A6',
            '--md-sys-color-on-secondary': '#1F1F1F',
            '--md-sys-color-secondary-container': '#252628',
            '--md-sys-color-on-secondary-container': '#E8EAED',

            '--md-sys-color-tertiary': '#9AA0A6',
            '--md-sys-color-on-tertiary': '#1F1F1F',
            '--md-sys-color-tertiary-container': '#252628',
            '--md-sys-color-on-tertiary-container': '#E8EAED',

            '--md-sys-color-error': '#F28B82',
            '--md-sys-color-on-error': '#601410',
            '--md-sys-color-error-container': '#8C1D18',
            '--md-sys-color-on-error-container': '#F9DEDC',

            '--md-sys-color-surface': '#131314',
            '--md-sys-color-surface-dim': '#0E0E0F',
            '--md-sys-color-surface-bright': '#37393B',
            '--md-sys-color-surface-container-lowest': '#1E1F20',
            '--md-sys-color-surface-container-low': '#161617',
            '--md-sys-color-surface-container': '#252628',
            '--md-sys-color-surface-container-high': '#2D2F31',
            '--md-sys-color-surface-container-highest': '#37393B',

            '--md-sys-color-on-surface': '#E8EAED',
            '--md-sys-color-on-surface-variant': '#9AA0A6',
            '--md-sys-color-outline': '#8C939D',
            '--md-sys-color-outline-variant': 'rgba(255, 255, 255, 0.08)',
            '--md-sys-color-inverse-surface': '#E3E3E3',
            '--md-sys-color-inverse-on-surface': '#1F1F1F',

            '--sys-status-success-bg': 'rgba(19, 115, 51, 0.25)',
            '--sys-status-success-text': '#81C995',
            '--sys-status-warning-bg': 'rgba(180, 83, 9, 0.25)',
            '--sys-status-warning-text': '#FDD663',
            '--sys-status-danger-bg': 'rgba(185, 28, 28, 0.25)',
            '--sys-status-danger-text': '#F28B82'
          }
        : {
            // 浅色模式 (Light Mode) - Studio 极简工程四级中性色阶
            '--md-sys-color-primary': '#1F1F1F',
            '--md-sys-color-on-primary': '#FFFFFF',
            '--md-sys-color-primary-container': '#F1F3F5',
            '--md-sys-color-on-primary-container': '#1F1F1F',
            '--md-sys-color-inverse-primary': '#E3E3E3',

            '--md-sys-color-secondary': '#5F6368',
            '--md-sys-color-on-secondary': '#FFFFFF',
            '--md-sys-color-secondary-container': '#F1F3F5',
            '--md-sys-color-on-secondary-container': '#1F1F1F',

            '--md-sys-color-tertiary': '#5F6368',
            '--md-sys-color-on-tertiary': '#FFFFFF',
            '--md-sys-color-tertiary-container': '#F1F3F5',
            '--md-sys-color-on-tertiary-container': '#1F1F1F',

            '--md-sys-color-error': '#B91C1C',
            '--md-sys-color-on-error': '#FFFFFF',
            '--md-sys-color-error-container': '#FEE2E2',
            '--md-sys-color-on-error-container': '#7F1D1D',

            '--md-sys-color-surface': '#F7F8FA',
            '--md-sys-color-surface-dim': '#EEF0F2',
            '--md-sys-color-surface-bright': '#FFFFFF',
            '--md-sys-color-surface-container-lowest': '#FFFFFF',
            '--md-sys-color-surface-container-low': '#F7F8FA',
            '--md-sys-color-surface-container': '#F1F3F5',
            '--md-sys-color-surface-container-high': '#ECEEF0',
            '--md-sys-color-surface-container-highest': '#E3E5E8',

            '--md-sys-color-on-surface': '#1F1F1F',
            '--md-sys-color-on-surface-variant': '#5F6368',
            '--md-sys-color-outline': '#8C939D',
            '--md-sys-color-outline-variant': 'rgba(0, 0, 0, 0.04)',
            '--md-sys-color-inverse-surface': '#28292A',
            '--md-sys-color-inverse-on-surface': '#F2F2F2',

            '--sys-status-success-bg': '#E6F4EA',
            '--sys-status-success-text': '#137333',
            '--sys-status-warning-bg': '#FEF3C7',
            '--sys-status-warning-text': '#B45309',
            '--sys-status-danger-bg': '#FEE2E2',
            '--sys-status-danger-text': '#B91C1C'
          }

      for (const [varName, varVal] of Object.entries(monoTokens)) {
        root.style.setProperty(varName, varVal)
      }
    } catch (e) {
      console.warn('Failed to apply Studio Monochrome theme:', e)
    }
  }

  const setTheme = (theme: ThemeMode, persist = true) => {
    currentTheme.value = theme
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.theme = theme
    }
    if (persist) safeStorage.setItem(THEME_STORAGE_KEY, theme)
    applyM3Theme(seedColor.value, theme === 'dark')
  }

  const toggleTheme = () => {
    setTheme(currentTheme.value === 'dark' ? 'light' : 'dark')
  }

  const setSeedColor = (_hex: string) => {
    seedColor.value = '#1F1F1F'
    safeStorage.setItem(SEED_STORAGE_KEY, '#1F1F1F')
    applyM3Theme('#1F1F1F', isDark.value)
  }

  const setLayoutContext = (ctx: LayoutContext) => {
    layoutContext.value = ctx
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.context = ctx
    }
    safeStorage.setItem(CONTEXT_STORAGE_KEY, ctx)
  }

  const setDensity = (den: DensityMode) => {
    density.value = den
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.density = den
    }
    safeStorage.setItem(DENSITY_STORAGE_KEY, den)
  }

  const initTheme = () => {
    // 1. 初始化主题（明暗）
    const savedTheme = safeStorage.getItem(THEME_STORAGE_KEY)
    if (savedTheme === 'dark' || savedTheme === 'light') {
      currentTheme.value = savedTheme
    } else {
      currentTheme.value = 'light'
    }
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.theme = currentTheme.value
    }

    // 2. 锁定种子色为 Studio 极简 #1F1F1F
    seedColor.value = '#1F1F1F'
    safeStorage.setItem(SEED_STORAGE_KEY, '#1F1F1F')

    // 3. 初始化场景预设与密度
    const savedContext = safeStorage.getItem(CONTEXT_STORAGE_KEY)
    if (savedContext === 'admin' || savedContext === 'portal') {
      layoutContext.value = savedContext
    }
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.context = layoutContext.value
    }

    const savedDensity = safeStorage.getItem(DENSITY_STORAGE_KEY)
    if (savedDensity === 'comfortable' || savedDensity === 'compact') {
      density.value = savedDensity
    }
    if (typeof document !== 'undefined') {
      document.documentElement.dataset.density = density.value
    }

    // 4. 执行动态色板注入
    applyM3Theme(seedColor.value, currentTheme.value === 'dark')
  }

  return {
    currentTheme,
    isDark,
    seedColor,
    layoutContext,
    density,
    THEME_PRESETS,
    themePresets: THEME_PRESETS,
    seedPresets: THEME_PRESETS,
    toggleTheme,
    setTheme,
    setSeedColor,
    setLayoutContext,
    setDensity,
    applyM3Theme,
    initTheme
  }
})
