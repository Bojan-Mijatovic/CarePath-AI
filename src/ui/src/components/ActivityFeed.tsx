import { agentName, useLang } from '../lib/i18n'
import type { StreamMessage } from '../lib/stream'

type FeedMessage = Exclude<StreamMessage, { type: 'tick' }>

/** The "Attività agenti · live" side panel: actions, alerts and investigation steps from /api/stream. */
export default function ActivityFeed({ messages }: { messages: FeedMessage[] }) {
  const { lang, t } = useLang()
  return (
    <aside className="feed" aria-labelledby="h-feed">
      <h2 id="h-feed">
        <span className="live-dot" aria-hidden="true" />
        {t('feed.title')}
      </h2>
      {messages.length === 0 && <p className="placeholder">{t('feed.empty')}</p>}
      <ol className="feed-items">
        {messages.map((m, i) => {
          let head: string
          let body: string
          let waiting = false
          if (m.type === 'action') {
            waiting = m.payload.status === 'proposed'
            head = `${agentName(m.payload.agent)} · ${waiting ? t('feed.waiting') : t('feed.level', { level: m.payload.autonomy_level })}`
            body = m.payload.rationale[lang]
          } else if (m.type === 'alert') {
            head = `Monitoring · ${t(m.payload.level === 'regional' ? 'feed.alertRegional' : 'feed.alertPatient')}`
            body = m.payload.text[lang]
          } else {
            head = `Investigator · ${t('feed.step', { step: m.payload.step })}`
            body = `${m.payload.tool}: ${m.payload.result_summary[lang]}`
          }
          return (
            <li key={`${m.day}-${m.type}-${i}`} className={waiting || m.type === 'alert' ? 'feed-item warn' : 'feed-item'}>
              <span className="feed-dot" aria-hidden="true" />
              <div>
                <div className="feed-head">{head}</div>
                <div className="feed-body">{body}</div>
                <div className="feed-day">{t('feed.day', { day: m.day })}</div>
              </div>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
