import { type Action, useApi } from '../lib/api'
import { label, type Key, useLang } from '../lib/i18n'
import type { StreamMessage } from '../lib/stream'

type FeedMessage = Exclude<StreamMessage, { type: 'tick' }>
const BACKFILL = 10 // as many actions as a tick pushes (C32)
const ORDER: Record<string, number> = { capacity_proposal: 0, reschedule: 1, notify_mmg: 2, call_task: 3, reminder: 4 }

/** The agents' activity of the day (delivery plan steps 1.25 and 2.29, D45), as in the console mockup: one row per
 * message from /api/stream, its type, its text and its state. A row with an action opens it in full on the right
 * (D67, proposed), where it can be approved, rejected or undone (SPEC §7.3). After a jump or a reconnect the stream
 * has nothing of the day yet, so the panel reads the day's actions from the API. */
export default function ActivityFeed({
  messages,
  day,
  past = false,
  onOpen,
  openId = null,
}: {
  messages: FeedMessage[]
  day: number | null
  /** `day` is a past day looked back at: only that day's actions, from the API */
  past?: boolean
  /** opens an action in full */
  onOpen?: (a: Action) => void
  /** the action open in full, marked in the list */
  openId?: string | null
}) {
  const { lang, t } = useLang()
  const live = !past && messages.some((m) => m.day === day)
  const { data: today } = useApi<Action[]>(day !== null && !live ? `/api/actions?day=${day}` : null, day)
  const backfill: FeedMessage[] = live
    ? []
    : [...(today ?? [])]
        .sort((a, b) => Number(b.status === 'proposed') - Number(a.status === 'proposed') || (ORDER[a.type] ?? 9) - (ORDER[b.type] ?? 9))
        .slice(0, BACKFILL)
        .map((a) => ({ type: 'action', scenario: 0, day: day ?? a.created_day, payload: a }))
  const items = live ? messages : past ? backfill : [...backfill, ...messages]

  return (
    <section className="panel feed inline" aria-labelledby="h-feed">
      <h2 id="h-feed">
        <span className="live-dot" aria-hidden="true" />
        {t('feed.title')}
        {day !== null && ` · ${t('feed.day', { day })}`}
      </h2>
      {items.length === 0 && <p className="placeholder">{t('feed.empty')}</p>}
      <ol className="feed-rows">
        {items.map((m, i) => {
          if (m.type === 'action') {
            const a = m.payload
            const status = a.status === 'executed' ? t('feed.level', { level: a.autonomy_level }) : label(t, 'feed.status', a.status)
            const text = a.patient_id ? `${a.patient_id}: ${a.rationale[lang]}` : a.rationale[lang]
            return (
              <li key={a.action_id}>
                <button
                  type="button"
                  className={`feed-row status-${a.status}`}
                  aria-pressed={openId === a.action_id}
                  title={t('details.open')}
                  onClick={() => onOpen?.(a)}
                >
                  <span className={`chip type-${a.type}`}>{label(t, 'action', a.type)}</span>
                  <span className="feed-text">{text}</span>
                  <span className="feed-status">{status}</span>
                </button>
              </li>
            )
          }
          const [kind, text] =
            m.type === 'alert'
              ? [t(m.payload.level === 'regional' ? 'feed.alertRegional' : 'feed.alertPatient'), m.payload.text[lang]]
              : m.type === 'report'
                ? ['Reporter', `${m.payload.title[lang]} · ${t('feed.report', { from: m.payload.from_day, to: m.day })}`]
                : [`Investigator · ${t('feed.step', { step: m.payload.step })}`, `${m.payload.tool}: ${m.payload.result_summary[lang]}`]
          return (
            <li key={`${m.day}-${m.type}-${i}`}>
              <div className={`feed-row kind-${m.type}`}>
                <span className={`chip kind-${m.type}`}>{kind}</span>
                <span className="feed-text">{text}</span>
                <span className="feed-status">{t(`feed.kind.${m.type}` as Key)}</span>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
