import type { ReactNode } from 'react'
import Origin from '../components/Origin'
import { type Pathway, type Situations as Result, useApi } from '../lib/api'
import { formatEuro, formatNumber, formatPercent, type Key, label, useLang } from '../lib/i18n'

/** The last panel of Analisi (D67, proposed; C43): the three situations side by side on the latest day all their
 * runs reached, with and without CarePath, and how the system responded: the wait alarms and the manager's
 * decisions. Every number is the API's; the saving is the difference of two estimated costs. */
export default function Situations({ day, leverDay, pathway }: { day: number | null; leverDay: number | null; pathway: Pathway | null }) {
  const { lang, t } = useLang()
  // A lever run catches up while the clock is paused (C28), which moves the common day without a new day on screen
  const { data, error } = useApi<Result>(day === null ? null : '/api/situations', `${day}-${leverDay}`)
  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  if (!data || !pathway) return <p className="placeholder">{t('loading')}</p>
  const n = (x: number) => formatNumber(lang, x)
  const pct = (x: number) => formatPercent(lang, x, 1)
  const days = (x: number | null) => (x === null ? '–' : t('hospitals.days', { n: formatNumber(lang, x, 1) }))
  const step = (id: string) => pathway.steps.find((s) => s.id === id)?.label[lang] ?? id
  const cols = data.situations
  const row = (title: string, cell: (s: Result['situations'][number]) => ReactNode) => (
    <tr>
      <th scope="row">{title}</th>
      {cols.map((s) => (
        <td key={s.scenario}>{cell(s)}</td>
      ))}
    </tr>
  )
  return (
    <section className="panel situations" aria-labelledby="h-situations" data-spot="situations">
      <h2 id="h-situations">
        {t('situations.title', { day: data.day })}
        <Origin kind="code" />
      </h2>
      <div className="card-sub">{t('situations.sub')}</div>
      <div className="table-wrap">
        <table className="compare-table situations-table">
          <thead>
            <tr>
              <th scope="col" />
              {cols.map((s) => (
                <th key={s.scenario} scope="col">
                  {t(`situation.${s.scenario}` as Key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {row(t('situations.onScreen'), (s) => t('top.day', { day: s.day_on_screen }))}
            {row(t('situations.onTrack'), (s) => (
              <>
                <strong>{pct(s.with.on_track_pct)}</strong>
                <div className="card-sub">{t('situations.without', { value: pct(s.without.on_track_pct) })}</div>
              </>
            ))}
            {row(t('situations.readmissions'), (s) => (
              <>
                <strong>{n(s.with.readmissions_30d)}</strong>
                <div className="card-sub">{t('situations.without', { value: n(s.without.readmissions_30d) })}</div>
              </>
            ))}
            {row(t('situations.saving'), (s) =>
              s.with.est_readmission_cost_eur === null || s.without.est_readmission_cost_eur === null
                ? '–'
                : formatEuro(lang, s.without.est_readmission_cost_eur - s.with.est_readmission_cost_eur),
            )}
            {row(t('situations.wait'), (s) =>
              s.waits.length === 0
                ? '–'
                : s.waits.map((w, i) => (
                    <div key={i}>
                      <strong>{days(w.with)}</strong>
                      <div className="card-sub">{t('situations.without', { value: days(w.without) })}</div>
                      <div className="card-sub">{t('situations.waitOf', { step: step(w.step), day: w.from_day })}</div>
                    </div>
                  )),
            )}
            {row(t('situations.actions'), (s) => n(s.with.actions_executed))}
            {row(t('situations.alarms'), (s) =>
              s.alarms.length === 0
                ? t('situations.none')
                : s.alarms.map((a, i) => (
                    <div key={i}>
                      {t('situations.alarm', { facility: a.facility, step: step(a.step), day: a.day })}{' '}
                      {s.with_purchase
                        ? t('situations.purchase')
                        : a.closed_day === null
                          ? t('situations.open')
                          : t('situations.closed', { day: a.closed_day })}
                    </div>
                  )),
            )}
            {row(t('situations.decisions'), (s) =>
              s.decisions.length === 0
                ? t('situations.none')
                : s.decisions.map((d, i) => (
                    <div key={i}>
                      {t('situations.decision', {
                        day: d.day,
                        type: label(t, 'action', d.type),
                        decision: t(`situations.${d.decision}` as Key),
                      })}
                      {d.patients > 0 && ` · ${t('situations.patients', { n: n(d.patients) })}`}
                    </div>
                  )),
            )}
          </tbody>
        </table>
      </div>
      {pathway.readmission_cost && (
        <div className="card-sub">
          {t('cost.note', { eur: formatEuro(lang, pathway.readmission_cost.eur), source: pathway.readmission_cost.label[lang] })}
        </div>
      )}
    </section>
  )
}
