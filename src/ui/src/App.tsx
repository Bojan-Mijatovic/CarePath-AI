import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import ActionDetails from './components/ActionDetails'
import ActivityFeed from './components/ActivityFeed'
import Autonomy from './components/Autonomy'
import Controls from './components/Controls'
import LangSwitch from './components/LangSwitch'
import { type Action, type Investigation, type Kpi, type KpiRow, type Pathway, type SimStatus, useApi } from './lib/api'
import { formatNumber, type Key, type Lang, LangContext, translator } from './lib/i18n'
import { type LeverRun, type StreamMessage, useStream } from './lib/stream'
import Ask from './screens/Ask'
import Beds, { type BedTarget } from './screens/Beds'
import Compare from './screens/Compare'
import Calls from './screens/Calls'
import DemoBar from './components/DemoBar'
import Reveal from './screens/Reveal'
import Flows from './screens/Flows'
import Hospitals from './screens/Hospitals'
import Dashboard, { type Alarm } from './screens/Dashboard'
import { type RegionalAlert } from './screens/MapScreen'
import MariaStory from './screens/MariaStory'
import { Approvals, LatestReport } from './screens/Overview'
import Patient from './screens/Patient'
import Situations from './screens/Situations'
import WhatIf from './screens/WhatIf'

// Six pages by domain as in the console mockup (D67, proposed): a dark header picks the situation and runs the
// clock, the pages are tabs, a line under them says which situation is on screen. No guide bar: the lead asked for
// the console without it (13 Nov 2026); the operator's hidden demo bar stays. Maria's story and the reveal are
// still full screen, from their hash only.
const PAGES = ['dashboard', 'pazienti', 'ospedali', 'agenti', 'analisi', 'impostazioni'] as const
export type Screen = 'storia' | 'rivelazione' | (typeof PAGES)[number]
const ALL: readonly Screen[] = ['storia', 'rivelazione', ...PAGES]
const FEED_SIZE = 30
const LANG_KEY = 'carepath.lang'

