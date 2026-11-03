import type { Screen } from '../App'

export type Step = {
  /** guide.<key>.title, guide.<key>.text and guide.<key>.behind */
  key: string
  scenario: number
  screen: Screen
  /** The clock: at ×1 the server stops it on the alarm (D63); at either speed the guide stops it on `until` */
  run?: { speed: 1 | 4; until: number }
  /** What the operator clicks here (data-spot); the guide outlines it and never clicks it (D66) */
  spots?: string[]
  /** Where the audience should look while nothing is clicked (data-spot): outlined, never scrolled to */
  watch?: string[]
  optional?: boolean
}

/** demo/SCRIPT.md, stage by stage, with its days (D66). */
export const STEPS: readonly Step[] = [
  { key: 'maria', scenario: 2, screen: 'storia' },
  { key: 'overview', scenario: 2, screen: 'panoramica', watch: ['feed'] },
  { key: 'map', scenario: 2, screen: 'mappa', run: { speed: 1, until: 33 }, spots: ['alarm'], watch: ['feed'] },
  { key: 'ask', scenario: 2, screen: 'chiedi' },
  { key: 'approve', scenario: 2, screen: 'panoramica', spots: ['approve-capacity_proposal', 'approve-notify_mmg'] },
  { key: 'autonomy', scenario: 2, screen: 'confronto', spots: ['autonomy-reschedule-3'] },
  { key: 'fast', scenario: 2, screen: 'confronto', run: { speed: 4, until: 62 } },
  { key: 'lever', scenario: 2, screen: 'confronto', spots: ['compare-lever'] },
  { key: 'whatif', scenario: 2, screen: 'whatif', spots: ['whatif'] },
  { key: 'calls', scenario: 2, screen: 'chiamate' },
  { key: 'patient', scenario: 2, screen: 'pazienti', spots: ['patient-arm'] },
  { key: 'bed', scenario: 2, screen: 'letti', spots: ['bed-request'], optional: true },
  { key: 'other', scenario: 1, screen: 'chiedi' },
  { key: 'approveOther', scenario: 1, screen: 'panoramica', spots: ['approve-capacity_proposal'] },
  { key: 'fastOther', scenario: 1, screen: 'confronto', run: { speed: 4, until: 43 }, spots: ['compare-lever'] },
  { key: 'third', scenario: 3, screen: 'mappa', run: { speed: 1, until: 29 }, spots: ['alarm'], watch: ['feed'] },
  { key: 'ask', scenario: 3, screen: 'chiedi' },
  { key: 'approveOther', scenario: 3, screen: 'panoramica', spots: ['approve-capacity_proposal'] },
  { key: 'fastOther', scenario: 3, screen: 'confronto', run: { speed: 4, until: 49 }, spots: ['compare-lever'] },
  { key: 'reveal', scenario: 3, screen: 'rivelazione' },
]
