import { useState } from 'react'
import { send, type SimStatus } from '../lib/api'
import { type Key, useLang } from '../lib/i18n'
import { SITUATIONS } from '../lib/situations'

/** The header's situation switch and clock, as in the console mockup (D67, proposed): the same calls as the
 * demo bar's keys, in sight. Each situation keeps its own day; at ×1 the server stops the clock on a wait alarm
 * (D63). ◀ ▶ look back at a past day of the situation, read only. */
export default function Controls({
  scenario,
  speed,
  day,
  past,
  onStatus,
  look,
}: {
  scenario: number | null
  speed: number
  /** the situation's day */
  day: number | null
  /** a past day looked back at, or null for today */
  past: number | null
  onStatus: (status: SimStatus) => void
  /** look at a day: today or later goes back to today */
  look: (day: number) => void
}) {
  const { t } = useLang()
  const [error, setError] = useState<string | null>(null)
  const run = (path: string, body?: unknown) => {
    setError(null)
    send<SimStatus>('POST', path, body)
      .then(onStatus)
      .catch((e: unknown) => setError(String(e)))
  }
  const shown = past ?? day
  const state = past !== null ? t('clock.past', { day: day ?? '' }) : speed > 0 ? t('clock.running', { speed }) : t('clock.paused')
  return (
    <>
      <div className="pills" role="group" aria-label={t('controls.situation')}>
        {SITUATIONS.map((n) => (
          <button key={n} type="button" aria-pressed={scenario === n} onClick={() => run(`/api/sim/scenario/${n}`)}>
            {t(`situation.${n}` as Key)}
          </button>
        ))}
      </div>
      <div className="clock">
        <div className="clock-buttons" role="group" aria-label={t('lookback.label')}>
          <button type="button" className="small" disabled={shown === null || shown <= 0} onClick={() => shown !== null && look(shown - 1)} aria-label={t('lookback.back')}>
            ◀
          </button>
        </div>
        <div className="clock-day">
          <strong>{shown === null ? '–' : t('top.day', { day: shown })}</strong>
          <span>{state}</span>
        </div>
        <div className="clock-buttons" role="group" aria-label={t('lookback.label')}>
          <button type="button" className="small" disabled={past === null} onClick={() => past !== null && look(past + 1)} aria-label={t('lookback.forward')}>
            ▶
          </button>
          {past !== null && (
            <button type="button" className="small" onClick={() => day !== null && look(day)}>
              {t('lookback.today')}
            </button>
          )}
        </div>
        <div className="clock-buttons" role="group" aria-label={t('controls.clock')}>
          <button type="button" aria-pressed={speed === 0} aria-label={t('clock.pauseLabel')} onClick={() => run('/api/sim/pause')}>
            II
          </button>
          {[1, 4].map((f) => (
            <button key={f} type="button" aria-pressed={speed === f} aria-label={t('clock.speedLabel', { speed: f })} onClick={() => run('/api/sim/speed', { factor: f })}>
              ×{f}
            </button>
          ))}
        </div>
        {error && (
          <span className="clock-error" role="alert">
            {t('bar.failed', { detail: error })}
          </span>
        )}
      </div>
    </>
  )
}
