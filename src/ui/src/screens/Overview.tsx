import { type Action, type Kpi, useApi } from '../lib/api'
import { agentName, formatNumber, formatPercent, label, PNE_ITALY, useLang } from '../lib/i18n'

/** Demo step 3 (prototype "Pregled"): headline numbers of the day, the approval queue, the PNE indicator. */
export default function Overview({ day, kpi }: { day: number | null; kpi: Kpi | null }) {
  const { lang, t } = useLang()
  const { data: proposed } = useApi<Action[]>('/api/actions?status=proposed')
  if (day === null || kpi === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const queue = (proposed ?? []).filter((a) => a.created_day <= day)
  const n = (x: number) => formatNumber(lang, x)

  return (
    <div className="overview">
      <p className="lead">{t('overview.intro', { days: day, patients: n(kpi.patients) })}</p>
      <div className="cards">
        <div className="card">
          <div className="card-label">{t('card.patients')}</div>
          <div className="card-value">{n(kpi.patients)}</div>
          <div className="card-sub">{t('card.patientsSub')}</div>
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
          {queue.map((a) => (
            <div key={a.action_id} className="approval">
              <div className="approval-text">
                <div className="approval-title">{label(t, 'action', a.type)}</div>
                <div className="approval-meta">
                  {t('approvals.meta', { agent: agentName(a.agent), level: a.autonomy_level, day: a.created_day })}
                </div>
                <p className="approval-rationale">{a.rationale[lang]}</p>
              </div>
              {/* Decisions are step 2.18 (POST /api/actions/{id}/approve and /reject). */}
              <button type="button" className="primary" disabled title={t('approvals.later')}>
                {t('approvals.approve')}
              </button>
              <button type="button" disabled title={t('approvals.later')}>
                {t('approvals.reject')}
              </button>
            </div>
          ))}
        </section>
        <section className="panel" aria-labelledby="h-pne">
          <h2 id="h-pne">{t('pne.title')}</h2>
          <div className="card-sub">{t('pne.sub')}</div>
          <div className="pne">
            <span className="card-value">
              {kpi.readmission_rate_30d === null ? '–' : formatPercent(lang, kpi.readmission_rate_30d)}
            </span>
            <span className="card-sub">{t('pne.count', { count: n(kpi.readmissions_30d) })}</span>
          </div>
          <div className="card-sub">{t('pne.reference', { rate: formatPercent(lang, PNE_ITALY, 2) })}</div>
        </section>
      </div>
    </div>
  )
}
