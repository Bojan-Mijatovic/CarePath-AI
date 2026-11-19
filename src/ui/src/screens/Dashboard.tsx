import { useState } from 'react'
import Origin from '../components/Origin'
import { type Action, type CapacityRow, type Kpi, type KpiRow, type MapRow, type Pathway, useApi } from '../lib/api'
import { patientsOf } from '../lib/evidence'
import { useGeo } from '../lib/geo'
import { formatEuro, formatNumber, formatPercent, type Key, label, useLang } from '../lib/i18n'
import type { LeverRun } from '../lib/stream'
import MapPanel, { type Site } from './MapScreen'

/** The wait alarm of the situation on screen: from the stream, or after a reload from its investigation. */
export type Alarm = { day: number; facility_id: string | null; text: string }

const ATTENTION = 5 // comuni listed under "need attention"
const TYPE_ORDER = ['reminder', 'call_task', 'notify_mmg', 'reschedule', 'capacity_proposal']

/** The Dashboard of the console mockup (D67, proposed): the day's numbers with and without CarePath, the map with
 * its hospitals, the alarms and events, the comuni that need attention, the share on their care plan day by day
 * and what the agents did today. Every number comes from the API (kpi_daily, map, capacity, actions); the page
 * only subtracts and counts. */
export default function Dashboard({
  day,
  past,
  scenario,
  kpi,
  pathway,
  alarm,
  leverRun,
  onAlarm,
  onAgents,
}: {
  /** today of the situation on screen */
  day: number | null
  /** a past day looked back at, or null */
  past: number | null
  scenario: number | null
  /** the agents arm's numbers of the day shown */
  kpi: Kpi | null
  pathway: Pathway | null
  alarm: Alarm | null
  leverRun: LeverRun | null
  onAlarm: () => void
  onAgents: () => void
}) {
  const { lang, t } = useLang()
  const { geo } = useGeo()
  const [arm, setArm] = useState<'with' | 'without'>('with')
  const [selected, setSelected] = useState<string | null>(null)
  const shown = past ?? day
  const pathwayId = pathway?.pathway_id ?? null
  const baseline = scenario === null ? null : `s${scenario}_baseline`
  const kpiPath = (run: string | null) =>
    pathwayId ? `/api/kpi?level=ats&pathway_id=${pathwayId}${run ? `&run=${run}` : ''}` : null
  const { data: withRows } = useApi<KpiRow[]>(kpiPath(null), `${scenario}-${day}`)
  const { data: withoutRows } = useApi<KpiRow[]>(baseline ? kpiPath(baseline) : null, `${scenario}-${day}`)
  const mapRun = arm === 'without' && baseline ? `&run=${baseline}` : ''
  const { data: mapRows } = useApi<MapRow[]>(pathwayId ? `/api/map?pathway_id=${pathwayId}${mapRun}` : null, `${scenario}-${day}`)
  const { data: actions } = useApi<Action[]>(shown !== null ? `/api/actions?day=${shown}` : null, `${scenario}-${day}`)
  const step = pathway?.steps.find((s) => s.service && s.max_wait_days !== undefined) ?? null
  const { data: capacity } = useApi<CapacityRow[]>(step ? `/api/capacity?service=${step.service}` : null, `${scenario}-${day}`)
  const bought = leverRun?.approved ? leverRun.run_id : null
  const { data: withPurchase } = useApi<CapacityRow[]>(
    step && bought ? `/api/capacity?service=${step.service}&run=${encodeURIComponent(bought)}` : null,
    `${day}-${leverRun?.day ?? ''}`,
  )

  if (shown === null || kpi === null || pathway === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const n = (x: number) => formatNumber(lang, x)
  const without = withoutRows?.find((r) => r.day === shown) ?? null
  const cost = pathway.readmission_cost ?? null
  const avoided =
    without && without.est_readmission_cost_eur !== null && kpi.est_readmission_cost_eur !== null
      ? without.est_readmission_cost_eur - kpi.est_readmission_cost_eur
      : null

  // Hospitals: an alarm, a closure (0 slots over 7 days) or new equipment (more slots in the approved lever run)
  const more = new Map((withPurchase ?? []).map((r) => [r.facility_id, r.slots_total ?? 0]))
  const sites: Site[] = (capacity ?? []).map((r) => ({
    facility_id: r.facility_id,
    name: r.name,
    lat: r.lat,
    lon: r.lon,
    state:
      alarm && alarm.facility_id === r.facility_id
        ? 'alarm'
        : r.slots_total === 0
          ? 'closed'
          : (more.get(r.facility_id) ?? 0) > (r.slots_total ?? 0)
            ? 'new'
            : 'open',
  }))
  const stepName = step?.label[lang] ?? ''
  const events = [
    ...sites.filter((s) => s.state === 'closed').map((s) => ({ kind: 'event', text: t('events.closed', { facility: s.name, step: stepName }) })),
    ...sites.filter((s) => s.state === 'new').map((s) => ({ kind: 'decision', text: t('events.new', { facility: s.name, step: stepName }) })),
  ]

  // Comuni that need attention: the lowest share on their care plan among those with enough patients
  const comuni = new Map((geo?.comuni ?? []).map((c) => [c.istat, c]))
  const low = (mapRows ?? [])
    .filter((r) => r.adherence_pct !== null)
    .sort((a, b) => (a.adherence_pct ?? 0) - (b.adherence_pct ?? 0))
    .slice(0, ATTENTION)
  const chosen = low.find((r) => r.comune_istat === selected) ?? null

  // What the agents did today, by type: actions and patients reached
  const byType = new Map<string, { actions: number; patients: number; waiting: number }>()
  for (const a of actions ?? []) {
    const g = byType.get(a.type) ?? { actions: 0, patients: 0, waiting: 0 }
    g.actions += 1
    g.patients += Math.max(patientsOf(a).length, 1)
    g.waiting += a.status === 'proposed' ? 1 : 0
    byType.set(a.type, g)
  }
  const groups = [...byType.entries()].sort(
    ([a], [b]) => (TYPE_ORDER.indexOf(a) + 99) % 99 - (TYPE_ORDER.indexOf(b) + 99) % 99,
  )

  return (
    <>
      {past !== null && <p className="placeholder">{t('lookback.mapToday')}</p>}
      <div className="tiles-row">
        <Tile label={t('card.patients')} value={n(kpi.patients)} sub={pathway.label[lang]} />
        <Tile
          label={t('card.onTrack')}
          value={formatPercent(lang, kpi.on_track_pct, 0)}
          sub={without ? t('tile.onTrackSub', { pct: formatPercent(lang, without.on_track_pct, 0) }) : ''}
          tone="primary"
        />
        <Tile
          label={t('tile.readmissions')}
          value={n(kpi.readmissions_30d)}
          sub={without ? t('tile.readmissionsSub', { n: n(without.readmissions_30d) }) : ''}
          tone="primary"
        />
        {cost && avoided !== null && (
          <Tile
            label={t('tile.saving')}
            value={formatEuro(lang, Math.max(avoided, 0))}
            sub={t('tile.savingSub', { eur: formatEuro(lang, cost.eur) })}
            tone="ok"
          />
        )}
        <Tile label={t('tile.today')} value={n((actions ?? []).length)} sub={t('tile.todaySub', { n: n(kpi.actions_pending) })} />
      </div>

      <div className="row">
        <div className="col-3">
          <MapPanel rows={mapRows} arm={arm} setArm={setArm} sites={sites} selected={selected} />
        </div>
        <div className="col-2">
          <section className="panel" aria-labelledby="h-events">
            <h2 id="h-events">{t('events.title')}</h2>
            {events.map((e, k) => (
              <div key={k} className={`event event-${e.kind}`}>
                <span className="chip">{t(`events.kind.${e.kind}` as Key)}</span>
                <span>{e.text}</span>
              </div>
            ))}
            {alarm ? (
              <div className="alarm-box">
                <strong>{t('events.alarmTitle', { day: alarm.day })}</strong>
                <span>{alarm.text}</span>
                <button type="button" onClick={onAlarm}>
                  {t('events.open')}
                </button>
              </div>
            ) : (
              events.length === 0 && <p className="placeholder">{t(scenario === 0 ? 'events.none' : 'events.notYet')}</p>
            )}
          </section>
          <section className="panel" aria-labelledby="h-attention">
            <h2 id="h-attention">{t('attention.title')}</h2>
            <div className="attention">
              {low.map((r) => {
                const c = comuni.get(r.comune_istat)
                return (
                  <button
                    key={r.comune_istat}
                    type="button"
                    aria-pressed={selected === r.comune_istat}
                    onClick={() => setSelected(selected === r.comune_istat ? null : r.comune_istat)}
                  >
                    <span className="attention-name">{c?.name ?? r.comune_istat}</span>
                    <span className="attention-asst">{c ? label(t, 'asst', c.asst) : ''}</span>
                    <strong className={`attention-pct band-text-${r.adherence_pct !== null && r.adherence_pct < 0.7 ? 'low' : 'ok'}`}>
                      {formatPercent(lang, r.adherence_pct ?? 0, 0)}
                    </strong>
                  </button>
                )
              })}
            </div>
            {chosen && (
              <div className="attention-info">
                <strong>{comuni.get(chosen.comune_istat)?.name ?? chosen.comune_istat}</strong>
                <span>
                  {t('attention.line1', {
                    pct: formatPercent(lang, chosen.adherence_pct ?? 0, 0),
                    n: n(chosen.high_risk_patients ?? 0),
                  })}
                </span>
                {chosen.readmission_rate_30d !== null && (
                  <span>{t('attention.line2', { pct: formatPercent(lang, chosen.readmission_rate_30d) })}</span>
                )}
              </div>
            )}
          </section>
        </div>
      </div>

      <div className="row">
        <div className="col-3">
          <Trend withRows={withRows} withoutRows={withoutRows} today={day ?? shown} shown={shown} alarmDay={alarm?.day ?? null} />
        </div>
        <div className="col-2">
          <section className="panel" aria-labelledby="h-today">
            <div className="panel-head">
              <h2 id="h-today">{t('today.title')}</h2>
              <button type="button" className="link" onClick={onAgents}>
                {t('today.all')}
              </button>
            </div>
            {groups.length === 0 && <p className="placeholder">{t('today.none')}</p>}
            {groups.map(([type, g]) => (
              <div key={type} className="today-row">
                <span className={`chip type-${type}`}>{label(t, 'action', type)}</span>
                <span>
                  {t('today.line', { n: n(g.patients) })}
                  {g.waiting > 0 && ` · ${t('today.waiting', { n: n(g.waiting) })}`}
                </span>
              </div>
            ))}
          </section>
        </div>
      </div>
    </>
  )
}

function Tile({ label: name, value, sub, tone }: { label: string; value: string; sub: string; tone?: 'primary' | 'ok' }) {
  return (
    <div className={`tile-card${tone ? ` ${tone}` : ''}`}>
      <span className="tile-label">{name}</span>
      <span className="tile-value">{value}</span>
      <span className="tile-sub">{sub}</span>
      <Origin kind="code" />
    </div>
  )
}

const W = 600
const H = 190
const X0 = 40
const TOP = 20
const BOTTOM = 170
const LOW = 0.6
const HIGH = 0.9

/** The share on their care plan, day by day, with and without CarePath (kpi_daily of both arms). */
function Trend({
  withRows,
  withoutRows,
  today,
  shown,
  alarmDay,
}: {
  withRows: KpiRow[] | undefined
  withoutRows: KpiRow[] | undefined
  today: number
  shown: number
  alarmDay: number | null
}) {
  const { lang, t } = useLang()
  const last = Math.max(120, today)
  const x = (d: number) => X0 + ((W - X0) * d) / last
  const y = (v: number) => BOTTOM - ((BOTTOM - TOP) * (Math.min(Math.max(v, LOW), HIGH) - LOW)) / (HIGH - LOW)
  const line = (rows: KpiRow[] | undefined) =>
    (rows ?? [])
      .filter((r) => r.day <= today)
      .map((r) => `${x(r.day).toFixed(1)},${y(r.on_track_pct).toFixed(1)}`)
      .join(' ')
  const ticks = [0.9, 0.8, 0.7, 0.6]
  return (
    <section className="panel" aria-labelledby="h-trend">
      <div className="panel-head trend-head">
        <h2 id="h-trend">{t('trend.title')}</h2>
        <span className="trend-with">{t('trend.with')}</span>
        <span className="trend-without">{t('trend.without')}</span>
        <Origin kind="code" />
      </div>
      <svg className="trend" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={t('trend.label', { day: today })}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={X0} y1={y(v)} x2={W} y2={y(v)} className={v === LOW ? 'axis' : 'grid'} />
            <text x={X0 - 6} y={y(v) + 4} textAnchor="end">
              {formatPercent(lang, v, 0)}
            </text>
          </g>
        ))}
        {alarmDay !== null && (
          <g className="trend-alarm">
            <line x1={x(alarmDay)} y1={TOP - 6} x2={x(alarmDay)} y2={BOTTOM} />
            <text x={x(alarmDay)} y={TOP - 9} textAnchor="middle">
              {t('trend.alarm')}
            </text>
          </g>
        )}
        <line className="trend-today" x1={x(shown)} y1={TOP} x2={x(shown)} y2={BOTTOM} />
        <polyline className="trend-line-without" points={line(withoutRows)} />
        <polyline className="trend-line-with" points={line(withRows)} />
        <text x={X0} y={H - 4}>
          {t('trend.day', { day: 0 })}
        </text>
        <text x={W} y={H - 4} textAnchor="end">
          {t('trend.day', { day: last })}
        </text>
      </svg>
    </section>
  )
}
