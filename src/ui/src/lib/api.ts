import { useEffect, useState } from 'react'
import type { Bilingual } from './i18n'

/** Shapes of spec/SPEC.md §5, §7 and §10 as the API returns them. */
export type Kpi = {
  pathway_id: string
  patients: number
  on_track_pct: number
  overdue: number
  dropped: number
  readmissions_30d: number
  readmission_rate_30d: number | null
  actions_executed: number
  actions_pending: number
  est_readmission_cost_eur: number | null
}

export type Action = {
  action_id: string
  agent: string
  type: string
  patient_id: string | null
  scope: Record<string, unknown> | null
  pathway_id: string | null
  payload: Record<string, unknown>
  rationale: Bilingual
  evidence: Record<string, unknown>[]
  autonomy_level: number
  status: 'proposed' | 'approved' | 'executed' | 'rejected' | 'undone'
  created_day: number
  executed_day: number | null
  decided_by: string | null
}

export type TimelineEvent = {
  day: number
  kind: 'event'
  event_id: string
  event_type: string
  code: string | null
  value: number | null
  facility_id: string | null
  facility_name: string | null
  source: 'sim' | 'agent_action'
  action_id: string | null
}

export type TimelineAction = Pick<Action, 'action_id' | 'type' | 'agent' | 'status' | 'rationale'> & {
  day: number
  kind: 'action'
}

/** GET /api/patients/{id} (SPEC §10, C15). */
export type Patient360 = {
  patient: {
    patient_id: string
    sex: 'F' | 'M'
    age: number
    comune_istat: string
    comune_name: string
    lives_alone: boolean
    distance_km: number
    conditions: string[]
  }
  pathways: Record<string, unknown>[]
  timeline: (TimelineEvent | TimelineAction)[]
}

export type Loaded<T> = { data?: T; error?: string }

/** GET a JSON path under /api once; `path` null waits. */
export function useApi<T>(path: string | null): Loaded<T> {
  const [state, setState] = useState<Loaded<T> & { path?: string }>({})
  useEffect(() => {
    if (path === null) return
    let live = true
    fetch(path)
      .then(async (r) => {
        if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
        return (await r.json()) as T
      })
      .then((data) => live && setState({ path, data }))
      .catch((e: unknown) => live && setState({ path, error: String(e) }))
    return () => {
      live = false
    }
  }, [path])
  return state.path === path ? state : {}
}
