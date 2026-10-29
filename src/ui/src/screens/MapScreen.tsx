import { type MapRow, useApi } from '../lib/api'
import { useGeo } from '../lib/geo'
import { formatPercent, type Key, useLang } from '../lib/i18n'
import type { AlertPayload } from '../lib/stream'

type Band = 'high' | 'medium' | 'low' | 'none'

/** The prototype's bands; `alarm` (C18) is the low band with at least 10 patients. */
function band(row: MapRow | undefined): Band {
  const a = row?.adherence_pct
  if (a === null || a === undefined) return 'none'
  return a >= 0.7 ? 'high' : a >= 0.5 ? 'medium' : 'low'
}

export type RegionalAlert = { day: number; payload: AlertPayload }

/** Demo step 4 (prototype "Mappa"): adherence by comune, recoloured every day, and the regional alarm. */
export default function MapScreen({
  day,
  pathwayId,
  alert,
  onInvestigation,
}: {
  day: number | null
  pathwayId: string | null
  alert: RegionalAlert | null
  onInvestigation: () => void
}) {
  const { lang, t } = useLang()
  const { geo, error: geoError } = useGeo()
  const { data: rows, error } = useApi<MapRow[]>(pathwayId ? `/api/map?pathway_id=${pathwayId}` : null, day)
  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  if (!rows || (!geo && !geoError)) return <p className="placeholder">{t('loading')}</p>

  const byIstat = new Map(rows.map((r) => [r.comune_istat, r]))
  const names = new Map((geo?.comuni ?? []).map((c) => [c.istat, c.name]))
  const name = (istat: string) => names.get(istat) ?? istat
  const pct = (r: MapRow) => (r.adherence_pct === null ? '–' : formatPercent(lang, r.adherence_pct, 0))
  const alarms = rows.filter((r) => r.alarm).sort((a, b) => (a.adherence_pct ?? 0) - (b.adherence_pct ?? 0))

  return (
    <div className="mapscreen">
      {alert && (
        <div className="alarm-banner" role="alert">
          <div className="alarm-text">
            <div className="alarm-head">{t('map.regional', { day: alert.day })}</div>
            <div>{alert.payload.text[lang]}</div>
          </div>
          {alert.payload.investigation_id && (
            <button type="button" className="alarm-open" onClick={onInvestigation}>
              {t('map.open')}
            </button>
          )}
        </div>
      )}
      <div className="legend">
        <span>{t('map.legend')}</span>
        {(['high', 'medium', 'low', 'none'] as const).map((b) => (
          <span key={b} className="legend-item">
            <span className={`swatch band-${b}`} aria-hidden="true" />
            {t(`map.${b}` as Key)}
          </span>
        ))}
        <span className="legend-item">
          <span className="swatch outline" aria-hidden="true" />
          {t('map.outline')}
        </span>
      </div>
      {geo ? (
        <svg className="map" viewBox={`0 0 ${geo.width} ${geo.height}`} role="img" aria-label={t('map.label')}>
          {/* Comuni in alarm last, so their outline is not covered by a neighbour. */}
          {[...geo.comuni]
            .sort((a, b) => Number(byIstat.get(a.istat)?.alarm ?? false) - Number(byIstat.get(b.istat)?.alarm ?? false))
            .map((c) => {
              const r = byIstat.get(c.istat)
              return (
                <path key={c.istat} d={c.d} className={`band-${band(r)}${r?.alarm ? ' alarm-outline' : ''}`}>
                  <title>{r && r.adherence_pct !== null ? t('map.tip', { name: c.name, pct: pct(r) }) : t('map.tipNone', { name: c.name })}</title>
                </path>
              )
            })}
        </svg>
      ) : (
        <>
          {/* The cut-order fallback (delivery plan §8): the comune table, as in the prototype. */}
          <p className="placeholder">{t('map.geoError', { detail: geoError ?? '' })}</p>
          <Tiles rows={rows} name={name} pct={pct} />
        </>
      )}
      <section className="panel" aria-labelledby="h-alarms">
        <h2 id="h-alarms">{t('map.alarms', { count: alarms.length })}</h2>
        {alarms.length === 0 && <p className="placeholder">{t('map.noAlarms')}</p>}
        <Tiles rows={alarms} name={name} pct={pct} />
      </section>
    </div>
  )
}

function Tiles({ rows, name, pct }: { rows: MapRow[]; name: (istat: string) => string; pct: (r: MapRow) => string }) {
  return (
    <ul className="tiles">
      {rows.map((r) => (
        <li key={r.comune_istat} className={`tile band-${band(r)}${r.alarm ? ' alarm-outline' : ''}`}>
          <div className="tile-name">{name(r.comune_istat)}</div>
          <div>{pct(r)}</div>
        </li>
      ))}
    </ul>
  )
}
