import { type MapRow } from '../lib/api'
import { useGeo } from '../lib/geo'
import { formatPercent, type Key, useLang } from '../lib/i18n'
import type { AlertPayload } from '../lib/stream'

export type RegionalAlert = { day: number; payload: AlertPayload }

/** A hospital drawn on the map: the facilities of the pathway step with a wait threshold, today. */
export type Site = { facility_id: string; name: string; lat: number; lon: number; state: 'alarm' | 'closed' | 'new' | 'open' }

const BANDS = ['b0', 'b1', 'b2', 'b3', 'b4'] as const

/** The mockup's five bands of the share on their care plan: under 70%, then steps of 5 points. */
function band(row: MapRow | undefined): string {
  const a = row?.adherence_pct
  if (a === null || a === undefined) return 'none'
  return a < 0.7 ? 'b0' : a < 0.75 ? 'b1' : a < 0.8 ? 'b2' : a < 0.85 ? 'b3' : 'b4'
}

/** Demo step 4 (prototype "Mappa") as in the console mockup: the share on their care plan by comune, with or
 * without CarePath, recoloured every day, and the hospitals of the step with a wait threshold. */
export default function MapPanel({
  rows,
  arm,
  setArm,
  sites,
  selected,
}: {
  rows: MapRow[] | undefined
  arm: 'with' | 'without'
  setArm: (arm: 'with' | 'without') => void
  sites: Site[]
  selected: string | null
}) {
  const { lang, t } = useLang()
  const { geo, error: geoError } = useGeo()
  const byIstat = new Map((rows ?? []).map((r) => [r.comune_istat, r]))
  const pct = (r: MapRow) => (r.adherence_pct === null ? '–' : formatPercent(lang, r.adherence_pct, 0))
  const states = [...new Set(sites.map((s) => s.state))].filter((s) => s !== 'open')

  return (
    <section className="panel map-panel" aria-labelledby="h-map">
      <div className="panel-head">
        <h2 id="h-map">{t('map.title')}</h2>
        <div className="segmented" role="group" aria-label={t('map.arms')}>
          {(['with', 'without'] as const).map((a) => (
            <button key={a} type="button" aria-pressed={arm === a} onClick={() => setArm(a)}>
              {t(`map.${a}`)}
            </button>
          ))}
        </div>
      </div>
      {!rows || (!geo && !geoError) ? (
        <p className="placeholder">{t('loading')}</p>
      ) : geo ? (
        <svg className="map" viewBox={`0 0 ${geo.width} ${geo.height}`} role="img" aria-label={t('map.label')}>
          {geo.comuni.map((c) => {
            const r = byIstat.get(c.istat)
            return (
              <path key={c.istat} d={c.d} className={`band-${band(r)}`}>
                <title>{r && r.adherence_pct !== null ? t('map.tip', { name: c.name, pct: pct(r) }) : t('map.tipNone', { name: c.name })}</title>
              </path>
            )
          })}
          {geo.comuni
            .filter((c) => c.istat === selected)
            .map((c) => (
              <path key="selected" d={c.d} className="selected" />
            ))}
          {sites.map((s) => {
            const [x, y] = geo.point(s.lon, s.lat)
            return (
              <g key={s.facility_id} className={`site site-${s.state}`}>
                <circle cx={x} cy={y} r={s.state === 'open' ? 7 : 10} />
                <text x={x} y={y - 15} textAnchor="middle">
                  {s.name}
                </text>
              </g>
            )
          })}
        </svg>
      ) : (
        <p className="placeholder">{t('map.geoError', { detail: geoError ?? '' })}</p>
      )}
      <div className="legend">
        {BANDS.map((b) => (
          <span key={b} className="legend-item">
            <span className={`swatch band-${b}`} aria-hidden="true" />
            {t(`map.${b}`)}
          </span>
        ))}
        {states.map((s) => (
          <span key={s} className="legend-item">
            <span className={`dot site-${s}`} aria-hidden="true" />
            {t(`map.dot.${s}` as Key)}
          </span>
        ))}
      </div>
    </section>
  )
}
