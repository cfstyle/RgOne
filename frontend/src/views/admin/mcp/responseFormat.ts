function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function tryParseJsonString(value: string): { ok: true; parsed: unknown } | { ok: false } {
  const trimmed = value.trim()
  if (!trimmed || (trimmed[0] !== '{' && trimmed[0] !== '[' && trimmed[0] !== '"')) {
    return { ok: false }
  }
  try {
    return { ok: true, parsed: JSON.parse(trimmed) as unknown }
  } catch {
    return { ok: false }
  }
}

function unwrapJsonItem(value: unknown): unknown {
  if (typeof value === 'string') {
    const res = tryParseJsonString(value)
    return res.ok ? unwrapJsonItem(res.parsed) : value
  }
  if (Array.isArray(value)) {
    return value.map(unwrapJsonItem)
  }
  if (isRecord(value)) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) {
      if ((k === 'text' || k === 'content') && (typeof v === 'string' || Array.isArray(v))) {
        out[k] = unwrapJsonItem(v)
      } else {
        out[k] = v
      }
    }
    return out
  }
  return value
}

export function formatDebugResponse(raw: unknown): string {
  if (raw === null || raw === undefined) {
    return 'null'
  }
  if (typeof raw === 'string') {
    const res = tryParseJsonString(raw)
    if (res.ok) {
      return JSON.stringify(unwrapJsonItem(res.parsed), null, 2)
    }
    return raw
  }
  if (Array.isArray(raw)) {
    const parsedItems = raw.map(unwrapJsonItem)
    if (
      parsedItems.length === 1 &&
      (isRecord(parsedItems[0]) || Array.isArray(parsedItems[0]))
    ) {
      return JSON.stringify(parsedItems[0], null, 2)
    }
    return JSON.stringify(parsedItems, null, 2)
  }
  if (isRecord(raw) && Array.isArray(raw.content)) {
    const parsedItems = raw.content.map(unwrapJsonItem)
    return JSON.stringify({ ...raw, content: parsedItems }, null, 2)
  }
  return JSON.stringify(unwrapJsonItem(raw), null, 2)
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
