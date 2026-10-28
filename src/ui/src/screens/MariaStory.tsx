import type { ReactNode } from 'react'
import { type Patient360, useApi } from '../lib/api'
import { formatNumber, useLang } from '../lib/i18n'
import { conditions, storyLines } from '../lib/story'

/** Demo step 1 (prototype "Marija"): Maria's path without CarePath, from her baseline-arm timeline. The runs
 * stand on day 23 when the demo opens, so the story is the recording to day 62 (demo/story/, D35). */
export default function MariaStory({ onStart, langSwitch }: { onStart: () => void; langSwitch: ReactNode }) {
  const { lang, t } = useLang()
  const { data, error } = useApi<Patient360>('/api/patients/p_00001?run=s2_baseline&day=62')
  const p = data?.patient

  return (
    <div className="intro">
      <div className="intro-bar">
        <span className="intro-brand">CarePath AI</span>
        <span className="spacer" />
        <span className="intro-pill">{t('maria.pill')}</span>
        {langSwitch}
      </div>
      <div className="intro-body">
        <div className="intro-text">
          <div className="kicker">{t('maria.kicker')}</div>
          <h1 className="intro-title">{t('maria.headline')}</h1>
          {p && (
            <p className="intro-lead">
              {t(p.lives_alone ? 'maria.alone' : 'maria.notAlone', {
                age: p.age,
                km: formatNumber(lang, p.distance_km, 0),
                conditions: conditions(t, p.conditions),
              })}
            </p>
          )}
          <button type="button" className="intro-cta" onClick={onStart}>
            {t('maria.start')}
          </button>
        </div>
        <section className="story" aria-labelledby="h-without">
          <h2 id="h-without">{t('maria.without')}</h2>
          <div className="story-sub">{t('maria.dayByDay')}</div>
          {error && <p className="intro-error">{t('error.load', { detail: error })}</p>}
          {!data && !error && <p className="story-sub">{t('loading')}</p>}
          <ol className="story-lines">
            {data &&
              storyLines(data, lang).map((line) => (
                <li key={line.key} className={line.alarm ? 'alarm' : undefined}>
                  <span className="story-day">{t('top.day', { day: line.day })}</span>
                  <span>{t(line.key, line.vars)}</span>
                </li>
              ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
