import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import ActivityFeed from './components/ActivityFeed'
import Autonomy from './components/Autonomy'
import Guide from './components/Guide'
import LangSwitch from './components/LangSwitch'
import { type Kpi, type Pathway, type SimStatus, useApi } from './lib/api'
import { STEPS } from './lib/guide'
import { type Key, type Lang, LangContext, translator } from './lib/i18n'
import { type LeverRun, type StreamMessage, useStream } from './lib/stream'
import Ask from './screens/Ask'
import Beds, { type BedTarget } from './screens/Beds'
import Compare from './screens/Compare'
import Calls from './screens/Calls'
import DemoBar from './components/DemoBar'
import Reveal from './screens/Reveal'
import Flows from './screens/Flows'
import MapScreen, { type RegionalAlert } from './screens/MapScreen'
import MariaStory from './screens/MariaStory'
import Overview from './screens/Overview'
import Patient from './screens/Patient'
import WhatIf from './screens/WhatIf'

// Menu order follows the demo's (D66), Percorsi last as the demo does not show it; Maria's story (demo step 1)
// and the reveal (step 10) are full screen. There is no envelope screen (D44): the guide and the operator's demo
// bar pick the scenario.
const SCREENS = ['panoramica', 'mappa', 'chiedi', 'confronto', 'whatif', 'chiamate', 'pazienti', 'letti', 'percorsi'] as const
export type Screen = 'storia' | 'rivelazione' | (typeof SCREENS)[number]
const ALL: readonly Screen[] = ['storia', 'rivelazione', ...SCREENS]
const FEED_SIZE = 30
const LANG_KEY = 'carepath.lang'
const GUIDE_KEY = 'carepath.guide.step'

// A reload keeps the guide's stage: taking the stages again would run their clocks
function savedStep(): number {
  try {
    const n = Number(localStorage.getItem(GUIDE_KEY))
    return Number.isInteger(n) && n >= 0 && n < STEPS.length ? n : 0
  } catch {
    return 0
  }
}

function screenFromHash(): Screen {
  const id = location.hash.slice(1)
  return (ALL as readonly string[]).includes(id) ? (id as Screen) : 'storia'
}

function savedLang(): Lang {
  try {
    return localStorage.getItem(LANG_KEY) === 'en' ? 'en' : 'it'
  } catch {
    return 'it'
  }
}

type FeedMessage = Exclude<StreamMessage, { type: 'tick' }>

