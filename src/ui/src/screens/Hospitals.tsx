import Origin from '../components/Origin'
import { type CapacityRow, type Pathway, useApi } from '../lib/api'
import { formatNumber, formatPercent, useLang } from '../lib/i18n'

type Step = Pathway['steps'][number]

/** The Hospitals page of D67 (proposed): for every pathway step booked at a facility, each facility's slot use
 * and mean wait over the last 7 days, with CarePath (agents arm) and without (baseline arm), from GET
 * /api/capacity (C28). The steps and their thresholds come from the pathway file (AC17). */
export default function Hospitals({ day, scenario, pathway }: { day: number | null; scenario: number | null; pathway: Pathway | null }) {
  const { t } = useLang()
  if (day === null || scenario === null || pathway === null) return <p className="placeholder">{t('overview.waiting')}</p>
  const steps = pathway.steps.filter((s) => s.service)
  return (
    <div className="panels">
      {steps.map((s) => (
        <ServiceTable key={s.id} step={s} day={day} scenario={scenario} />
      ))}
    </div>
  )
}

function ServiceTable({ step, day, scenario }: { step: Step; day: number; scenario: number }) {
  const { lang, t } = useLang()
  const path = (arm: string) => `/api/capacity?service=${step.service}&run=s${scenario}_${arm}&day=${day}`
  const withCp = useApi<CapacityRow[]>(path('agents'), day)
  const without = useApi<CapacityRow[]>(path('baseline'), day)
  const error = withCp.error ?? without.error
  const base = new Map((without.data ?? []).map((r) => [r.facility_id, r]))
  const limit = step.max_wait_days
  const wait = (w: number | null | undefined) => (w === null || w === undefined ? '–' : t('hospitals.days', { n: formatNumber(lang, w) }))
  const over = (w: number | null | undefined) => limit !== undefined && w !== null && w !== undefined && w > limit
  return (
    <section className="panel wide" aria-labelledby={`h-hosp-${step.id}`}>
      <h2 id={`h-hosp-${step.id}`}>
        {step.label[lang]}
        <Origin kind="code" />
      </h2>
      <div className="card-sub">
        {limit === undefined ? t('hospitals.sub') : t('hospitals.subLimit', { days: limit })}
      </div>
      {error && <p className="placeholder">{t('error.load', { detail: error })}</p>}
      {withCp.data && (
        <div className="table-wrap">
          <table className="compare-table">
            <thead>
              <tr>
                <th scope="col">{t('hospitals.facility')}</th>
                <th scope="col">{t('hospitals.use')}</th>
                <th scope="col">{t('hospitals.waitWith')}</th>
                <th scope="col">{t('hospitals.waitWithout')}</th>
              </tr>
            </thead>
            <tbody>
              {withCp.data.map((r) => {
                const b = base.get(r.facility_id)
                return (
                  <tr key={r.facility_id}>
                    <th scope="row">{r.name}</th>
                    <td>
                      {r.slots_total === 0
                        ? t('hospitals.closed')
                        : r.use_pct === null
                          ? '–'
                          : `${formatPercent(lang, r.use_pct, 0)} · ${formatNumber(lang, r.slots_booked ?? 0)}/${formatNumber(lang, r.slots_total ?? 0)}`}
                    </td>
                    <td className={over(r.wait_mean) ? 'over' : undefined}>{wait(r.wait_mean)}</td>
                    <td className={over(b?.wait_mean) ? 'over' : undefined}>{wait(b?.wait_mean)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
