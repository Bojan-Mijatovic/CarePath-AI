import { useState } from 'react'
import { type Autonomy as Levels, send, useApi } from '../lib/api'
import Origin from './Origin'
import { type Key, label, useLang } from '../lib/i18n'

// The Intervention's action types, the ones the demo shows (prototype step 6); the others belong to agents
// the demo leaves out.
const SHOWN = ['reschedule', 'notify_mmg', 'call_task', 'reminder']
const LEVELS = [0, 1, 2, 3] as const

/** Demo step 6 (prototype "Autonomija agenata"): the manager sets how much the AI may do alone, per action
 * type; every change goes to the audit log (SPEC §7, step 2.18). */
export default function Autonomy({ day }: { day: number | null }) {
  const { t } = useLang()
  const [changes, setChanges] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const { data, error: loadError } = useApi<{ autonomy: Levels }>('/api/settings', `${day}-${changes}`)
  if (loadError) return <p className="placeholder">{t('error.load', { detail: loadError })}</p>
  const set = (type: string, level: number) => {
    setError(null)
    send('PUT', '/api/settings/autonomy', { type, level })
      .then(() => setChanges((k) => k + 1))
      .catch(() => setError(t('autonomy.failed')))
  }

  return (
    <section className="panel autonomy" aria-labelledby="h-autonomy">
      <h2 id="h-autonomy">
        {t('autonomy.title')}
        <Origin kind="person" />
      </h2>
      <p className="lead">{t('autonomy.lead')}</p>
      {error && <p className="placeholder">{error}</p>}
      {data &&
        SHOWN.filter((type) => type in data.autonomy).map((type) => {
          const { level, fixed } = data.autonomy[type]
          return (
            <div key={type} className="autonomy-row">
              <span className="autonomy-type">{label(t, 'action', type)}</span>
              <div className="levels" role="radiogroup" aria-label={label(t, 'action', type)}>
                {LEVELS.map((l) => (
                  <button
                    key={l}
                    type="button"
                    role="radio"
                    aria-checked={l === level}
                    className={l === level ? 'level active' : 'level'}
                    data-spot={l === level ? undefined : `autonomy-${type}-${l}`}
                    disabled={fixed}
                    onClick={() => l !== level && set(type, l)}
                  >
                    {t(`autonomy.level${l}` as Key)}
                  </button>
                ))}
              </div>
            </div>
          )
        })}
    </section>
  )
}
