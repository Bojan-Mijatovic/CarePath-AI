import type { Action } from './api'
import type { Translator } from './i18n'

/** The tools or the rules behind an action (SPEC §7.1 `evidence`), in a few words. */
export function evidence(t: Translator, items: Record<string, unknown>[]): string {
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

/** One evidence item in full, as the audit log keeps it: the tool call with its arguments, the rule or deadline,
 * or the what-if run, with the run and day. The tool's result is not in the evidence (SPEC §7.1). */
export function proof(t: Translator, e: Record<string, unknown>): string {
  const at = typeof e.run_id === 'string' ? ` · ${t('feed.proofAt', { run: e.run_id, day: String(e.day ?? '–') })}` : ''
  const value = (v: unknown) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))
  if (typeof e.tool === 'string') {
    const args = Object.entries((e.args ?? {}) as Record<string, unknown>).map(([k, v]) => `${k}=${value(v)}`)
    return `${e.tool}(${args.join(', ')})${at}`
  }
  if (typeof e.whatif === 'string') return `${t('feed.whatif')}: ${e.whatif} · ${value(e.levers)} · ${t('feed.proofMonths', { months: String(e.months ?? '–') })}${at}`
  return `${evidence(t, [e])}${at}`
}

/** The patients an action reaches: its own, or the ids of its payload's list (an MMG notice lists objects). */
export function patientsOf(a: Action): string[] {
  const listed = Array.isArray(a.payload.patients) ? (a.payload.patients as unknown[]) : []
  const ids = listed.map((p) => (typeof p === 'string' ? p : String((p as { patient_id?: unknown }).patient_id ?? '')))
  return a.patient_id ? [a.patient_id, ...ids] : ids
}
