import { useCallback, useEffect, useState } from 'react'
import { type Pathway, type WhatIf as Result, type WhatIfRun, send } from '../lib/api'
import { formatNumber, formatPercent, useLang } from '../lib/i18n'

const MAX_EXTRA_SLOTS = 4 // the grid's levers, SPEC §10 (C27)
const MONTHS = 6

/** Demo step 7 (prototype "Šta ako"): one lever, extra slots a day at the facility of the first wait alarm,
 * and 6 months with and without the agents, same seed. The runs were computed in advance (C27, D48); the
 * screen reads them for the scenario on screen and says so. The prototype's second lever (a step deadline) and
 * the PNE forecast to year end are not in the grid (step 2.6). */
export default function WhatIf({ scenario, pathway }: { scenario: number | null; pathway: Pathway | null }) {
  const { lang, t } = useLang()
  const [extra, setExtra] = useState(1)
  const [result, setResult] = useState<Result | null>(null)
  const [ms, setMs] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchResult = useCallback((slots: number) => {
    const started = performance.now()
    return send<Result>('POST', '/api/whatif', { levers: { extra_slots: slots }, months: MONTHS })
      .then((r) => {
        setResult(r)
        setMs(performance.now() - started)
        setError(null)
      })
      .catch((e: unknown) => setError(String(e)))
  }, [])
  useEffect(() => {
    if (scenario !== null) void fetchResult(1) // the scenario's facility and lever day, for the slider's label
  }, [scenario, fetchResult])
  const run = (slots: number) => {
    setBusy(true)
    void fetchResult(slots).finally(() => setBusy(false))
  }

  if (scenario === null || pathway === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const step = result ? pathway.steps.find((s) => s.service === result.service) : undefined
  const n = (x: number) => formatNumber(lang, x)
  const wait = (r: WhatIfRun) => (r.wait_days === null ? '–' : t('compare.days', { days: formatNumber(lang, r.wait_days, 1) }))
  const columns: [string, WhatIfRun][] = result
    ? [
        [t('compare.without'), result.baseline],
        [t('compare.with'), result.agents],
        [
          result.levers.extra_slots === 1 ? t('whatif.withLeverOne') : t('whatif.withLever', { slots: result.levers.extra_slots }),
          result.lever,
        ],
      ]
    : []

  return (
    <div className="whatif">
      <section className="panel" aria-labelledby="h-whatif">
        <h2 id="h-whatif">{t('whatif.title')}</h2>
        <p className="lead">{t('whatif.lead', { months: MONTHS })}</p>
        <div className="whatif-lever">
          <label htmlFor="extra-slots">
            {result && step
              ? t('whatif.lever', { step: step.label[lang], facility: result.facility, day: result.lever_day })
              : t('whatif.leverPlain')}
          </label>
          <input
            id="extra-slots"
            type="range"
            min={0}
            max={MAX_EXTRA_SLOTS}
            step={1}
            value={extra}
            onChange={(e) => setExtra(Number(e.target.value))}
          />
          <output htmlFor="extra-slots">+{extra}</output>
          <button type="button" className="primary" disabled={busy} onClick={() => run(extra)}>
            {t('whatif.run', { months: MONTHS })}
          </button>
        </div>
        {error && <p className="placeholder">{t('error.load', { detail: error })}</p>}
      </section>
      {result && (
        <>
          <div className="cards">
            <div className="card accent">
              <div className="card-label">{t('whatif.avoided', { months: MONTHS })}</div>
              <div className="card-value">{n(result.avoided_readmissions)}</div>
              <div className="card-sub">{t('whatif.avoidedSub')}</div>
            </div>
            <div className="card">
              <div className="card-label">{t('whatif.wait', { facility: result.facility })}</div>
              <div className="card-value">{wait(result.lever)}</div>
              <div className="card-sub">{t('whatif.waitSub', { without: wait(result.agents) })}</div>
            </div>
            <div className="card">
              <div className="card-label">{t('whatif.time')}</div>
              <div className="card-value">{ms === null ? '–' : t('whatif.ms', { ms: n(Math.round(ms)) })}</div>
              <div className="card-sub">{t('whatif.precomputed')}</div>
            </div>
          </div>
          <section className="panel" aria-labelledby="h-whatif-table">
            <h2 id="h-whatif-table">{t('whatif.table', { from: result.lever_day, to: result.last_day })}</h2>
            <table className="compare-table">
              <thead>
                <tr>
                  <th scope="col" />
                  {columns.map(([title]) => (
                    <th key={title} scope="col">
                      {title}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">{t('compare.readmissions')}</th>
                  {columns.map(([title, r]) => (
                    <td key={title}>{n(r.readmissions)}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">{t('compare.onTrack')}</th>
                  {columns.map(([title, r]) => (
                    <td key={title}>{formatPercent(lang, r.on_track_pct, 0)}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">{t('compare.overdue')}</th>
                  {columns.map(([title, r]) => (
                    <td key={title}>{n(r.overdue)}</td>
                  ))}
                </tr>
                <tr>
                  <th scope="row">{t('whatif.wait', { facility: result.facility })}</th>
                  {columns.map(([title, r]) => (
                    <td key={title}>{wait(r)}</td>
                  ))}
                </tr>
              </tbody>
            </table>
            <p className="card-sub">{t('whatif.note')}</p>
          </section>
        </>
      )}
    </div>
  )
}
