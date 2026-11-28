import { Briefcase, Code, Database, FileText, Globe, Shield, Sparkles, Zap } from 'lucide-vue-next'
import { request } from '@/api'

export const tileIcons = { Sparkles, Code, FileText, Globe, Database, Shield, Briefcase, Zap }

export interface TileDraft {
  title: string
  subtitle: string
  tile_type: 'prompt' | 'link'
  icon: keyof typeof tileIcons
  payload: string
  category: string | null
  sort_order: number
  is_enabled: boolean
}

export interface WorkbenchTile extends TileDraft {
  id: number
  owner_emp_no: string | null
  created_at: string
  updated_at: string
}

export interface TileList {
  tiles: WorkbenchTile[]
  hidden_presets: WorkbenchTile[]
}

export function newTile(): TileDraft {
  return { title: '', subtitle: '', tile_type: 'prompt', icon: 'Sparkles', payload: '',
    category: null, sort_order: 0, is_enabled: true }
}

export function safeTileLink(value: string): { url: string; internal: boolean } | undefined {
  const url = value.trim()
  if (/[\s\\]/.test(url) || Array.from(url).some(char => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127)) return undefined
  if (url.startsWith('/') && !url.startsWith('//')) return { url, internal: true }
  if (!/^https?:\/\//i.test(url)) return undefined
  try {
    const parsed = new URL(url)
    if (parsed.hostname && !parsed.username && !parsed.password && parsed.port !== '0') {
      return { url: parsed.href, internal: false }
    }
  } catch {
    return undefined
  }
  return undefined
}

function isTile(value: unknown): value is WorkbenchTile {
  if (!value || typeof value !== 'object') return false
  const tile = value as Partial<WorkbenchTile>
  return Number.isSafeInteger(tile.id) && typeof tile.title === 'string' &&
    typeof tile.subtitle === 'string' && typeof tile.payload === 'string' &&
    (tile.category === null || typeof tile.category === 'string') &&
    (tile.owner_emp_no === null || typeof tile.owner_emp_no === 'string') &&
    (tile.tile_type === 'prompt' || tile.tile_type === 'link') &&
    typeof tile.icon === 'string' && Object.prototype.hasOwnProperty.call(tileIcons, tile.icon) &&
    Number.isInteger(tile.sort_order) && typeof tile.is_enabled === 'boolean'
}

function readTiles(value: unknown): WorkbenchTile[] {
  if (!Array.isArray(value) || !value.every(isTile)) throw new Error('磁贴数据格式异常')
  return value
}

const tilePath = (admin: boolean) => admin ? '/admin/workbench/presets' : '/workbench/tiles'

export const workbenchApi = {
  async list(admin: boolean, signal: AbortSignal): Promise<TileList> {
    if (admin) {
      return { tiles: readTiles(await request(tilePath(true), { signal }, true)), hidden_presets: [] }
    }
    const data = await request<Partial<TileList>>(tilePath(false), { signal })
    return { tiles: readTiles(data?.tiles), hidden_presets: readTiles(data?.hidden_presets) }
  },
  save(admin: boolean, signal: AbortSignal, tile: Partial<TileDraft>, id?: number) {
    const path = tilePath(admin)
    return request(id === undefined ? path : `${path}/${id}`, {
      method: id === undefined ? 'POST' : 'PATCH', body: JSON.stringify(tile), signal,
    }, admin)
  },
  remove(admin: boolean, id: number, signal: AbortSignal) {
    return request(`${tilePath(admin)}/${id}`, { method: 'DELETE', signal }, admin)
  },
  setHidden(id: number, hidden: boolean, signal: AbortSignal) {
    return request(`/workbench/presets/${id}/hide`, { method: hidden ? 'POST' : 'DELETE', signal })
  },
  reorder(items: { id: number; sort_order: number }[], signal: AbortSignal) {
    return request('/workbench/tiles/reorder', { method: 'POST', body: JSON.stringify({ items }), signal })
  },
}