function screenFromHash(): Screen {
  const id = location.hash.slice(1)
  return (ALL as readonly string[]).includes(id) ? (id as Screen) : 'dashboard'
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
  const [detail, setDetail] = useState<Action | null>(null) // the action open in full on the Agents page
  const [viewDay, setViewDay] = useState<number | null>(null) // a past day looked back at, read only; null: today
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
  const lastScenario = useRef<number | null>(null)
  const onMessage = useCallback((msg: StreamMessage) => {
    if (msg.type === 'tick') {
      // A day before the last one means the server started over (reset, jump back, reconnect).
      if (lastDay.current !== null && msg.day < lastDay.current) {
        setFeed([])
        setAlarm(null)
      }
      lastDay.current = msg.day
      setDay(msg.day)
      if (lastScenario.current !== msg.scenario) {
        setViewDay(null) // another situation: back to its today
        setAlarm(null) // and its own alarm, if it has one (from its investigation, below)
        setFeed([])
      }
      lastScenario.current = msg.scenario
      setScenario(msg.scenario)
      if (msg.payload.speed) setViewDay(null) // the clock runs: the screens follow today again
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
  // Looking back (D67, proposed): a past day of the situation on screen, read only, from what the runs keep by day
  const past = viewDay !== null && day !== null && viewDay < day ? viewDay : null
  const shown = past ?? day
  const { data: kpiRows } = useApi<KpiRow[]>(past !== null && pathwayId ? `/api/kpi?level=ats&pathway_id=${pathwayId}` : null, past)
  const shownKpi = past === null ? kpi : (kpiRows?.find((r) => r.day === past) ?? null)
  const look = (d: number) => setViewDay(day === null || d >= day ? null : Math.max(d, 0))
  // The wait alarm of the situation on screen: the stream's, or after a reload or a switch its investigation's
  const { data: investigations } = useApi<Investigation[]>(scenario !== null ? '/api/investigations' : null, `${scenario}-${day}`)
  const investigated = (investigations ?? []).find((i) => i.alert_id !== null && day !== null && i.day <= day)
  const shownAlarm: Alarm | null = alarm
    ? { day: alarm.day, facility_id: alarm.payload.facility_id, text: alarm.payload.text[lang] }
    : investigated
      ? { day: investigated.day, facility_id: null, text: investigated.question[lang] }
      : null
  const go = useCallback((next: Screen) => {
    window.history.pushState(null, '', `#${next}`) // pushState fires no hashchange, so set the screen too
    setScreen(next)
    window.scrollTo(0, 0) // a new screen from its top, not where the last one was scrolled to
  }, [])
  const follow = go
  const onStatus = useCallback((status: SimStatus) => setSpeed(status.speed), [])
  // An action opened from the approvals or the feed, on any page, is shown in full on the Agents page
  const openAction = (a: Action) => {
    setDetail(a)
    go('agenti')
    window.requestAnimationFrame(() => document.getElementById('action-details')?.scrollIntoView({ behavior: 'smooth' }))
  }
  const restart = useCallback(() => setViewDay(null), [])

  let content
  const langSwitch = <LangSwitch onChange={setLang} />
  // The runs stand paused on day 23 (D21); the operator starts the clock on Mappa (demo step 4).
  if (screen === 'storia') content = <MariaStory onStart={() => follow('dashboard')} langSwitch={langSwitch} />
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
    const pending = kpi?.actions_pending ?? 0
    content = (
      <div className="app">
        <header className="header">
          <div className="wrap">
            <div className="brand">
              <strong>CarePath AI</strong>
              <span>
                {pathway && kpi
                  ? t('top.subtitle', { pathway: pathway.label[lang], patients: formatNumber(lang, kpi.patients) })
                  : t('brand.ats')}
                {' · '}
                {t('top.synthetic')}
              </span>
            </div>
            <Controls scenario={scenario} speed={speed} day={day} past={past} onStatus={onStatus} look={look} />
            <div className="header-side">
              <LangSwitch onChange={setLang} />
              <span className={`connection-dot ${connection}`} role="status" title={t(`conn.${connection}`)} aria-label={t(`conn.${connection}`)} />
            </div>
          </div>
        </header>
        <nav className="tabs" aria-label={t('nav.menu')}>
          <div className="wrap">
            {PAGES.map((name) => (
              <button key={name} type="button" aria-current={name === screen ? 'page' : undefined} onClick={() => follow(name)}>
                {t(`nav.${name}` as Key)}
                {name === 'agenti' && pending > 0 && <span className="badge">{pending}</span>}
                {name === 'ospedali' && shownAlarm && <span className="badge warn">!</span>}
              </button>
            ))}
          </div>
        </nav>
        {scenario !== null && (
          <div className="wrap">
            <div className={`context${shownAlarm ? ' alarm' : ''}`}>
              <strong>{t(`situation.${scenario}.name` as Key)}</strong>
              <span>{t(`situation.${scenario}.desc` as Key)}</span>
              {shownAlarm && (
                <button type="button" onClick={() => follow('ospedali')}>
                  {t('context.alarm', { day: shownAlarm.day })}
                </button>
              )}
            </div>
          </div>
        )}
        {past !== null && (
          <div className="wrap">
            <div className="lookback-banner" role="status">
              {t('lookback.banner', { day: past, today: day ?? '' })}
            </div>
          </div>
        )}
        <main className="wrap page">
          <h1>{t(`nav.${screen}` as Key)}</h1>
          {screen === 'dashboard' ? (
            <Dashboard
              day={day}
              past={past}
              scenario={scenario}
              kpi={shownKpi}
              pathway={pathway ?? null}
              alarm={shownAlarm}
              leverRun={leverRun}
              onAlarm={() => follow('ospedali')}
              onAgents={() => follow('agenti')}
            />
          ) : screen === 'pazienti' ? (
            <>
              <div className="row patients">
                <div className="col-2 maria">
              <Patient
                day={day}
                scenario={scenario}
                pathway={pathway ?? null}
                onAdmission={(target) => {
                  setBedTarget(target)
                  window.requestAnimationFrame(() => document.getElementById('beds')?.scrollIntoView({ behavior: 'smooth' }))
                }}
              />
                </div>
                <div className="col-3">
                  <Calls key={past ?? 'today'} day={shown} />
                </div>
              </div>
              <div id="beds">
                <Beds
                  key={bedTarget ? `${bedTarget.run}-${bedTarget.patientId}-${bedTarget.day}` : `s${scenario}`}
                  day={day}
                  scenario={scenario}
                  target={bedTarget?.run.startsWith(`s${scenario}_`) ? bedTarget : null}
                />
              </div>
            </>
          ) : screen === 'ospedali' ? (
            <>
              <Hospitals day={shown} scenario={scenario} pathway={pathway ?? null} />
              <Ask day={day} />
            </>
          ) : screen === 'agenti' ? (
            <>
              <div className="row agents">
                <div className="col-left">
                  <Approvals day={day} onOpen={openAction} />
                  <ActivityFeed messages={feed} day={shown} past={past !== null} onOpen={openAction} openId={detail?.action_id ?? null} />
                </div>
                <div className="col-right">
                  {detail ? (
                    <ActionDetails action={detail} pathway={pathway ?? null} onClose={() => setDetail(null)} />
                  ) : (
                    <section className="panel details" aria-labelledby="h-details" id="action-details">
                      <h2 id="h-details">{t('agents.detailsTitle')}</h2>
                      <p className="placeholder">{t('agents.detailsHint')}</p>
                    </section>
                  )}
                </div>
              </div>
              <LatestReport day={day} />
            </>
          ) : screen === 'analisi' ? (
            <>
              <Compare day={day} scenario={scenario} pathway={pathway ?? null} leverRun={leverRun} viewDay={past} />
              <WhatIf scenario={scenario} pathway={pathway ?? null} />
              <Situations day={day} leverDay={leverRun?.day ?? null} pathway={pathway ?? null} />
              <Flows day={day} pathwayId={pathwayId} />
            </>
          ) : (
            <>
              <Autonomy day={day} />
              <div className="panels">
                <section className="panel" aria-labelledby="h-language">
                  <h2 id="h-language">{t('top.language')}</h2>
                  <LangSwitch onChange={setLang} />
                </section>
              </div>
            </>
          )}
        </main>
      </div>
    )
  }
  return (
    <LangContext value={lang}>
      {content}
      <DemoBar day={day} speed={speed} onReveal={() => go('rivelazione')} onStatus={onStatus} onReset={restart} />
    </LangContext>
  )
}
