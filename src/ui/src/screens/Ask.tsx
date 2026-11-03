import { useEffect, useState } from 'react'
import Origin from '../components/Origin'
import { type Investigation, send, useApi } from '../lib/api'
import { useLang } from '../lib/i18n'

const STEP_MS = 700 // one step after another, as the prototype shows them

/** Demo step 5 (prototype "Chiedi"): the investigation of the latest regional alarm, step by step, each step
 * with the tool it called, the code's summary of its result and the claims it supports (SPEC §6, C24). The
 * Verifier (C33) repeated each step's call: a step is "verificato" when all its claims passed and "corretto"
 * when one had an issue, shown under the claim; without a verdict it stays "da verificare". */
export default function Ask({ day }: { day: number | null }) {
  const { lang, t } = useLang()
  const [asked, setAsked] = useState(0)
  const { data, error } = useApi<Investigation[]>('/api/investigations', `${day}-${asked}`)
  const inv = data?.[0]
  const [shown, setShown] = useState<{ id?: string; steps: number }>({ steps: 0 })
  const { data: cache } = useApi<{ mode: string }>('/api/sim/cache', `${day}-${asked}`) // the gateway's mode (C37)

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

  const box = <QuestionBox day={day} onAnswered={() => setAsked((k) => k + 1)} />
  if (error) return <p className="placeholder">{t('error.load', { detail: error })}</p>
  if (!data) return <p className="placeholder">{t('loading')}</p>
  if (!inv)
    return (
      <div className="ask">
        {box}
        <p className="placeholder">{t('ask.empty')}</p>
      </div>
    )
  const steps = shown.id === inv.investigation_id ? inv.steps.slice(0, shown.steps) : []
  const done = steps.length === inv.steps.length

  return (
    <div className="ask">
      {box}
      <section className="panel">
        <div className="card-sub">
          {inv.alert_id ? t('ask.kicker') : t('ask.kickerQuestion')} · {t('ask.day', { day: inv.day })}
        </div>
        <h2 className="ask-question">{inv.question[lang]}</h2>
        {/* D14: the demo shows what the local model wrote at the warm-up; the audience is told so, not left to guess */}
        {cache?.mode === 'cache_only' && <p className="ask-prepared">{t('ask.prepared')}</p>}
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
                <div className="ask-summary">
                  {s.result_summary[lang]}
                  <Origin kind="code" />
                </div>
                {claims.length > 0 && (
                  <div className="ask-origin">
                    <Origin kind="model" />
                  </div>
                )}
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
          <h2 id="h-conclusion">
            {t('ask.conclusion')}
            <Origin kind="model" />
          </h2>
          <p className="ask-conclusion">{inv.conclusion[lang]}</p>
        </section>
      )}
    </div>
  )
}

/** C40: the questions the demo has an answer for on its alarm day (the cache manifest's, from the API, so the
 * console holds no question of its own, AC17), and a free one. In the demo the answer comes from the cache
 * (D14): a question nobody prepared gets a plain "no answer prepared", never a made-up one. */
function QuestionBox({ day, onAnswered }: { day: number | null; onAnswered: () => void }) {
  const { t } = useLang()
  const { data } = useApi<{ scenario: number; day: number | null; questions: string[] }>('/api/questions', day)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const ask = (question: string) => {
    if (question.trim().length < 3) return
    setBusy(true)
    setNote(null)
    send('POST', '/api/ask', { question: question.trim() })
      .then(() => {
        setDraft('')
        onAnswered()
      })
      .catch((e: unknown) => setNote(String(e).includes('503') ? t('ask.noAnswer') : t('error.load', { detail: String(e) })))
      .finally(() => setBusy(false))
  }
  return (
    <section className="panel" aria-labelledby="h-ask-box">
      <h2 id="h-ask-box">{t('ask.box')}</h2>
      {data && data.questions.length > 0 && (
        <div className="ask-suggestions">
          {data.questions.map((q) => (
            <button key={q} type="button" disabled={busy} onClick={() => ask(q)}>
              {q}
            </button>
          ))}
          {data.day !== null && day !== data.day && <div className="card-sub">{t('ask.suggestionsDay', { day: data.day })}</div>}
        </div>
      )}
      <div className="ask-free">
        <input
          type="text"
          value={draft}
          placeholder={t('ask.placeholder')}
          aria-label={t('ask.box')}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && ask(draft)}
        />
        <button type="button" className="primary" disabled={busy} onClick={() => ask(draft)}>
          {t('ask.send')}
        </button>
      </div>
      {note && <p className="ask-note">{note}</p>}
    </section>
  )
}
