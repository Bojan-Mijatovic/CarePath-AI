import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import ActivityFeed from './components/ActivityFeed'
import LangSwitch from './components/LangSwitch'
import { type Kpi, type Pathway, useApi } from './lib/api'
import { type Key, type Lang, LangContext, translator } from './lib/i18n'
import { type StreamMessage, useStream } from './lib/stream'
import Envelopes from './screens/Envelopes'
import Flows from './screens/Flows'
import MapScreen, { type RegionalAlert } from './screens/MapScreen'
import MariaStory from './screens/MariaStory'
import Overview from './screens/Overview'

// Menu order follows the prototype; the two intro screens (demo steps 1 and 2) are full screen.
const SCREENS = ['panoramica', 'mappa', 'chiedi', 'confronto', 'whatif', 'percorsi', 'chiamate', 'letti', 'pazienti'] as const
type Screen = 'storia' | 'buste' | (typeof SCREENS)[number]
const ALL: readonly Screen[] = ['storia', 'buste', ...SCREENS]
const FEED_SIZE = 30
const LANG_KEY = 'carepath.lang'

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
  const [speed, setSpeed] = useState(1)
  const [kpi, setKpi] = useState<Kpi | null>(null)
  const [feed, setFeed] = useState<FeedMessage[]>([])
  const [alarm, setAlarm] = useState<RegionalAlert | null>(null)
  const t = translator(lang)

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
      if (msg.payload.kpi) setKpi(msg.payload.kpi)
      if (msg.payload.speed !== undefined) setSpeed(msg.payload.speed)
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
  const go = (next: Screen) => {
    window.history.pushState(null, '', `#${next}`) // pushState fires no hashchange, so set the screen too
    setScreen(next)
  }

  let content
  const langSwitch = <LangSwitch onChange={setLang} />
  if (screen === 'storia') content = <MariaStory onStart={() => go('buste')} langSwitch={langSwitch} />
  else if (screen === 'buste') content = <Envelopes onChosen={() => go('panoramica')} langSwitch={langSwitch} />
  else {
    content = (
      <div className="shell">
        <nav className="nav" aria-label={t('nav.panoramica')}>
          <div className="brand">
            <strong>CarePath AI</strong>
            <span>{t('brand.ats')}</span>
          </div>
          {SCREENS.map((name) => (
            <button
              key={name}
              type="button"
              className={name === screen ? 'nav-item active' : 'nav-item'}
              onClick={() => go(name)}
            >
              {t(`nav.${name}` as Key)}
            </button>
          ))}
          <button type="button" className="nav-item muted" onClick={() => go('storia')}>
            {t('nav.storia')}
          </button>
          <div className="nav-footer">{t('nav.footer')}</div>
        </nav>

        <main className="main">
          <header className="topbar">
            <h1>{t(`nav.${screen}` as Key)}</h1>
            {pathway && <span className="tag">{pathway.label[lang]}</span>}
            <span className="spacer" />
            <span className="day">{day === null ? '–' : t('top.day', { day })}</span>
            <span className="speed">{t('top.speed', { speed })}</span>
            <span className="pill">{t('top.synthetic')}</span>
            <LangSwitch onChange={setLang} />
            <span className={`connection ${connection}`}>{t(`conn.${connection}`)}</span>
          </header>
          <div className="body">
            <section className="content">
              {screen === 'panoramica' ? (
                <Overview day={day} kpi={kpi} pathway={pathway ?? null} />
              ) : screen === 'mappa' ? (
                <MapScreen day={day} pathwayId={pathwayId} alert={alarm} />
              ) : screen === 'percorsi' ? (
                <Flows day={day} pathwayId={pathwayId} />
              ) : (
                <p className="placeholder">{t('placeholder.screen', { screen: t(`nav.${screen}` as Key) })}</p>
              )}
            </section>
            <ActivityFeed messages={feed} />
          </div>
        </main>
      </div>
    )
  }
  return <LangContext value={lang}>{content}</LangContext>
}
