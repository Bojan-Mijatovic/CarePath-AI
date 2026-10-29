import type { Patient360, TimelineEvent } from './api'
import { type Bilingual, formatNumber, isKey, type Key, type Lang, type Translator } from './i18n'

/** Maria's story without CarePath (demo step 1), computed from her baseline-arm timeline. A scripted
 * narrative about one patient, so it is outside the AC17 console check; drug names still come from the
 * pathway file. */

export type Line = { day: number; key: Key; vars?: Record<string, string | number>; alarm?: boolean }

const WEIGHT_GAIN_KG = 2 // the pathway rule weight_gain_kg_3d >= 2 (spec/pathways/hf_lombardia_v1.json)
const DAYS_WITHOUT_DRUG = 30 // told once the supply has been out for more than this

function isEvent(item: Patient360['timeline'][number]): item is TimelineEvent {
  return item.kind === 'event'
}

/** The moments the story tells, each computed from her events: discharge, the drug running out, the
 * weight rising, the readmission. */
export function storyLines(p: Patient360, lang: Lang, drugNames: Record<string, Bilingual>): Line[] {
  const events = p.timeline.filter(isEvent)
  const discharge = events.find((e) => e.event_type === 'DISCHARGE' && e.day >= 0)
  if (!discharge) return []
  const lines: Line[] = [{ day: discharge.day, key: 'maria.discharge', vars: { facility: discharge.facility_name ?? '' } }]

  const dispenses = events.filter((e) => e.event_type === 'DISPENSE')
  const last = dispenses.filter((e) => e.day <= discharge.day).at(-1)
  if (last?.value) {
    const supplyEnd = last.day + last.value
    const day = supplyEnd + DAYS_WITHOUT_DRUG + 1
    const next = dispenses.find((e) => e.day > last.day)
    if (!next || next.day > day) {
      const drug = drugNames[last.code ?? '']?.[lang] ?? last.code ?? ''
      lines.push({ day, key: 'maria.noDrug', vars: { days: day - supplyEnd, drug } })
    }
  }

  const readings = events.filter((e) => e.event_type === 'TELEMON_READING' && e.value !== null && e.day > discharge.day)
  const weight = new Map(readings.map((e) => [e.day, e.value as number]))
  const rising = readings.find((e) => (e.value as number) - (weight.get(e.day - 3) ?? Infinity) >= WEIGHT_GAIN_KG)
  if (rising) {
    const kg = (rising.value as number) - (weight.get(rising.day - 3) as number)
    lines.push({ day: rising.day, key: 'maria.weight', vars: { kg: formatNumber(lang, kg, 1) } })
  }

  const readmission = events.find((e) => e.event_type === 'ADMISSION' && e.value === 1 && e.day > discharge.day)
  if (readmission) lines.push({ day: readmission.day, key: 'maria.readmitted', alarm: true })
  return lines.sort((a, b) => a.day - b.day)
}

/** "Heart failure and type 2 diabetes" from patients.conditions. */
export function conditions(t: Translator, codes: string[]): string {
  const names = codes.map((c) => `condition.${c}`).filter(isKey).map((k) => t(k))
  return names.length > 1 ? `${names.slice(0, -1).join(', ')} ${t('and')} ${names.at(-1)}` : (names[0] ?? '')
}
