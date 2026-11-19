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

/** demo/SCRIPT.md, stage by stage, with its days (D66). The three situations of D67 (proposed), in the order of
 * engine.tick.DEMO_ORDER: the normal one (scenario 0), an unplanned closure (4), an investment (3). The days are
 * measured on seed 42: scenario 4's wait alarm opens on day 36, scenario 3's on day 29. */
export const STEPS: readonly Step[] = [
  { key: 'maria', scenario: 0, screen: 'storia' },
  { key: 'overview', scenario: 0, screen: 'dashboard', watch: ['feed'] },
  { key: 'calls', scenario: 0, screen: 'pazienti' },
  { key: 'fast', scenario: 0, screen: 'analisi', run: { speed: 4, until: 60 } },
  { key: 'patient', scenario: 0, screen: 'pazienti', spots: ['patient-arm'] },
  { key: 'bed', scenario: 0, screen: 'pazienti', spots: ['bed-request'], optional: true },
  { key: 'closure', scenario: 4, screen: 'dashboard', run: { speed: 1, until: 36 }, spots: ['alarm'], watch: ['feed'] },
  { key: 'ask', scenario: 4, screen: 'ospedali' },
  { key: 'approveMove', scenario: 4, screen: 'agenti', spots: ['approve-reschedule'] },
  { key: 'fastClosure', scenario: 4, screen: 'analisi', run: { speed: 4, until: 60 } },
  { key: 'investment', scenario: 3, screen: 'dashboard', run: { speed: 1, until: 29 }, spots: ['alarm'], watch: ['feed'] },
  { key: 'ask', scenario: 3, screen: 'ospedali' },
  { key: 'approveOther', scenario: 3, screen: 'agenti', spots: ['approve-capacity_proposal'] },
  { key: 'fastOther', scenario: 3, screen: 'analisi', run: { speed: 4, until: 60 }, spots: ['compare-lever'] },
  { key: 'whatif', scenario: 3, screen: 'analisi', spots: ['whatif'] },
  // the closing comparison: nothing to click, a spot so the guide scrolls to it
  { key: 'situations', scenario: 3, screen: 'analisi', spots: ['situations'] },
]
