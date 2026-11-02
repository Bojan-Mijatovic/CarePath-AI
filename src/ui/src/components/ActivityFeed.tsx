import { useState } from 'react'
import { type Action, send, useApi } from '../lib/api'
import { agentName, label, type Translator, useLang } from '../lib/i18n'
import type { StreamMessage } from '../lib/stream'

type FeedMessage = Exclude<StreamMessage, { type: 'tick' }>
const BACKFILL = 10 // as many actions as a tick pushes (C32)
const ORDER: Record<string, number> = { capacity_proposal: 0, reschedule: 1, notify_mmg: 2, call_task: 3, reminder: 4 }

/** The tools or the rules behind an action (SPEC §7.1 `evidence`), in a few words. */
function evidence(t: Translator, items: Record<string, unknown>[]): string {
  const names = items.map((e) =>
    typeof e.tool === 'string'
      ? e.tool
      : typeof e.whatif === 'string'
        ? t('feed.whatif')
        : typeof e.rule === 'string'
          ? t('feed.rule', { id: e.rule })
          : typeof e.step === 'string'
            ? t('feed.deadline', { id: e.step })
            : t('feed.openDays', { days: String(e.open_days ?? '') }),
  )
  return [...new Set(names)].join(' · ')
}

/** The "Attività agenti · live" side panel (delivery plan steps 1.25 and 2.29, D45): what the agents do, from
 * /api/stream. An action shows its type, its agent, whether it ran on its own, waits for the manager or was
 * undone, its rationale and its evidence; an executed one can be undone (SPEC §7.3: the action is marked
 * undone in the audit log; the compensating event in the simulation is not built). After a jump or a
 * reconnect the stream has nothing of the day yet, so the panel reads the day's actions from the API. */
export default function ActivityFeed({ messages, day }: { messages: FeedMessage[]; day: number | null }) {
  const { lang, t } = useLang()
  const [busy, setBusy] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const live = messages.some((m) => m.day === day)
  const { data: today } = useApi<Action[]>(day !== null && !live ? `/api/actions?day=${day}` : null, day)
  const backfill: FeedMessage[] = live
    ? []
    : [...(today ?? [])]
        .sort((a, b) => Number(b.status === 'proposed') - Number(a.status === 'proposed') || (ORDER[a.type] ?? 9) - (ORDER[b.type] ?? 9))
        .slice(0, BACKFILL)
        .map((a) => ({ type: 'action', scenario: 0, day: day ?? a.created_day, payload: a }))
  const items = live ? messages : [...backfill, ...messages]

  const undo = (id: string) => {
    setBusy(id)
    setFailed(null)
    send('POST', `/api/actions/${id}/undo`) // the changed action comes back on the stream
      .catch(() => setFailed(id))
      .finally(() => setBusy(null))
  }

  return (
    <aside className="feed" aria-labelledby="h-feed">
      <h2 id="h-feed">
        <span className="live-dot" aria-hidden="true" />
        {t('feed.title')}
      </h2>
      {items.length === 0 && <p className="placeholder">{t('feed.empty')}</p>}
      <ol className="feed-items">
        {items.map((m, i) => {
          let head: string
          let body: string
          let extra: string | null = null
          let waiting = false
          let action: Action | null = null
          if (m.type === 'action') {
            action = m.payload
            waiting = action.status === 'proposed'
            const status =
              action.status === 'executed'
                ? t('feed.level', { level: action.autonomy_level })
                : label(t, 'feed.status', action.status)
            head = `${agentName(action.agent)} · ${label(t, 'action', action.type)} · ${status}`
            body = action.patient_id ? `${action.patient_id}: ${action.rationale[lang]}` : action.rationale[lang]
            extra = action.evidence.length ? t('feed.evidence', { list: evidence(t, action.evidence) }) : null
          } else if (m.type === 'alert') {
            head = `Monitoring · ${t(m.payload.level === 'regional' ? 'feed.alertRegional' : 'feed.alertPatient')}`
            body = m.payload.text[lang]
          } else if (m.type === 'report') {
            head = `Reporter · ${m.payload.title[lang]}`
            body = t('feed.report', { from: m.payload.from_day, to: m.day })
          } else {
            head = `Investigator · ${t('feed.step', { step: m.payload.step })}`
            body = `${m.payload.tool}: ${m.payload.result_summary[lang]}`
          }
          const undone = action?.status === 'undone'
          return (
            <li
              key={action ? action.action_id : `${m.day}-${m.type}-${i}`}
              className={waiting || m.type === 'alert' ? 'feed-item warn' : undone ? 'feed-item undone' : 'feed-item'}
            >
              <span className="feed-dot" aria-hidden="true" />
              <div>
                <div className="feed-head">{head}</div>
                <div className="feed-body">{body}</div>
                {extra && <div className="feed-evidence">{extra}</div>}
                <div className="feed-day">
                  {t('feed.day', { day: m.day })}
                  {action?.status === 'executed' && (
                    <button
                      type="button"
                      className="feed-undo"
                      disabled={busy !== null}
                      onClick={() => undo(action.action_id)}
                    >
                      {t('feed.undo')}
                    </button>
                  )}
                  {failed === action?.action_id && <span className="feed-failed">{t('feed.undoFailed')}</span>}
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
