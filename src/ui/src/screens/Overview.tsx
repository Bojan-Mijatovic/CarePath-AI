import { useState } from 'react'
import { type Action, type Kpi, type Pathway, type Report, send, useApi } from '../lib/api'
import { agentName, formatNumber, formatPercent, label, useLang } from '../lib/i18n'

/** Demo step 3 (prototype "Pregled"): headline numbers of the day, the approval queue, the PNE indicator, and
 * the Reporter's latest monthly report (step 2.14). */
export default function Overview({ day, kpi, pathway }: { day: number | null; kpi: Kpi | null; pathway: Pathway | null }) {
  const { lang, t } = useLang()
  const [decisions, setDecisions] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { data: proposed } = useApi<Action[]>('/api/actions?status=proposed', `${day}-${decisions}`)
  const { data: reports } = useApi<Report[]>('/api/reports', day) // the Reporter's monthly reports (C36)
  if (day === null || kpi === null || pathway === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const report = (reports ?? []).find((r) => r.day <= day)
  const reference = pathway.readmission_reference
  const queue = (proposed ?? []).filter((a) => a.created_day <= day)
  const n = (x: number) => formatNumber(lang, x)
  // The manager's decision goes to the action service, which writes it to the audit log (step 2.18).
  const decide = (id: string, decision: 'approve' | 'reject') => {
    setBusy(id)
    setError(null)
    send('POST', `/api/actions/${id}/${decision}`)
      .then(() => setDecisions((k) => k + 1))
      .catch(() => setError(t('approvals.failed')))
      .finally(() => setBusy(null))
  }

  return (
    <div className="overview">
      <p className="lead">{t('overview.intro', { days: day, patients: n(kpi.patients) })}</p>
      <div className="cards">
        <div className="card">
          <div className="card-label">{t('card.patients')}</div>
          <div className="card-value">{n(kpi.patients)}</div>
          <div className="card-sub">{t('card.patientsSub', { pathway: pathway.label[lang] })}</div>
        </div>
        <div className="card">
          <div className="card-label">{t('card.onTrack')}</div>
          <div className="card-value">{formatPercent(lang, kpi.on_track_pct, 0)}</div>
          <div className="card-sub">{t('card.onTrackSub', { overdue: n(kpi.overdue), dropped: n(kpi.dropped) })}</div>
        </div>
        <div className="card">
          <div className="card-label">{t('card.actions')}</div>
          <div className="card-value">{n(kpi.actions_executed)}</div>
          <div className="card-sub">{t('card.actionsSub')}</div>
        </div>
        <div className="card accent">
          <div className="card-label">{t('card.pending')}</div>
          <div className="card-value">{n(kpi.actions_pending)}</div>
          <div className="card-sub">{t('card.pendingSub')}</div>
        </div>
      </div>
      <div className="panels">
        <section className="panel wide" aria-labelledby="h-approvals">
          <h2 id="h-approvals">{t('approvals.title')}</h2>
          {queue.length === 0 && <p className="placeholder">{t('approvals.empty')}</p>}
          {error && <p className="placeholder">{error}</p>}
          {queue.map((a) => (
            <div key={a.action_id} className="approval">
              <div className="approval-text">
                <div className="approval-title">{label(t, 'action', a.type)}</div>
                <div className="approval-meta">
                  {t('approvals.meta', { agent: agentName(a.agent), level: a.autonomy_level, day: a.created_day })}
                </div>
                <p className="approval-rationale">{a.rationale[lang]}</p>
              </div>
              <button
                type="button"
                className="primary"
                disabled={busy !== null}
                onClick={() => decide(a.action_id, 'approve')}
              >
                {t('approvals.approve')}
              </button>
              <button type="button" disabled={busy !== null} onClick={() => decide(a.action_id, 'reject')}>
                {t('approvals.reject')}
              </button>
            </div>
          ))}
        </section>
        <section className="panel" aria-labelledby="h-pne">
          <h2 id="h-pne">{t('pne.title')}</h2>
          <div className="card-sub">{t('pne.sub', { pathway: pathway.label[lang] })}</div>
          <div className="pne">
            <span className="card-value">
              {kpi.readmission_rate_30d === null ? '–' : formatPercent(lang, kpi.readmission_rate_30d)}
            </span>
            <span className="card-sub">{t('pne.count', { count: n(kpi.readmissions_30d) })}</span>
          </div>
          {reference && (
            <div className="card-sub">
              {t('pne.reference', { source: reference.label[lang], rate: formatPercent(lang, reference.rate, 2) })}
            </div>
          )}
        </section>
        {report && (
          <section className="panel wide" aria-labelledby="h-report">
            <h2 id="h-report">{t('report.title', { month: report.month })}</h2>
            <div className="card-sub">
              {t('report.sub', { from: report.from_day, to: report.day })}
            </div>
            <div className="report-text">
              {report.text[lang].split('\n').map((line, i) => (
                <p key={i}>{line}</p>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
