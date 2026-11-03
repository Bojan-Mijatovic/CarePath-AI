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

/** GET /api/settings (SPEC §7.2): the autonomy level per action type. 0 observe, 1 propose, 2 do with
 * approval, 3 do alone. */
export type Autonomy = Record<string, { level: number; default: number; fixed: boolean }>

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
  /** C39: the cost per readmission behind every euro figure, with where it comes from */
  readmission_cost?: { eur: number; label: Bilingual } | null
  steps: {
    id: string
    label: Bilingual
    event: string
    codes?: string[]
    specialty?: string
    loinc?: string[]
    service?: string
    max_wait_days?: number
  }[]
  eligibility: { drug_names: Record<string, Bilingual> }
}

/** GET /api/kpi?level=ats (SPEC §5.2, C14): one row per day. */
export type KpiRow = Kpi & { day: number; level: string; key: string }

/** GET /api/capacity (C28): slot use and waits per facility of a service over 7 days. */
export type CapacityRow = {
  day: number
  facility_id: string
  name: string
  slots_total: number | null
  slots_booked: number | null
  use_pct: number | null
  bookings: number | null
  wait_mean: number | null
  wait_median: number | null
  wait_p90: number | null
}

/** A run summary of POST /api/whatif (C27). */
export type WhatIfRun = {
  run_id: string
  readmissions: number
  readmission_rate_30d: number | null
  on_track_pct: number
  overdue: number
  wait_days: number | null
}

export type WhatIf = {
  scenario: number
  facility_id: string
  facility: string
  service: string
  lever_day: number
  last_day: number
  months: number
  base_slots: number
  levers: { extra_slots: number }
  baseline: WhatIfRun
  agents: WhatIfRun
  lever: WhatIfRun
  avoided_readmissions: number
  /** C39: the avoided readmissions in euros, and the cost per readmission they are counted at */
  saving_eur?: number
  cost?: { eur: number; label: Bilingual }
  /** The PNE forecast to year end (C35): each arm's 30-day readmission rate on the year's last day. */
  pne?: {
    day: number
    baseline: PneYearEnd
    agents: PneYearEnd
    lever: PneYearEnd
    reference: { rate: number; label: Bilingual } | null
  }
}

export type PneYearEnd = { readmissions_30d: number; readmission_rate_30d: number | null }

/** GET /api/worklist (SPEC §5.2, C20): one call per patient, by risk; who the patient is (C37). */
export type WorklistRow = {
  rank: number
  patient_id: string
  risk_score: number
  reasons: Bilingual
  pathways: string[]
  escalation_step: number
  script: Bilingual | null
  outcome: string | null
  age: number
  lives_alone: boolean
  comune_name: string
}

/** GET /api/reveal/{scenario} (C37): what the agents' alarms found, next to what the scenario hid. */
export type Reveal = {
  scenario: number
  bottleneck: {
    found: { day: number; facility: string; asst_id: string } | null
    hidden: { facility: string; asst_id: string }
    match: boolean
  }
  mmg_group: { found: { day: number; group: string; text: Bilingual } | null; hidden: { group: string }; match: boolean }
  rural_comuni: {
    found: { day: number; text: Bilingual } | null
    hidden: { comuni: string[]; named: string[] }
    match: boolean
  }
}

/** GET /api/reports (C36): the Reporter's monthly reports, the latest first. `figures` keeps every number. */
export type Report = {
  report_id: string
  day: number
  month: number
  from_day: number
  pathway_id: string
  figures: Record<string, unknown>
  text: Bilingual
  wording: 'model' | 'template'
}

/** A ward Bed Finder considered (SPEC §6 `free_beds`, C42), best first. */
export type BedCandidate = {
  facility_id: string
  name: string
  ward: string
  ward_label: Bilingual
  beds_total: number
  free_now: number
  free_in_2d: number
  bed: number | null
  distance_km: number
  same_facility: boolean
}

/** POST /api/admissions (C42): the candidates and the bed_assignment, null when no ward has a bed free today. */
export type Admission = {
  admission: { run_id: string; patient_id: string; day: number; facility_id: string }
  candidates: BedCandidate[]
  action: Action | null
}

/** GET /api/investigations (SPEC §6, C24, C25), the latest first. */
export type Investigation = {
  investigation_id: string
  day: number
  pathway_id: string
  alert_id: string | null
  question: Bilingual
  steps: { step: number; tool: string; args: Record<string, unknown>; result_summary: Bilingual }[]
  /** `verified` and `issues` come from the Verifier (SPEC §6, C33); null when the step's call gave no data. */
  claims: { text: Bilingual; step: number; verified?: boolean | null; issues?: { kind: string; text: Bilingual }[] }[]
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

/** A decision sent to the API (POST or PUT with a JSON body); throws with the server's reason when refused. */
export async function send<T>(method: 'POST' | 'PUT', path: string, body?: unknown): Promise<T> {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return (await r.json()) as T
}

export type Loaded<T> = { data?: T; error?: string }

/** GET a JSON path under /api; `path` null waits. A new `refresh` value (the day, or the day and a decision
 * count) fetches it again and keeps the last data on screen until the new data arrives. */
export function useApi<T>(path: string | null, refresh?: number | string | null): Loaded<T> {
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
