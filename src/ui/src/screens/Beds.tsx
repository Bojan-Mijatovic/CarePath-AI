import { useState } from 'react'
import {
  type Action,
  type Admission,
  type Autonomy as Levels,
  type BedCandidate,
  type Patient360,
  send,
  type TimelineEvent,
  useApi,
} from '../lib/api'
import { formatNumber, useLang } from '../lib/i18n'

const MARIA = 'p_00001'
const BED = 'bed_assignment'

/** An admission to place: a run, a patient and the day a doctor admitted them. */
export type BedTarget = { run: string; patientId: string; day: number }

const order = (a: Action) => Number(a.action_id.split('_').at(-1))

/** Demo step 9c (prototype "Posti letto", C42): a doctor has decided to admit; Bed Finder picks ward, hospital and
 * bed, and assigns it alone (level 3) or proposes it for the doctor to confirm (level 2). Without a target it
 * shows Maria's latest admission in the run without CarePath of the scenario on screen (day 47). */
export default function Beds({
  day,
  scenario,
  target,
}: {
  day: number | null
  scenario: number | null
  target: BedTarget | null
}) {
  const { lang, t } = useLang()
  const run = target?.run ?? (scenario === null ? null : `s${scenario}_baseline`)
  const patientId = target?.patientId ?? MARIA
  const [changes, setChanges] = useState(0)
  const [ms, setMs] = useState<number | null>(null)
  const [noBed, setNoBed] = useState<BedCandidate[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const refresh = `${day}-${changes}`
  const { data: patient, error: loadError } = useApi<Patient360>(
    run ? `/api/patients/${encodeURIComponent(patientId)}?run=${run}` : null,
    day,
  )
  const admissions = (patient?.timeline ?? []).filter(
    (i): i is TimelineEvent => i.kind === 'event' && i.event_type === 'ADMISSION' && i.day >= 0,
  )
  const admission = target ? admissions.find((e) => e.day === target.day) : admissions.at(-1)
  const { data: settings } = useApi<{ autonomy: Levels }>('/api/settings', refresh)
  const { data: actions } = useApi<Action[]>(
    run && admission ? `/api/actions?run=${run}&day=${admission.day}` : null,
    refresh,
  )

  if (loadError) return <p className="placeholder">{t('error.load', { detail: loadError })}</p>
  if (!patient || !run) return <p className="placeholder">{t('loading')}</p>
  if (!admission) return <p className="placeholder">{t('beds.noAdmission', { patient: patientId })}</p>

  const mine = (actions ?? []).filter((a) => a.type === BED && a.patient_id === patientId && a.status !== 'rejected')
  const action = mine.sort((a, b) => order(a) - order(b)).at(-1)
  const placed = action && action.status !== 'undone' ? action : undefined
  const level = settings?.autonomy[BED]?.level ?? 3
  const p = placed?.payload as
    | { facility_name: string; ward_label: { it: string; en: string }; bed: number; choice: number; candidates: BedCandidate[] }
    | undefined
  const candidates = p?.candidates ?? noBed ?? []
  const seconds = ms === null ? null : formatNumber(lang, ms / 1000, 2)

  const act = (work: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    work()
      .then(() => setChanges((k) => k + 1))
      .catch((e: unknown) => setError(t('beds.failed', { detail: String(e) })))
      .finally(() => setBusy(false))
  }
  const request = (choice = 0) =>
    act(async () => {
      if (choice && placed?.status === 'proposed') await send('POST', `/api/actions/${placed.action_id}/reject`)
      const started = performance.now()
      const out = await send<Admission>('POST', '/api/admissions', {
        patient_id: patientId,
        run,
        day: admission.day,
        choice,
      })
      setMs(performance.now() - started)
      setNoBed(out.action ? null : out.candidates)
    })
  const decide = (decision: 'approve' | 'reject' | 'undo') =>
    act(() => send('POST', `/api/actions/${placed?.action_id}/${decision}`))
  const setLevel = (l: number) =>
    l !== level && act(() => send('PUT', '/api/settings/autonomy', { type: BED, level: l }))

  const where = (c: BedCandidate) =>
    !c.free_now
      ? t('beds.freeLater', { n: c.free_in_2d })
      : c.same_facility
        ? t('beds.freeHere', { bed: c.bed ?? '–' })
        : t('beds.freeThere', { bed: c.bed ?? '–', km: formatNumber(lang, c.distance_km, 0) })

  return (
    <div className="overview beds">
      <section className="panel beds-head" aria-labelledby="h-bed-patient">
        <div className="beds-who">
          <div className="card-sub">{t('beds.er', { facility: admission.facility_name ?? '–', day: admission.day })}</div>
          <h2 id="h-bed-patient">
            {patientId} · {t('beds.age', { age: patient.patient.age })}
          </h2>
          <div className="beds-tags">
            <span className="tag">{t(run.endsWith('_baseline') ? 'patient.without' : 'patient.with')}</span>
            {candidates[0] && (
              <span className="tag">{t('beds.ward', { ward: candidates[0].ward_label[lang] })}</span>
            )}
          </div>
        </div>
        <div className="lang beds-mode" role="group" aria-label={t('beds.mode')}>
          {[2, 3].map((l) => (
            <button key={l} type="button" aria-pressed={level === l} disabled={busy} onClick={() => setLevel(l)}>
              {t(l === 3 ? 'beds.assignMode' : 'beds.confirmMode')}
            </button>
          ))}
        </div>
      </section>
      <p className="lead">{t('beds.lead')}</p>
      {error && <p className="placeholder">{error}</p>}

      {placed && p ? (
        <div className={placed.status === 'executed' ? 'beds-status ok' : 'beds-status wait'} role="status">
          <div className="beds-status-text">
            <strong>
              {t(
                placed.status === 'proposed'
                  ? 'beds.proposed'
                  : placed.decided_by === 'auto'
                    ? 'beds.assigned'
                    : 'beds.confirmed',
                { ward: p.ward_label[lang], facility: p.facility_name, bed: p.bed },
              )}
            </strong>
            <span>
              {[seconds && t('beds.time', { s: seconds }), t(placed.status === 'proposed' ? 'beds.waiting' : 'beds.audit')]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </div>
          {placed.status === 'executed' ? (
            <button type="button" disabled={busy} onClick={() => decide('undo')}>
              {t('beds.undo')}
            </button>
          ) : (
            <span className="beds-buttons">
              <button type="button" className="primary" disabled={busy} onClick={() => decide('approve')}>
                {t('beds.confirm')}
              </button>
              <button type="button" disabled={busy} onClick={() => decide('reject')}>
                {t('beds.reject')}
              </button>
            </span>
          )}
        </div>
      ) : (
        <div className="beds-status idle">
          <div className="beds-status-text">
            <span>{noBed ? t('beds.noBed') : action?.status === 'undone' ? t('beds.undone') : t('beds.guard')}</span>
          </div>
          <button type="button" className="primary" disabled={busy} onClick={() => request()}>
            {t(action ? 'beds.again' : 'beds.request')}
          </button>
        </div>
      )}

      {candidates.length > 0 && (
        <section className="panel" aria-labelledby="h-beds">
          <div className="card-sub">{seconds ? t('beds.foundIn', { s: seconds }) : t('beds.foundBy')}</div>
          <h2 id="h-beds">{t('beds.candidates')}</h2>
          <div className="beds-cards">
            {candidates.map((c, k) => {
              const chosen = p !== undefined && k === p.choice
              return (
                <div key={`${c.facility_id}-${c.ward}`} className={chosen ? 'beds-card chosen' : 'beds-card'}>
                  <div className="card-label">
                    {t(chosen ? (k === 0 ? 'beds.aiChoice' : 'beds.doctorChoice') : 'beds.alternative')}
                  </div>
                  <div className="beds-card-title">
                    {c.ward_label[lang]} · {c.name}
                  </div>
                  <div className="card-sub">{where(c)}</div>
                  {placed?.status === 'proposed' && !chosen && c.free_now > 0 && (
                    <button type="button" disabled={busy} onClick={() => request(k)}>
                      {t('beds.choose')}
                    </button>
                  )}
                </div>
              )
            })}
          </div>
          {placed && <p className="approval-rationale">{placed.rationale[lang]}</p>}
        </section>
      )}
    </div>
  )
}
