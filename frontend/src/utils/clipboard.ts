/**
 * 健壮的内网多环境剪贴板复制工具
 * - 优先使用现代 Clipboard API
 * - 在普通 HTTP / 权限受限或非安全上下文中平滑降级到 document.execCommand
 * - 若全部失败则提供备用提示，只有真正写入成功才返回 true
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false

  // 1. 尝试现代 Clipboard API（仅安全上下文且浏览器授权时可用）
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (e) {
      console.warn('Clipboard API 写入失败或权限被拒，降级到 execCommand', e)
    }
  }

  // 2. 降级方案：创建隐藏 textarea 选中文本执行 execCommand('copy')
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    // 避免页面跳动与键盘弹出
    textArea.style.position = 'fixed'
    textArea.style.top = '-9999px'
    textArea.style.left = '-9999px'
    textArea.style.opacity = '0'
    textArea.setAttribute('readonly', '')
    document.body.appendChild(textArea)

    textArea.focus()
    textArea.select()
    textArea.setSelectionRange(0, 99999)

    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    if (successful) {
      return true
    }
  } catch (err) {
    console.warn('execCommand 复制执行失败', err)
  }

  // 3. 若浏览器完全拒绝写入，提供用户手动提示并选中文本
  window.prompt('当前内网浏览器限制自动剪贴板写入，请按 Ctrl+C 手动复制文本：', text)
  return false
}
