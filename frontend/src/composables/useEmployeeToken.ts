import { computed, onScopeDispose, ref, watch } from 'vue'
import { api, type EmployeeTokenDetail } from '@/api'
import { useAuthStore } from '@/stores/auth'

export function useEmployeeToken() {
  const auth = useAuthStore()
  const detail = ref<EmployeeTokenDetail | null>(null)
  const failure = ref('')
  const pending = ref<'load' | 'claim' | 'reset' | null>(null)
  let active: AbortController | undefined

  async function update(operation: 'load' | 'claim' | 'reset', request: typeof api.getMyToken) {
    if (!auth.empToken) return false
    active?.abort()
    const controller = new AbortController()
    active = controller
    pending.value = operation
    failure.value = ''
    try {
      const result = await request(controller.signal)
      if (controller.signal.aborted) return false
      if (result?.emp_no !== auth.empNo || typeof result?.api_key !== 'string') {
        throw new Error('未能读取当前工号的专属 Key')
      }
      detail.value = result
      return true
    } catch (error) {
      if (!controller.signal.aborted) {
        failure.value = error instanceof Error ? error.message : '专属 Key 加载失败，请重试'
      }
      return false
    } finally {
      if (active === controller) {
        pending.value = null
        active = undefined
      }
    }
  }

  const reload = () => update('load', api.getMyToken)
  const claim = () => update('claim', api.claimMyToken)
  const reset = () => update('reset', api.resetMyToken)

  watch(() => auth.empToken, (token) => {
    active?.abort()
    active = undefined
    detail.value = null
    failure.value = ''
    pending.value = null
    if (token) void reload()
  }, { immediate: true })

  onScopeDispose(() => active?.abort())

  return {
    detail,
    failure,
    loading: computed(() => pending.value === 'load'),
    claiming: computed(() => pending.value === 'claim'),
    resetting: computed(() => pending.value === 'reset'),
    reload,
    claim,
    reset,
  }
}
