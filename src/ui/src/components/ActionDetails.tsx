import { useState } from 'react'
import { type Action, type CapacityRow, type Pathway, send, useApi } from '../lib/api'
import { patientsOf, proof } from '../lib/evidence'
import { agentName, formatNumber, label, useLang } from '../lib/i18n'
import Origin from './Origin'

const SHOWN = 12 // patients listed before "show all"

/** One action in full on the Agents page (D67, proposed; the mockup's "Details"): what it does, why (its
 * rationale, code's template or the model's sentence), the evidence as the audit log keeps it, the patients it
 * reaches, and the decision: approve or reject a proposal, undo an executed one (SPEC §7.3). Every field is the
 * action's own row (SPEC §7.1); nothing is computed here. */
export default function ActionDetails({ action, pathway, onClose }: { action: Action; pathway: Pathway | null; onClose: () => void }) {
  const { lang, t } = useLang()
  // facility and service names, from the facilities of the action's service and the pathway file (AC17)
  const service = typeof action.payload.service === 'string' ? action.payload.service : null
  const { data: sites } = useApi<CapacityRow[]>(service ? `/api/capacity?service=${service}` : null)
  const name = (id: unknown) => sites?.find((r) => r.facility_id === id)?.name ?? String(id)
  const serviceName = pathway?.steps.find((s) => s.service === service)?.label[lang] ?? service ?? ''
  const [row, setRow] = useState(action)
  const [all, setAll] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (row.action_id !== action.action_id) {
    // another action opened: start from its row (React: state from the last render)
    setRow(action)
    setAll(false)
    setError(null)
  }
  const patients = patientsOf(row)
  const shown = all ? patients : patients.slice(0, SHOWN)
  const p = row.payload
  const where =
    typeof p.from_facility === 'string' && typeof p.to_facility === 'string'
      ? t('details.move', { from: name(p.from_facility), to: name(p.to_facility), service: serviceName })
      : typeof p.facility === 'string'
        ? String(p.facility)
        : null
  const decide = (decision: 'approve' | 'reject' | 'undo') => {
    setBusy(true)
    setError(null)
    send<{ action_id: string; status: Action['status'] }>('POST', `/api/actions/${row.action_id}/${decision}`)
      .then((r) => setRow({ ...row, status: r.status, decided_by: row.decided_by ?? 'manager' }))
      .catch(() => setError(t('approvals.failed')))
      .finally(() => setBusy(false))
  }

  return (
    <section className="panel details" aria-labelledby="h-details" id="action-details">
      <div className="details-head">
        <h2 id="h-details">{label(t, 'action', row.type)}</h2>
        <button type="button" onClick={onClose} aria-label={t('details.close')}>
          ×
        </button>
      </div>
      <div className="card-sub">
        {t('details.meta', { agent: agentName(row.agent), level: row.autonomy_level, day: row.created_day, id: row.action_id })}
      </div>

      <h3>{t('details.what')}</h3>
      <p>
        {label(t, 'action', row.type)}
        {where && ` · ${where}`}
        {patients.length > 0 && ` · ${t('details.patientsCount', { n: formatNumber(lang, patients.length) })}`}
      </p>

      <h3>
        {t('details.why')}
        <Origin kind={p.wording === 'model' ? 'model' : 'code'} />
      </h3>
      <p>{row.rationale[lang]}</p>

      {row.evidence.length > 0 && (
        <>
          <h3>{t('details.evidence')}</h3>
          <ul className="details-list">
            {row.evidence.map((e, k) => (
              <li key={k}>
                <code>{proof(t, e)}</code>
              </li>
            ))}
          </ul>
        </>
      )}

      {patients.length > 0 && (
        <>
          <h3>{t('details.patients')}</h3>
          <p className="details-patients">{shown.join(' · ')}</p>
          {patients.length > SHOWN && (
            <button type="button" onClick={() => setAll(!all)}>
              {all ? t('details.fewer') : t('details.all', { n: formatNumber(lang, patients.length) })}
            </button>
          )}
        </>
      )}

      <h3>
        {t('details.decision')}
        <Origin kind="person" />
      </h3>
      <p>
        {t('details.status', {
          status: label(t, 'feed.status', row.status),
          level: row.autonomy_level,
        })}
        {row.executed_day !== null && ` · ${t('details.executed', { day: row.executed_day })}`}
        {row.decided_by && ` · ${t('details.by', { who: row.decided_by })}`}
      </p>
      {error && <p className="placeholder">{error}</p>}
      <div className="details-actions">
        {row.status === 'proposed' && (
          <>
            <button type="button" className="primary" disabled={busy} onClick={() => decide('approve')}>
              {t('approvals.approve')}
            </button>
            <button type="button" disabled={busy} onClick={() => decide('reject')}>
              {t('approvals.reject')}
            </button>
          </>
        )}
        {row.status === 'executed' && (
          <button
            type="button"
            disabled={busy}
            title={t(row.type === 'reschedule' ? 'feed.undoMove' : row.type === 'capacity_proposal' ? 'feed.undoPurchase' : 'feed.undoMark')}
            onClick={() => decide('undo')}
          >
            {t('feed.undo')}
          </button>
        )}
      </div>
    </section>
  )
}