export default function App() {
  const [screen, setScreen] = useState<Screen>(screenFromHash)
  const [lang, setLang] = useState<Lang>(savedLang)
  const [day, setDay] = useState<number | null>(null)
  const [scenario, setScenario] = useState<number | null>(null)
  const [speed, setSpeed] = useState(1)
  const [kpi, setKpi] = useState<Kpi | null>(null)
  const [leverRun, setLeverRun] = useState<LeverRun | null>(null)
  const [feed, setFeed] = useState<FeedMessage[]>([])
  const [alarm, setAlarm] = useState<RegionalAlert | null>(null)
  const [bedTarget, setBedTarget] = useState<BedTarget | null>(null)
  const [guideStep, setGuideStep] = useState(savedStep)
  const t = translator(lang)

  useEffect(() => {
    try {
      localStorage.setItem(GUIDE_KEY, String(guideStep))
    } catch {
      // a blocked store only loses the stage on a reload
    }
  }, [guideStep])

  useEffect(() => {
    const onHash = () => setScreen(screenFromHash())
    window.addEventListener('hashchange', onHash)
    window.addEventListener('popstate', onHash) // back and forward after pushState
    return () => {
      window.removeEventListener('hashchange', onHash)
      window.removeEventListener('popstate', onHash)
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
    try {
      localStorage.setItem(LANG_KEY, lang)
    } catch {
      // a blocked store only loses the remembered language
    }
  }, [lang])

  const lastDay = useRef<number | null>(null)
  const onMessage = useCallback((msg: StreamMessage) => {
    if (msg.type === 'tick') {
      // A day before the last one means the server started over (reset, jump back, reconnect).
      if (lastDay.current !== null && msg.day < lastDay.current) {
        setFeed([])
        setAlarm(null)
      }
      lastDay.current = msg.day
      setDay(msg.day)
      setScenario(msg.scenario)
      if (msg.payload.kpi) setKpi(msg.payload.kpi)
      if (msg.payload.speed !== undefined) setSpeed(msg.payload.speed)
      setLeverRun(msg.payload.lever_run ?? null)
    } else if (msg.type === 'action') {
      // A decision or an undo sends the action again: it replaces its earlier line (step 2.29)
      setFeed((items) => {
        const at = items.findIndex((m) => m.type === 'action' && m.payload.action_id === msg.payload.action_id)
        return at < 0 ? [msg, ...items].slice(0, FEED_SIZE) : items.map((m, k) => (k === at ? msg : m))
      })
    } else {
      setFeed((items) => [msg, ...items].slice(0, FEED_SIZE))
      // The Mappa banner keeps the latest regional alarm; patient alerts would push it out of the feed.
      if (msg.type === 'alert' && msg.payload.level === 'regional') setAlarm({ day: msg.day, payload: msg.payload })
    }
  }, [])
  const connection = useStream(onMessage)
  const pathwayId = kpi?.pathway_id ?? null
  // Names come from the pathway file, so the console names no disease itself (AC17).
  const { data: pathway } = useApi<Pathway>(pathwayId ? `/api/pathways/${pathwayId}` : null)
  const go = useCallback((next: Screen) => {
    window.history.pushState(null, '', `#${next}`) // pushState fires no hashchange, so set the screen too
    setScreen(next)
    window.scrollTo(0, 0) // a new screen from its top, not where the last one was scrolled to
  }, [])
  // A click that does what the guide's next stage does moves the guide with it, unless that stage runs the clock
  const follow = (next: Screen) => {
    const coming = STEPS[guideStep + 1]
    if (coming && !coming.run && coming.screen === next && coming.scenario === scenario) setGuideStep(guideStep + 1)
    go(next)
  }
  const onStatus = useCallback((status: SimStatus) => setSpeed(status.speed), [])
  const restart = useCallback(() => setGuideStep(0), [])

  let content
  const langSwitch = <LangSwitch onChange={setLang} />
  // The runs stand paused on day 23 (D21); the operator starts the clock on Mappa (demo step 4).
  if (screen === 'storia') content = <MariaStory onStart={() => follow('panoramica')} langSwitch={langSwitch} />
  else if (screen === 'rivelazione')
    content = (
      <Reveal
        onRestart={() => {
          restart()
          go('storia')
        }}
        langSwitch={langSwitch}
      />
    )
  else {
    content = (
      <div className="shell">
        <nav className="nav" aria-label={t('nav.panoramica')}>
          <div className="brand">
            <strong>CarePath AI</strong>
            <span>{t('brand.ats')}</span>
          </div>
          <button type="button" className="nav-item" onClick={() => go('storia')}>
            {t('nav.storia')}
          </button>
          {SCREENS.map((name) => (
            <button
              key={name}
              type="button"
              className={`nav-item${name === screen ? ' active' : ''}${name === 'percorsi' ? ' muted' : ''}`}
              onClick={() => follow(name)}
            >
              {t(`nav.${name}` as Key)}
            </button>
          ))}
          <div className="nav-footer">{t('nav.footer')}</div>
        </nav>

        <main className="main">
          <header className="topbar">
            <h1>{t(`nav.${screen}` as Key)}</h1>
            {pathway && <span className="tag">{pathway.label[lang]}</span>}
            <span className="spacer" />
            <span className="day">{day === null ? '–' : t('top.day', { day })}</span>
            <span className="speed">{speed === 0 ? t('top.paused') : t('top.speed', { speed })}</span>
            <span className="pill">{t('top.synthetic')}</span>
            <LangSwitch onChange={setLang} />
            <span className={`connection ${connection}`}>{t(`conn.${connection}`)}</span>
          </header>
          <div className="body">
            <section className="content">
              {screen === 'panoramica' ? (
                <Overview day={day} kpi={kpi} pathway={pathway ?? null} />
              ) : screen === 'mappa' ? (
                <MapScreen day={day} pathwayId={pathwayId} alert={alarm} onInvestigation={() => follow('chiedi')} />
              ) : screen === 'percorsi' ? (
                <Flows day={day} pathwayId={pathwayId} />
              ) : screen === 'chiedi' ? (
                <Ask day={day} />
              ) : screen === 'confronto' ? (
                // Prototype step 6: autonomy on top, the comparison below it.
                <div className="overview">
                  <Autonomy day={day} />
                  <Compare day={day} scenario={scenario} pathway={pathway ?? null} leverRun={leverRun} />
                </div>
              ) : screen === 'whatif' ? (
                <WhatIf scenario={scenario} pathway={pathway ?? null} />
              ) : screen === 'chiamate' ? (
                <Calls day={day} />
              ) : screen === 'pazienti' ? (
                <Patient
                  day={day}
                  scenario={scenario}
                  pathway={pathway ?? null}
                  onAdmission={(target) => {
                    setBedTarget(target)
                    follow('letti')
                  }}
                />
              ) : screen === 'letti' ? (
                <Beds
                  key={bedTarget ? `${bedTarget.run}-${bedTarget.patientId}-${bedTarget.day}` : `s${scenario}`}
                  day={day}
                  scenario={scenario}
                  target={bedTarget?.run.startsWith(`s${scenario}_`) ? bedTarget : null}
                />
              ) : (
                <p className="placeholder">{t('placeholder.screen', { screen: t(`nav.${screen}` as Key) })}</p>
              )}
            </section>
            <ActivityFeed messages={feed} day={day} />
          </div>
        </main>
      </div>
    )
  }
  return (
    <LangContext value={lang}>
      {content}
      <Guide
        step={guideStep}
        setStep={setGuideStep}
        scenario={scenario}
        day={day}
        speed={speed}
        go={go}
        onStatus={onStatus}
      />
      <DemoBar day={day} speed={speed} onReveal={() => go('rivelazione')} onStatus={onStatus} onReset={restart} />
    </LangContext>
  )
}
