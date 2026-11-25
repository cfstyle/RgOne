import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const empToken = ref(localStorage.getItem('rgone_emp_token') || '')
  const empNo = ref(localStorage.getItem('rgone_emp_no') || '')
  const empName = ref(localStorage.getItem('rgone_emp_name') || '')

  const adminToken = ref(localStorage.getItem('rgone_admin_token') || '')
  const adminUsername = ref(localStorage.getItem('rgone_admin_username') || '')

  const isEmployeeLoggedIn = computed(() => !!empToken.value)
  const isAdminLoggedIn = computed(() => !!adminToken.value)

  function setEmployeeAuth(token: string, no: string, name: string) {
    empToken.value = token
    empNo.value = no
    empName.value = name
    localStorage.setItem('rgone_emp_token', token)
    localStorage.setItem('rgone_emp_no', no)
    localStorage.setItem('rgone_emp_name', name)
  }

  function logoutEmployee() {
    empToken.value = ''
    empNo.value = ''
    empName.value = ''
    localStorage.removeItem('rgone_emp_token')
    localStorage.removeItem('rgone_emp_no')
    localStorage.removeItem('rgone_emp_name')
  }

  function setAdminAuth(token: string, username: string) {
    adminToken.value = token
    adminUsername.value = username
    localStorage.setItem('rgone_admin_token', token)
    localStorage.setItem('rgone_admin_username', username)
  }

  function logoutAdmin() {
    adminToken.value = ''
    adminUsername.value = ''
    localStorage.removeItem('rgone_admin_token')
    localStorage.removeItem('rgone_admin_username')
  }

  return {
    empToken,
    empNo,
    empName,
    adminToken,
    adminUsername,
    isEmployeeLoggedIn,
    isAdminLoggedIn,
    setEmployeeAuth,
    logoutEmployee,
    setAdminAuth,
    logoutAdmin,
  }
})
