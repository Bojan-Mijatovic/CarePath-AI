import { useEffect, useState } from 'react'
import { type Investigation, useApi } from '../lib/api'
import { useLang } from '../lib/i18n'

const STEP_MS = 700 // one step after another, as the prototype shows them

/** Demo step 5 (prototype "Chiedi"): the investigation of the latest regional alarm, step by step, each step
 * with the tool it called, the code's summary of its result and the claims it supports (SPEC §6, C24). The
 * Verifier (C33) repeated each step's call: a step is "verificato" when all its claims passed and "corretto"
 * when one had an issue, shown under the claim; without a verdict it stays "da verificare". */
export default function Ask({ day }: { day: number | null }) {
  const { lang, t } = useLang()
  const { data, error } = useApi<Investigation[]>('/api/investigations', day)
  const inv = data?.[0]
  const [shown, setShown] = useState<{ id?: string; steps: number }>({ steps: 0 })

  useEffect(() => {
    if (!inv) return
    const total = inv.steps.length
    const timer = window.setInterval(() => {
      setShown((s) => {
        if (s.id !== inv.investigation_id) return { id: inv.investigation_id, steps: 1 }
        if (s.steps >= total) {
          window.clearInterval(timer)
          return s
        }
        return { ...s, steps: s.steps + 1 }
      })
    }, STEP_MS)
    return () => window.clearInterval(timer)
  }, [inv])

  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  if (!data) return <p className="placeholder">{t('loading')}</p>
  if (!inv) return <p className="placeholder">{t('ask.empty')}</p>
  const steps = shown.id === inv.investigation_id ? inv.steps.slice(0, shown.steps) : []
  const done = steps.length === inv.steps.length

  return (
    <div className="ask">
      <section className="panel">
        <div className="card-sub">
          {t('ask.kicker')} · {t('ask.day', { day: inv.day })}
        </div>
        <h2 className="ask-question">{inv.question[lang]}</h2>
      </section>
      <section className="panel" aria-labelledby="h-steps">
        <h2 id="h-steps">{t('ask.steps')}</h2>
        <ol className="ask-steps" aria-live="polite">
          {steps.map((s) => {
            const claims = inv.claims.filter((c) => c.step === s.step)
            const marks = claims.map((c) => c.verified).filter((v) => v !== undefined && v !== null)
            const badge = marks.length === 0 ? 'unverified' : marks.every(Boolean) ? 'verified' : 'corrected'
            return (
              <li key={s.step} className="ask-step">
                <div className="ask-step-head">
                  <span className="ask-step-n">{t('ask.step', { step: s.step })}</span>
                  <code className="ask-tool">{s.tool}</code>
                  <span className={`ask-badge ask-badge-${badge}`}>{t(`ask.${badge}`)}</span>
                </div>
                <div className="ask-summary">{s.result_summary[lang]}</div>
                <ul className="ask-claims">
                  {claims.map((c, i) => (
                    <li key={i}>
                      {c.text[lang]}
                      {c.issues?.map((issue, j) => (
                        <div key={j} className="ask-issue">
                          {t('ask.correction')}: {issue.text[lang]}
                        </div>
                      ))}
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ol>
      </section>
      {done && (
        <section className="panel" aria-labelledby="h-conclusion">
          <h2 id="h-conclusion">{t('ask.conclusion')}</h2>
          <p className="ask-conclusion">{inv.conclusion[lang]}</p>
        </section>
      )}
    </div>
  )
}
