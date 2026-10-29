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
    mmg_id: string
    lives_alone: boolean
    distance_km: number
    conditions: string[]
  }
  pathways: Record<string, unknown>[]
  timeline: (TimelineEvent | TimelineAction)[]
}

/** GET /api/map (SPEC §5.2, C18): one row per comune with enrolled patients. */
export type MapRow = {
  comune_istat: string
  pathway_id: string
  adherence_pct: number | null
  risk_mean: number | null
  high_risk_patients: number | null
  readmission_rate_30d: number | null
  alarm: boolean
}

export type PathwayStatus = 'on_track' | 'due_soon' | 'overdue' | 'dropped'

/** GET /api/sankey (SPEC §5.2, C15): last step done → next step, by status. */
export type SankeyRow = {
  pathway_id: string
  from_step: string | null
  to_step: string | null
  status: PathwayStatus
  patients: number
}

/** GET /api/pathways/{id} (SPEC §4, C22): the parts of the pathway file the console reads. */
export type Pathway = {
  pathway_id: string
  name: string
  label: Bilingual
  readmission_reference: { rate: number; label: Bilingual } | null
  steps: {
    id: string
    label: Bilingual
    event: string
    codes?: string[]
    specialty?: string
    loinc?: string[]
    service?: string
  }[]
  eligibility: { drug_names: Record<string, Bilingual> }
}

/** GET /api/investigations (SPEC §6, C24, C25), the latest first. */
export type Investigation = {
  investigation_id: string
  day: number
  pathway_id: string
  alert_id: string | null
  question: Bilingual
  steps: { step: number; tool: string; args: Record<string, unknown>; result_summary: Bilingual }[]
  claims: { text: Bilingual; step: number }[]
  conclusion: Bilingual
}

/** The step of the pathway an event completes, as engine.state matches it (SPEC §5.1); codes ending in * are
 * prefixes. */
export function stepOf(pathway: Pathway, e: TimelineEvent): Pathway['steps'][number] | undefined {
  const match = (patterns: string[] | undefined) =>
    !patterns || patterns.some((p) => (p.endsWith('*') ? (e.code ?? '').startsWith(p.slice(0, -1)) : e.code === p))
  return pathway.steps.find(
    (s) => s.event === e.event_type && match(s.codes) && match(s.loinc) && (!s.specialty || s.specialty === e.code),
  )
}

export type Loaded<T> = { data?: T; error?: string }

/** GET a JSON path under /api; `path` null waits. A new `refresh` value (the day) fetches it again and keeps
 * the last data on screen until the new data arrives. */
export function useApi<T>(path: string | null, refresh?: number | null): Loaded<T> {
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
  }, [path, refresh])
  return state.path === path ? state : {}
}
