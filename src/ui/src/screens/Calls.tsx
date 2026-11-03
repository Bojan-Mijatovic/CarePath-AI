import { useState } from 'react'
import Origin from '../components/Origin'
import { useApi, type WorklistRow } from '../lib/api'
import { formatPercent, label, useLang } from '../lib/i18n'

const SHOWN = 20 // the Centro Servizi calls from the top (C20, C32)

/** Demo step 9a (prototype "Lista poziva"): the list the agents prepare each morning for the Centro Servizi, on
 * the day on screen or an earlier one (worklist_today keeps every day, SPEC §5.2): one call per patient, by
 * risk, with every reason, the rung of the escalation ladder and the call's outcome. Patients have no names
 * in the synthetic data, so they are shown by id, age and comune. */
export default function Calls({ day }: { day: number | null }) {
  const { lang, t } = useLang()
  const [chosen, setChosen] = useState<number | null>(null) // null follows the day on screen
  const [draft, setDraft] = useState('')
  const shown = chosen ?? day
  const { data, error } = useApi<WorklistRow[]>(shown === null ? null : `/api/worklist?day=${shown}`, day)

  if (day === null) return <p className="placeholder">{t('overview.waiting')}</p>
  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  const rows = (data ?? []).slice(0, SHOWN)
  const go = () => {
    const d = Number(draft)
    if (Number.isInteger(d) && d >= 0 && d <= day) setChosen(d)
  }

  return (
    <div className="calls">
      <p className="lead">
        {t('calls.lead')}
        <Origin kind="code" />
      </p>
      <div className="calls-day">
        <label htmlFor="calls-day">{t('calls.day')}</label>
        <input
          id="calls-day"
          type="number"
          min={0}
          max={day}
          value={draft}
          placeholder={String(shown)}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && go()}
        />
        <button type="button" onClick={go}>
          {t('bar.go')}
        </button>
        <button type="button" onClick={() => setChosen(null)} aria-pressed={chosen === null}>
          {t('calls.today')}
        </button>
      </div>
      <section className="panel" aria-labelledby="h-calls">
        <h2 id="h-calls">{t('calls.count', { day: shown ?? day, n: rows.length, total: data?.length ?? 0 })}</h2>
        {data && rows.length === 0 && <p className="placeholder">{t('calls.empty')}</p>}
        {rows.length > 0 && (
          <table className="calls-table">
            <thead>
              <tr>
                <th scope="col">{t('calls.rank')}</th>
                <th scope="col">{t('calls.patient')}</th>
                <th scope="col">{t('calls.risk')}</th>
                <th scope="col">{t('calls.reasons')}</th>
                <th scope="col">{t('calls.step')}</th>
                <th scope="col">{t('calls.outcome')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.patient_id}>
                  <td>{r.rank}</td>
                  <td>
                    <strong>{r.patient_id}</strong>
                    <div className="card-sub">
                      {t('calls.who', { age: r.age, comune: r.comune_name })}
                      {r.lives_alone && ` · ${t('calls.alone')}`}
                    </div>
                  </td>
                  <td>{formatPercent(lang, r.risk_score, 0)}</td>
                  <td className="calls-reasons">{r.reasons[lang]}</td>
                  <td>{label(t, 'escalation', String(r.escalation_step))}</td>
                  <td>{r.outcome ? label(t, 'outcome', r.outcome) : '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
