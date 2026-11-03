import { useState } from 'react'
import Origin from '../components/Origin'
import { type Pathway, type Patient360, stepOf, type TimelineEvent, useApi } from '../lib/api'
import { formatNumber, formatPercent, label, useLang } from '../lib/i18n'
import type { BedTarget } from './Beds'

const MARIA = 'p_00001'

/** Demo step 9b (prototype "Paziente 360"): one patient's state and timeline in either arm of the scenario on
 * screen (SPEC §10, C15). Steps and drugs are named from the pathway file (AC17); TELEMON_READING events,
 * one a day, are counted instead of listed. */
export default function Patient({
  day,
  scenario,
  pathway,
  onAdmission,
}: {
  day: number | null
  scenario: number | null
  pathway: Pathway | null
  /** An admission's link to Posti letto (demo step 9c, C42) */
  onAdmission: (target: BedTarget) => void
}) {
  const { lang, t } = useLang()
  const [draft, setDraft] = useState(MARIA)
  const [patientId, setPatientId] = useState(MARIA)
  const [arm, setArm] = useState<'agents' | 'baseline'>('agents')
  const path = scenario === null ? null : `/api/patients/${encodeURIComponent(patientId)}?run=s${scenario}_${arm}`
  const { data, error } = useApi<Patient360>(path, day)

  const stepName = (id: unknown) =>
    typeof id === 'string' ? (pathway?.steps.find((s) => s.id === id)?.label[lang] ?? id) : '–'
  const eventDetail = (e: TimelineEvent): string => {
    const step = (pathway && stepOf(pathway, e)?.label[lang]) ?? ''
    // The step's name only where it adds to the event type's own label, which may already say it.
    const parts = [label(t, 'event', e.event_type).toLowerCase().includes(step.toLowerCase()) ? '' : step]
    if (e.event_type === 'DISPENSE') parts.push(pathway?.eligibility.drug_names[e.code ?? '']?.[lang] ?? e.code ?? '')
    else if (e.event_type === 'BOOKING' && e.value !== null) {
      const booked = pathway?.steps.find((s) => s.service === e.code)?.label[lang] ?? e.code
      parts.push(`${booked} ${t('patient.bookedFor', { day: e.value })}`)
    }
    else if (e.event_type === 'ADMISSION' && e.value === 1) parts.push(t('patient.unplanned'))
    else if (e.event_type === 'CALL') parts.push(e.code ?? '')
    if (e.facility_name) parts.push(e.facility_name)
    return parts.filter(Boolean).join(' · ')
  }

  const switcher = (
    <div className="patient-bar">
      <form
        className="patient-pick"
        onSubmit={(ev) => {
          ev.preventDefault()
          setPatientId(draft.trim())
        }}
      >
        <label htmlFor="patient-id">{t('patient.label')}</label>
        <input id="patient-id" value={draft} onChange={(ev) => setDraft(ev.target.value)} />
        <button type="submit">{t('patient.show')}</button>
      </form>
      <div className="lang" role="group" aria-label={t('patient.with')} data-spot="patient-arm">
        {(['agents', 'baseline'] as const).map((a) => (
          <button key={a} type="button" aria-pressed={arm === a} onClick={() => setArm(a)}>
            {t(a === 'agents' ? 'patient.with' : 'patient.without')}
          </button>
        ))}
      </div>
    </div>
  )
  if (error || !data || !pathway) {
    const note = error ? (error.startsWith('404') ? t('patient.notFound') : t('error.load', { detail: error })) : t('loading')
    return (
      <div className="patient">
        {switcher}
        <p className="placeholder">{note}</p>
      </div>
    )
  }

  const p = data.patient
  const events = data.timeline.filter((i) => i.day >= 0)
  const readings = events.filter((i) => i.kind === 'event' && i.event_type === 'TELEMON_READING').length
  const shown = events.filter((i) => !(i.kind === 'event' && i.event_type === 'TELEMON_READING'))

  return (
    <div className="patient">
      {switcher}
      <section className="panel">
        <h2>{p.patient_id}</h2>
        <div className="card-sub">
          {t('patient.header', {
            age: p.age,
            comune: p.comune_name,
            alone: p.lives_alone ? t(p.sex === 'F' ? 'patient.alone' : 'patient.aloneM') : '',
            km: formatNumber(lang, p.distance_km, 1),
            mmg: p.mmg_id,
          })}
        </div>
        {data.pathways.map((s) => (
          <div key={String(s.pathway_id)} className="patient-state">
            <span className="tag">{pathway.pathway_id === s.pathway_id ? pathway.label[lang] : String(s.pathway_id)}</span>
            <div>
              {t('patient.state', {
                status: label(t, 'status', String(s.status)),
                current: stepName(s.current_step),
                next: stepName(s.next_step),
                due: s.next_due_day === null ? '–' : String(s.next_due_day),
              })}
            </div>
            {Array.isArray(s.overdue_steps) && s.overdue_steps.length > 0 && (
              <div className="patient-overdue">{t('patient.overdue', { steps: s.overdue_steps.map(stepName).join(', ') })}</div>
            )}
            <div className="card-sub">
              {t('patient.risk', { risk: formatPercent(lang, Number(s.risk_score), 1) })}
              <Origin kind="code" />
            </div>
          </div>
        ))}
      </section>
      <section className="panel" aria-labelledby="h-timeline">
        <h2 id="h-timeline">{t('patient.timeline')}</h2>
        <div className="card-sub">
          {t('patient.since')} {t('event.TELEMON_READING.count', { count: readings })}
        </div>
        <ol className="timeline">
          {shown.map((i) =>
            i.kind === 'action' ? (
              <li key={i.action_id} className="timeline-item agent">
                <span className="timeline-day">{t('top.day', { day: i.day })}</span>
                <span>
                  <strong>{label(t, 'action', i.type)}</strong> · {i.rationale[lang]}
                </span>
                <span className="timeline-tag">{t('patient.agent')}</span>
              </li>
            ) : (
              <li key={i.event_id} className={i.source === 'agent_action' ? 'timeline-item agent' : 'timeline-item'}>
                <span className="timeline-day">{t('top.day', { day: i.day })}</span>
                <span>
                  <strong>{label(t, 'event', i.event_type)}</strong>
                  {eventDetail(i) && ` · ${eventDetail(i)}`}
                </span>
                {i.source === 'agent_action' && <span className="timeline-tag">{t('patient.agent')}</span>}
                {i.event_type === 'ADMISSION' && scenario !== null && (
                  <button
                    type="button"
                    className="timeline-link"
                    onClick={() => onAdmission({ run: `s${scenario}_${arm}`, patientId: p.patient_id, day: i.day })}
                  >
                    {t('patient.bed')}
                  </button>
                )}
              </li>
            ),
          )}
        </ol>
      </section>
    </div>
  )
}
