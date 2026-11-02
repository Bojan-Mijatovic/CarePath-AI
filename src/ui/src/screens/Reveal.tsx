import type { ReactNode } from 'react'
import { type Reveal as Result, useApi } from '../lib/api'
import { useLang } from '../lib/i18n'

const ORDER = [2, 1, 3] // D44: the demo's order

/** Demo step 10 (prototype "Rivelazione"): for each scenario, what the agents' own alarms found next to where the
 * scenario hid its problems (GET /api/reveal, C37), which only this screen reads. With D44 there is no envelope:
 * all three scenarios side by side. */
export default function Reveal({ onRestart, langSwitch }: { onRestart: () => void; langSwitch: ReactNode }) {
  const { t } = useLang()
  return (
    <div className="intro">
      <div className="intro-bar">
        <span className="intro-brand">CarePath AI</span>
        <span className="spacer" />
        {langSwitch}
        <button type="button" className="intro-cta small" onClick={onRestart}>
          {t('reveal.restart')}
        </button>
      </div>
      <div className="intro-body column">
        <div className="intro-text narrow">
          <div className="kicker">{t('reveal.kicker')}</div>
          <h1 className="intro-title">{t('reveal.headline')}</h1>
        </div>
        <div className="reveal-grid">
          {ORDER.map((n) => (
            <ScenarioCard key={n} n={n} />
          ))}
        </div>
      </div>
    </div>
  )
}

function ScenarioCard({ n }: { n: number }) {
  const { lang, t } = useLang()
  const { data, error } = useApi<Result>(`/api/reveal/${n}`)
  const mark = (match: boolean) => (
    <span className={match ? 'reveal-mark ok' : 'reveal-mark'}>{match ? `✓ ${t('reveal.match')}` : t('reveal.noMatch')}</span>
  )
  const asst = (id: string) => `ASST ${id.replace('asst_', '').replace(/^./, (c) => c.toUpperCase())}`
  const notYet = <em>{t('reveal.notYet')}</em>
  return (
    <section className="reveal-card" aria-labelledby={`h-reveal-${n}`}>
      <h2 id={`h-reveal-${n}`}>{t('reveal.scenario', { n })}</h2>
      {error && <p className="intro-error">{t('error.load', { detail: error })}</p>}
      {data && (
        <dl className="reveal-rows">
          <dt>{t('reveal.bottleneck')}</dt>
          <dd>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.found')}</span>
              {data.bottleneck.found
                ? `${data.bottleneck.found.facility} · ${asst(data.bottleneck.found.asst_id)} (${t('reveal.day', { day: data.bottleneck.found.day })})`
                : notYet}
            </div>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.hidden')}</span>
              {`${data.bottleneck.hidden.facility} · ${asst(data.bottleneck.hidden.asst_id)}`}
            </div>
            {mark(data.bottleneck.match)}
          </dd>
          <dt>{t('reveal.mmg')}</dt>
          <dd>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.found')}</span>
              {data.mmg_group.found ? data.mmg_group.found.text[lang] : notYet}
            </div>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.hidden')}</span>
              {data.mmg_group.hidden.group}
            </div>
            {mark(data.mmg_group.match)}
          </dd>
          <dt>{t('reveal.comuni')}</dt>
          <dd>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.found')}</span>
              {data.rural_comuni.found ? data.rural_comuni.found.text[lang] : notYet}
            </div>
            <div className="reveal-side">
              <span className="reveal-label">{t('reveal.hidden')}</span>
              {data.rural_comuni.hidden.comuni.join(', ')}
            </div>
            {mark(data.rural_comuni.match)}{' '}
            <span className="card-sub">
              {t('reveal.named', { n: data.rural_comuni.hidden.named.length, total: data.rural_comuni.hidden.comuni.length })}
            </span>
          </dd>
        </dl>
      )}
    </section>
  )
}
