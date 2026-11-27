function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function formatDebugResponse(raw: unknown): string {
  if (raw === null || raw === undefined) {
    return 'null'
  }
  if (typeof raw === 'string') {
    try {
      return JSON.stringify(JSON.parse(raw), null, 2)
    } catch {
      return raw
    }
  }
  if (isRecord(raw) && Array.isArray(raw.content)) {
    const parsedItems = raw.content.map((item) => {
      if (isRecord(item) && typeof item.text === 'string') {
        try {
          return { ...item, text: JSON.parse(item.text) as unknown }
        } catch {
          return item
        }
      }
      return item
    })
    return JSON.stringify({ ...raw, content: parsedItems }, null, 2)
  }
  return JSON.stringify(raw, null, 2)
}

export function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

export function highlightDebugJson(jsonStr: string): string {
  const escaped = escapeHtml(jsonStr)
  return escaped.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g,
    (match) => {
      let cls = 'json-number'
      if (/^"/.test(match)) {
        cls = /:$/.test(match) ? 'json-key' : 'json-string'
      } else if (/true|false/.test(match)) {
        cls = 'json-boolean'
      } else if (/null/.test(match)) {
        cls = 'json-null'
      }
      return `<span class="${cls}">${match}</span>`
    }
  )
}
