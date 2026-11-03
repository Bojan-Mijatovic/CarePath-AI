import { useState } from 'react'
import Origin from '../components/Origin'
import { type CapacityRow, type KpiRow, type Pathway, useApi } from '../lib/api'
import { formatEuro, formatNumber, formatPercent, useLang } from '../lib/i18n'
import type { LeverRun } from '../lib/stream'

type Mode = 'arms' | 'lever'

/** Demo step 6, below the autonomy panel (prototype "Poređenje"): the same simulation without and with the
 * agents on the day on screen, same seed and population. With a lever run (D45, C28) a second mode compares
 * the agents arm before and after the new slots; approving the capacity proposal turns the screen to it
 * (C34). The waits are those of the pathway's step with a wait threshold, per facility, over 7 days. */
export default function Compare({
  day,
  scenario,
  pathway,
  leverRun,
}: {
  day: number | null
  scenario: number | null
  pathway: Pathway | null
  leverRun: LeverRun | null
}) {
  const { lang, t } = useLang()
  const [mode, setMode] = useState<Mode>('arms')
  const approved = leverRun?.approved ?? false
  const [seenApproved, setSeenApproved] = useState(approved)
  if (approved !== seenApproved) {
    // the moment the manager approves, the screen turns to the lever run (React: state from the last render)
    setSeenApproved(approved)
    if (approved) setMode('lever')
  }
  const lever = mode === 'lever' ? leverRun : null
  const runs = scenario === null ? null : lever ? [`s${scenario}_agents`, lever.run_id] : [`s${scenario}_baseline`, `s${scenario}_agents`]
  const step = pathway?.steps.find((s) => s.service && s.max_wait_days !== undefined)
  // A lever run's id has a "+" (s2_agents_echo+1), which a query string reads as a space
  const kpiPath = (run: string | undefined) =>
    run && pathway ? `/api/kpi?run=${encodeURIComponent(run)}&level=ats&pathway_id=${pathway.pathway_id}` : null
  const capPath = (run: string | undefined) =>
    run && step ? `/api/capacity?service=${step.service}&run=${encodeURIComponent(run)}` : null
  const refresh = `${day}-${lever?.day ?? ''}`
  const kpiA = useApi<KpiRow[]>(kpiPath(runs?.[0]), refresh)
  const kpiB = useApi<KpiRow[]>(kpiPath(runs?.[1]), refresh)
  const capA = useApi<CapacityRow[]>(capPath(runs?.[0]), refresh)
  const capB = useApi<CapacityRow[]>(capPath(runs?.[1]), refresh)

  if (day === null || runs === null || pathway === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const error = kpiA.error ?? kpiB.error ?? capA.error ?? capB.error
  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  const a = kpiA.data?.at(-1)
  const b = kpiB.data?.at(-1)
  const n = (x: number) => formatNumber(lang, x)
  const signed = (x: number, digits = 0) => `${x > 0 ? '+' : '−'}${formatNumber(lang, Math.abs(x), digits)}`
  const slots = lever?.run_id.split('+').at(-1) ?? ''
  const titles = lever
    ? [t('compare.before'), t(slots === '1' ? 'compare.afterOne' : 'compare.after', { slots })]
    : [t('compare.without'), t('compare.with')]
  const readmissionsDelta = a && b ? b.readmissions_30d - a.readmissions_30d : 0
  const pointsDelta = a && b ? Math.round(100 * (b.on_track_pct - a.on_track_pct)) : 0
  const costDelta = (b?.est_readmission_cost_eur ?? 0) - (a?.est_readmission_cost_eur ?? 0)
  const cost = pathway.readmission_cost

  const column = (k: 0 | 1, row: KpiRow | undefined, cap: CapacityRow[] | undefined) => (
    <section className={k === 1 ? 'panel compare-col accent' : 'panel compare-col'} aria-labelledby={`h-compare-${k}`}>
      <h2 id={`h-compare-${k}`}>{titles[k]}</h2>
      {row === undefined ? (
        <p className="placeholder">{t('loading')}</p>
      ) : (
        <>
          <div className="card-sub">{t('compare.day', { day: row.day })}</div>
          <dl className="compare-figures">
            <dt>{t('compare.readmissions')}</dt>
            <dd>
              {n(row.readmissions_30d)}
              {k === 1 && readmissionsDelta !== 0 && <span className="compare-delta">{signed(readmissionsDelta)}</span>}
            </dd>
            <dt>{t('compare.onTrack')}</dt>
            <dd>
              {formatPercent(lang, row.on_track_pct, 0)}
              {k === 1 && pointsDelta !== 0 && (
                <span className="compare-delta">{t('compare.points', { points: signed(pointsDelta) })}</span>
              )}
            </dd>
            <dt>{t('compare.overdue')}</dt>
            <dd>{n(row.overdue)}</dd>
            {row.est_readmission_cost_eur !== null && (
              <>
                <dt>{t('compare.cost')}</dt>
                <dd>
                  {formatEuro(lang, row.est_readmission_cost_eur)}
                  {k === 1 && costDelta !== 0 && (
                    <span className="compare-delta">{`${costDelta > 0 ? '+' : '−'}${formatEuro(lang, Math.abs(costDelta))}`}</span>
                  )}
                </dd>
              </>
            )}
          </dl>
          {step && (
            <table className="compare-table">
              <caption>{t('compare.waits', { step: step.label[lang] })}</caption>
              <thead>
                <tr>
                  <th scope="col">{t('compare.facility')}</th>
                  <th scope="col">{t('compare.wait')}</th>
                  <th scope="col">{t('compare.use')}</th>
                </tr>
              </thead>
              <tbody>
                {(cap ?? []).map((c) => (
                  <tr key={c.facility_id} className={c.wait_mean !== null && c.wait_mean > (step.max_wait_days ?? Infinity) ? 'over' : ''}>
                    <th scope="row">{c.name}</th>
                    <td>{c.wait_mean === null ? '–' : t('compare.days', { days: formatNumber(lang, c.wait_mean, 1) })}</td>
                    <td>{c.use_pct === null ? '–' : formatPercent(lang, c.use_pct, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </section>
  )

  return (
    <div className="compare">
      <div className="compare-head">
        <p className="lead">
          {lever ? t('compare.leadLever') : t('compare.lead')}
          <Origin kind="code" />
        </p>
        {leverRun && (
          <div className="lang" role="group" aria-label={t('compare.mode')}>
            <button type="button" aria-pressed={mode === 'arms'} onClick={() => setMode('arms')}>
              {t('compare.modeArms')}
            </button>
            <button
              type="button"
              aria-pressed={mode === 'lever'}
              data-spot={mode === 'lever' ? undefined : 'compare-lever'}
              onClick={() => setMode('lever')}
            >
              {t('compare.modeLever')}
            </button>
          </div>
        )}
      </div>
      {lever && lever.day < day && <p className="card-sub">{t('compare.catchingUp', { day: lever.day })}</p>}
      <div className="compare-cols">
        {column(0, a, capA.data)}
        {column(1, b, capB.data)}
      </div>
      {cost && <p className="card-sub">{t('cost.note', { eur: formatEuro(lang, cost.eur), source: cost.label[lang] })}</p>}
    </div>
  )
}
