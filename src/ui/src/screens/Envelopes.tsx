import { type ReactNode, useState } from 'react'
import { useLang } from '../lib/i18n'

/** Demo step 2 (prototype "Koverta"): the audience picks envelope 1, 2 or 3; the agents are not told. */
export default function Envelopes({ onChosen, langSwitch }: { onChosen: () => void; langSwitch: ReactNode }) {
  const { t } = useLang()
  const [error, setError] = useState<string | null>(null)

  const choose = (n: number) => {
    fetch(`/api/sim/scenario/${n}`, { method: 'POST' })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        onChosen()
      })
      .catch((e: unknown) => setError(String(e)))
  }

  return (
    <div className="intro">
      <div className="intro-bar">
        <span className="intro-brand">CarePath AI</span>
        <span className="spacer" />
        <span className="intro-pill">{t('busta.pill')}</span>
        {langSwitch}
      </div>
      <div className="intro-body column">
        <div className="intro-text narrow">
          <div className="kicker">{t('busta.kicker')}</div>
          <h1 className="intro-title">{t('busta.headline')}</h1>
          <p className="intro-lead">{t('busta.body')}</p>
        </div>
        <div className="envelopes">
          {[1, 2, 3].map((n) => (
            <button key={n} type="button" className="envelope" aria-label={t('busta.label', { n })} onClick={() => choose(n)}>
              <svg width="56" height="40" viewBox="0 0 56 40" aria-hidden="true">
                <rect x="2" y="2" width="52" height="36" rx="4" fill="none" stroke="#8C7B55" strokeWidth="2" />
                <path d="M2 6l26 18L54 6" fill="none" stroke="#8C7B55" strokeWidth="2" strokeLinejoin="round" />
              </svg>
              <span>
                <span className="envelope-number">{n}</span>
                <span className="envelope-label">{t('busta.sealed')}</span>
              </span>
            </button>
          ))}
        </div>
        {error && <p className="intro-error">{t('error.load', { detail: error })}</p>}
        <p className="intro-note">{t('busta.footer')}</p>
      </div>
    </div>
  )
}
