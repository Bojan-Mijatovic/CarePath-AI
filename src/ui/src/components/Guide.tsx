import { useCallback, useEffect, useRef, useState } from 'react'
import type { Screen } from '../App'
import { send, type SimStatus } from '../lib/api'
import { type Step, STEPS } from '../lib/guide'
import { type Key, useLang } from '../lib/i18n'

const HIDDEN_KEY = 'carepath.guide.hidden'

function savedHidden(): boolean {
  try {
    return localStorage.getItem(HIDDEN_KEY) === '1'
  } catch {
    return false
  }
}

/** The guide bar (D66): the audience sees the demo's stage, its title and one sentence; ▶ (or PageDown, a
 * presenter's clicker) takes the next stage: its scenario, its screen and its clock. Approvals stay the
 * operator's clicks. `g` hides it; the hidden demo bar and its keys stay as the fallback. */
export default function Guide({
  step,
  setStep,
  scenario,
  day,
  speed,
  go,
  onStatus,
}: {
  step: number
  setStep: (step: number) => void
  scenario: number | null
  day: number | null
  speed: number
  go: (screen: Screen) => void
  onStatus: (status: SimStatus) => void
}) {
  const { t } = useLang()
  const [hidden, setHidden] = useState(savedHidden)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stopping = useRef(false)
  const current = STEPS[step]
  const running = speed > 0
  const title = (s: Step) => t(`guide.${s.key}.title` as Key)

  const enter = useCallback(
    async (k: number, play: boolean) => {
      const s = STEPS[k]
      setBusy(true)
      setError(null)
      try {
        const chosen = s.scenario === scenario ? null : await send<SimStatus>('POST', `/api/sim/scenario/${s.scenario}`)
        go(s.screen)
        setStep(k)
        const today = chosen?.day ?? day
        // Never past the stage's day: a stage taken again after its clock ran leaves the clock alone
        if (play && s.run && today !== null && today < s.run.until)
          onStatus(await send<SimStatus>('POST', '/api/sim/speed', { factor: s.run.speed }))
      } catch (e) {
        setError(String(e))
      } finally {
        setBusy(false)
      }
    },
    [scenario, day, go, setStep, onStatus],
  )
  const canMove = !busy && !running
  const next = useCallback(() => {
    if (canMove && step < STEPS.length - 1) void enter(step + 1, true)
  }, [canMove, step, enter])
  const back = useCallback(() => {
    if (canMove && step > 0) void enter(step - 1, false)
  }, [canMove, step, enter])

  // The script's day for a run at ×4 (the server stops ×1 on the alarm itself); the pause lands a day later at most
  useEffect(() => {
    const r = current.run
    if (!r || !running || day === null || day < r.until || scenario !== current.scenario || stopping.current) return
    stopping.current = true
    send<SimStatus>('POST', '/api/sim/speed', { factor: 0 })
      .then(onStatus)
      .catch((e: unknown) => setError(String(e)))
      .finally(() => {
        stopping.current = false
      })
  }, [current, running, day, scenario, onStatus])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      const keys: Record<string, () => void> = {
        PageDown: next,
        ArrowRight: next,
        PageUp: back,
        ArrowLeft: back,
        g: () => setHidden((h) => !h),
      }
      const action = keys[e.key]
      if (action) {
        e.preventDefault()
        action()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [next, back])

  // The first outlined button into view, once its screen has loaded: the queue can put it below the fold
  useEffect(() => {
    const spots = current.spots
    if (hidden || !spots) return
    let tries = 0
    const timer = window.setInterval(() => {
      const first = spots.map((s) => document.querySelector(`[data-spot="${s}"]`)).find((e) => e !== null)
      if (first || ++tries > 20) {
        window.clearInterval(timer)
        first?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }, 150)
    return () => window.clearInterval(timer)
  }, [current, hidden])

  useEffect(() => {
    document.body.classList.toggle('guided', !hidden)
    try {
      localStorage.setItem(HIDDEN_KEY, hidden ? '1' : '0')
    } catch {
      // a blocked store only loses whether the bar was hidden
    }
  }, [hidden])

  if (hidden) return null
  const spots = current.spots ?? []
  const watch = current.watch ?? []
  const selector = (names: string[]) => names.map((s) => `[data-spot="${s}"]`).join(',')
  const following = STEPS[step + 1]
  return (
    <aside className="guide" aria-label={t('guide.title')}>
      {spots.length > 0 && (
        <style>{`${selector(spots)}{outline:3px solid var(--primary);outline-offset:3px;animation:guide-spot 1.6s ease-in-out infinite}`}</style>
      )}
      {/* inside the element: the agents' panel stands on the window's right edge */}
      {watch.length > 0 && <style>{`${selector(watch)}{outline:3px dashed var(--primary);outline-offset:-4px}`}</style>}
      <div className="guide-count">
        {t('guide.count', { n: step + 1, total: STEPS.length })}
        {current.optional && <span className="guide-optional">{t('guide.optional')}</span>}
      </div>
      <div className="guide-text">
        <strong>{title(current)}</strong>
        <span>{t(`guide.${current.key}.text` as Key, { day: current.run?.until ?? '' })}</span>
        <span className="guide-behind">
          <b>{t('guide.behind')}</b> {t(`guide.${current.key}.behind` as Key)}
        </span>
      </div>
      {error ? (
        <div className="guide-clock failed">{t('guide.failed', { detail: error })}</div>
      ) : (
        running && (
          <div className="guide-clock">
            {t('guide.running', { speed, day: day ?? '–', until: current.run?.until ?? '–' })}
          </div>
        )
      )}
      <div className="guide-buttons">
        <button type="button" aria-label={t('guide.back')} disabled={!canMove || step === 0} onClick={back}>
          ◀
        </button>
        <button
          type="button"
          className="primary"
          aria-label={following ? t('guide.next', { title: title(following) }) : t('guide.last')}
          title={following ? t('guide.next', { title: title(following) }) : t('guide.last')}
          disabled={!canMove || !following}
          onClick={next}
        >
          ▶
        </button>
      </div>
    </aside>
  )
}
