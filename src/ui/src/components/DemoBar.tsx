import { useCallback, useEffect, useRef, useState } from 'react'
import { send, type SimStatus, useApi } from '../lib/api'
import { useLang } from '../lib/i18n'

const ORDER = [2, 1, 3] // D44: the demo walks the scenarios in this order
type Mode = 'cache_only' | 'cache_first'

/** The operator's hidden demo bar (delivery plan step 2.20, Solution Plan §11): scenario, pause, speed, jump to a
 * day, the LLM's cache switch and reset, with hotkeys that work while the bar is hidden. The audience never sees
 * it; the cache indicator is for the team (D14: the demo starts in cache_only). Keys are ignored while the
 * focus is in a text field. */
export default function DemoBar({
  day,
  speed,
  onReveal,
  onStatus,
  onReset,
}: {
  day: number | null
  speed: number
  onReveal: () => void
  /** The server's answer to a clock command: a pause sends no tick, so the top bar would keep the old speed */
  onStatus: (status: SimStatus) => void
  onReset: () => void
}) {
  const { t } = useLang()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [changes, setChanges] = useState(0)
  const jumpField = useRef<HTMLInputElement>(null)
  const { data: cache } = useApi<{ mode: Mode }>('/api/sim/cache', changes)

  const run = useCallback(
    (method: 'POST' | 'PUT', path: string, body?: unknown) => {
      setError(null)
      send<SimStatus | { mode: Mode }>(method, path, body)
        .then((status) => {
          setChanges((k) => k + 1)
          if ('speed' in status) onStatus(status)
        })
        .catch((e: unknown) => setError(String(e)))
    },
    [onStatus],
  )
  const setSpeed = useCallback((factor: number) => run('POST', '/api/sim/speed', { factor }), [run])
  const jump = () => {
    const d = Number(draft)
    if (Number.isInteger(d) && d >= 0) run('POST', `/api/sim/jump/${d}`)
    setDraft('')
  }
  const toggleCache = useCallback(
    () => run('PUT', '/api/sim/cache', { mode: cache?.mode === 'cache_only' ? 'cache_first' : 'cache_only' }),
    [run, cache],
  )
  const reset = useCallback(() => {
    if (window.confirm(t('bar.resetConfirm'))) {
      run('POST', '/api/sim/reset')
      onReset()
    }
  }, [run, t, onReset])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) return
      const keys: Record<string, () => void> = {
        '`': () => setOpen((o) => !o),
        '1': () => run('POST', '/api/sim/scenario/1'),
        '2': () => run('POST', '/api/sim/scenario/2'),
        '3': () => run('POST', '/api/sim/scenario/3'),
        ' ': () => setSpeed(speed === 0 ? 1 : 0),
        f: () => setSpeed(4),
        j: () => {
          setOpen(true)
          window.setTimeout(() => jumpField.current?.focus(), 0)
        },
        c: toggleCache,
        r: reset,
        v: onReveal,
      }
      // The key left of 1 by its place, not its character: on an Italian or Serbian layout it types \ or ‚
      const action = e.code === 'Backquote' ? keys['`'] : keys[e.key]
      if (action) {
        e.preventDefault()
        action()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [run, setSpeed, speed, toggleCache, reset, onReveal])

  if (!open) return null
  return (
    <aside className="demobar" aria-label={t('bar.title')}>
      <div className="demobar-row">
        {ORDER.map((n) => (
          <button key={n} type="button" onClick={() => run('POST', `/api/sim/scenario/${n}`)}>
            {t('bar.scenario', { n })}
          </button>
        ))}
      </div>
      <div className="demobar-row">
        <button type="button" aria-pressed={speed === 0} onClick={() => setSpeed(0)}>
          {t('bar.pause')}
        </button>
        <button type="button" aria-pressed={speed === 1} onClick={() => setSpeed(1)}>
          ×1
        </button>
        <button type="button" aria-pressed={speed === 4} onClick={() => setSpeed(4)}>
          ×4
        </button>
        <input
          ref={jumpField}
          type="number"
          min={0}
          aria-label={t('bar.jump')}
          placeholder={day === null ? t('bar.jump') : String(day)}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && jump()}
        />
        <button type="button" onClick={jump}>
          {t('bar.go')}
        </button>
      </div>
      <div className="demobar-row">
        <span className={cache?.mode === 'cache_only' ? 'demobar-cache' : 'demobar-cache live'}>
          {t('bar.cache', { mode: cache?.mode ?? '…' })}
        </span>
        <button type="button" onClick={toggleCache}>
          {t('bar.cacheToggle')}
        </button>
        <button type="button" onClick={reset}>
          {t('bar.reset')}
        </button>
        <button type="button" onClick={onReveal}>
          {t('bar.reveal')}
        </button>
      </div>
      <div className="demobar-keys">{t('bar.keys')}</div>
      {error && <div className="demobar-error">{t('bar.failed', { detail: error })}</div>}
    </aside>
  )
}
