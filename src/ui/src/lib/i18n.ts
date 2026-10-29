import { createContext, useContext } from 'react'

/** Every string a user sees, in Italian and English; Italian by default (delivery plan D30). */
export type Lang = 'it' | 'en'
export type Bilingual = { it: string; en: string }

const STRINGS = {
  'nav.panoramica': { it: 'Panoramica', en: 'Overview' },
  'nav.mappa': { it: 'Mappa', en: 'Map' },
  'nav.chiedi': { it: 'Chiedi', en: 'Ask' },
  'nav.confronto': { it: 'Confronto', en: 'Compare' },
  'nav.whatif': { it: 'What-if', en: 'What-if' },
  'nav.percorsi': { it: 'Percorsi', en: 'Pathways' },
  'nav.chiamate': { it: 'Chiamate', en: 'Calls' },
  'nav.letti': { it: 'Posti letto', en: 'Beds' },
  'nav.pazienti': { it: 'Pazienti', en: 'Patients' },
  'nav.storia': { it: 'Storia di Maria', en: "Maria's story" },
  'nav.footer': { it: 'Modelli locali · nessun dato reale', en: 'Local models · no real data' },
  'brand.ats': { it: 'ATS della Val Padana', en: 'ATS della Val Padana' },
  'top.day': { it: 'Giorno {day}', en: 'Day {day}' },
  'top.speed': { it: 'Velocità ×{speed}', en: 'Speed ×{speed}' },
  'top.synthetic': { it: 'Dati sintetici', en: 'Synthetic data' },
  'top.language': { it: 'Lingua', en: 'Language' },
  'conn.connecting': { it: 'connessione…', en: 'connecting…' },
  'conn.open': { it: 'connesso', en: 'connected' },
  'conn.closed': { it: 'riconnessione…', en: 'reconnecting…' },
  'placeholder.screen': { it: 'Schermata “{screen}”: in arrivo nella Fase 2.', en: 'Screen “{screen}”: coming in Phase 2.' },
  loading: { it: 'Caricamento…', en: 'Loading…' },
  'error.load': { it: 'Dati non disponibili: {detail}', en: 'Data not available: {detail}' },

  'maria.pill': { it: 'Paziente sintetica', en: 'Synthetic patient' },
  'maria.kicker': { it: 'La signora Maria', en: 'Mrs Maria' },
  'maria.headline': {
    it: 'Ogni paziente cronico ha un PAI. Ma chi controlla ogni giorno che venga seguito?',
    en: 'Every chronic patient has a care plan (PAI). But who checks every day that it is followed?',
  },
  'maria.alone': {
    it: '{age} anni, vive sola, a {km} km dall’ospedale. {conditions}. Ha un piano di cura, ma nessuno vede ogni giorno se lo segue.',
    en: '{age}, lives alone, {km} km from the hospital. {conditions}. She has a care plan, but nobody sees every day whether she follows it.',
  },
  'maria.notAlone': {
    it: '{age} anni, a {km} km dall’ospedale. {conditions}. Ha un piano di cura, ma nessuno vede ogni giorno se lo segue.',
    en: '{age}, {km} km from the hospital. {conditions}. She has a care plan, but nobody sees every day whether she follows it.',
  },
  'maria.start': { it: 'Avvia la simulazione', en: 'Start the simulation' },
  'maria.without': { it: 'Senza un sistema che la segue', en: 'Without a system that follows her' },
  'maria.dayByDay': { it: 'Il percorso di Maria, giorno per giorno', en: "Maria's path, day by day" },
  'maria.discharge': { it: 'Dimessa dall’ospedale ({facility})', en: 'Discharged from hospital ({facility})' },
  'maria.noDrug': {
    it: 'Da {days} giorni senza {drug}. Nessuno se ne accorge.',
    en: '{days} days without {drug}. Nobody notices.',
  },
  'maria.weight': {
    it: 'Il peso sale di {kg} kg in 3 giorni: le letture arrivano, ma nessuno le guarda.',
    en: 'Weight up {kg} kg in 3 days: the readings arrive, but nobody looks at them.',
  },
  'maria.readmitted': { it: 'Torna in ospedale. Riammissione.', en: 'Back in hospital. Readmitted.' },
  'condition.HF': { it: 'Scompenso cardiaco', en: 'Heart failure' },
  'condition.T2D': { it: 'diabete di tipo 2', en: 'type 2 diabetes' },
  and: { it: 'e', en: 'and' },

  'busta.pill': { it: 'La simulazione è già in corso', en: 'The simulation is already running' },
  'busta.kicker': { it: 'Scegliete voi', en: 'You choose' },
  'busta.headline': { it: 'Scegliete voi dove sono i problemi.', en: 'You choose where the problems are.' },
  'busta.body': {
    it: 'Abbiamo preparato tre versioni dello stesso territorio. In ognuna i problemi sono in un posto diverso. Scegliete una busta e tenetela chiusa: gli agenti non sanno quale avete scelto.',
    en: 'We prepared three versions of the same territory. In each, the problems are somewhere else. Pick an envelope and keep it sealed: the agents do not know which one you chose.',
  },
  'busta.sealed': { it: 'Busta chiusa', en: 'Sealed envelope' },
  'busta.label': { it: 'Busta {n}', en: 'Envelope {n}' },
  'busta.footer': {
    it: 'In ogni busta: un ospedale con un collo di bottiglia, i comuni a rischio e un gruppo di MMG con bassa aderenza alla terapia. La apriamo alla fine.',
    en: 'In each envelope: a hospital with a bottleneck, the comuni at risk and an MMG group with low adherence to therapy. We open it at the end.',
  },

  'overview.intro': {
    it: 'Mentre parlavamo, gli agenti hanno elaborato {days} giorni di dati per {patients} pazienti.',
    en: 'While we were talking, the agents processed {days} days of data for {patients} patients.',
  },
  'overview.waiting': { it: 'In attesa del primo giorno della simulazione…', en: 'Waiting for the first simulated day…' },
  'card.patients': { it: 'Pazienti seguiti', en: 'Patients followed' },
  'card.patientsSub': { it: 'PDTA: {pathway}', en: 'Pathway (PDTA): {pathway}' },
  'card.onTrack': { it: 'In linea con il PAI', en: 'On track with the PAI' },
  'card.onTrackSub': { it: '{overdue} in ritardo · {dropped} fuori percorso', en: '{overdue} overdue · {dropped} off the pathway' },
  'card.actions': { it: 'Azioni degli agenti', en: 'Agent actions' },
  'card.actionsSub': { it: 'dall’inizio della simulazione', en: 'since the simulation started' },
  'card.pending': { it: 'In attesa di approvazione', en: 'Awaiting approval' },
  'card.pendingSub': { it: 'decidete voi', en: 'you decide' },
  'approvals.title': { it: 'In attesa di approvazione', en: 'Awaiting approval' },
  'approvals.empty': { it: 'Nessuna azione in attesa.', en: 'No action is waiting.' },
  'approvals.meta': { it: '{agent} · livello {level} · giorno {day}', en: '{agent} · level {level} · day {day}' },
  'approvals.approve': { it: 'Approva', en: 'Approve' },
  'approvals.reject': { it: 'Rifiuta', en: 'Reject' },
  'approvals.later': { it: 'Le decisioni arrivano con il passo 2.18', en: 'Decisions come with step 2.18' },
  'pne.title': { it: 'Riammissioni a 30 giorni', en: '30-day readmissions' },
  'pne.sub': { it: 'Indicatore PNE · {pathway} · dal giorno 0', en: 'PNE indicator · {pathway} · since day 0' },
  'pne.count': { it: '{count} riammissioni', en: '{count} readmissions' },
  'pne.reference': { it: '{source}: {rate}', en: '{source}: {rate}' },

  'map.regional': { it: 'Allarme regionale · giorno {day}', en: 'Regional alarm · day {day}' },
  'map.legend': { it: 'Aderenza al PDTA per comune:', en: 'Adherence to the PDTA by comune:' },
  'map.high': { it: 'alta (≥ 70%)', en: 'high (≥ 70%)' },
  'map.medium': { it: 'media (50–69%)', en: 'medium (50–69%)' },
  'map.low': { it: 'bassa (< 50%)', en: 'low (< 50%)' },
  'map.none': { it: 'meno di 10 pazienti', en: 'fewer than 10 patients' },
  'map.outline': { it: 'bordo rosso: comune in allarme', en: 'red outline: comune in alarm' },
  'map.label': { it: 'Mappa dei comuni dell’ATS per aderenza al PDTA', en: 'Map of the ATS comuni by adherence to the PDTA' },
  'map.tip': { it: '{name}: aderenza {pct}', en: '{name}: adherence {pct}' },
  'map.tipNone': { it: '{name}: meno di 10 pazienti', en: '{name}: fewer than 10 patients' },
  'map.alarms': { it: 'Comuni in allarme: {count}', en: 'Comuni in alarm: {count}' },
  'map.noAlarms': { it: 'Nessun comune sotto il 50%.', en: 'No comune below 50%.' },
  'map.geoError': { it: 'Mappa non disponibile ({detail}): elenco dei comuni.', en: 'Map not available ({detail}): list of comuni.' },
  'sankey.intro': {
    it: 'Dove sono oggi i pazienti nel percorso: a sinistra l’ultimo passo fatto, a destra il prossimo.',
    en: 'Where patients stand in the pathway today: the last step done on the left, the next one on the right.',
  },
  'sankey.from': { it: 'Ultimo passo fatto', en: 'Last step done' },
  'sankey.to': { it: 'Prossimo passo', en: 'Next step' },
  'sankey.none': { it: 'Nessuno', en: 'None' },
  'sankey.label': { it: 'Flussi dei pazienti dall’ultimo passo al prossimo', en: 'Patient flows from the last step to the next' },
  'sankey.node': { it: '{step}: {patients} pazienti', en: '{step}: {patients} patients' },
  'sankey.link': { it: '{from} → {to}, {status}: {patients} pazienti', en: '{from} → {to}, {status}: {patients} patients' },
  'status.on_track': { it: 'In linea', en: 'On track' },
  'status.due_soon': { it: 'In scadenza', en: 'Due soon' },
  'status.overdue': { it: 'In ritardo', en: 'Overdue' },
  'status.dropped': { it: 'Fuori percorso', en: 'Off the pathway' },

  'feed.title': { it: 'Attività agenti · live', en: 'Agent activity · live' },
  'feed.empty': { it: 'Le azioni degli agenti appariranno qui.', en: 'Agent actions will appear here.' },
  'feed.level': { it: 'livello {level}', en: 'level {level}' },
  'feed.waiting': { it: 'in attesa', en: 'waiting' },
  'feed.alertRegional': { it: 'Allarme regionale', en: 'Regional alarm' },
  'feed.alertPatient': { it: 'Paziente', en: 'Patient' },
  'feed.step': { it: 'passo {step}', en: 'step {step}' },
  'feed.day': { it: 'Giorno {day}', en: 'Day {day}' },

  'action.reminder': { it: 'Promemoria', en: 'Reminder' },
  'action.call_task': { it: 'Chiamata del Centro Servizi', en: 'Centro Servizi call' },
  'action.notify_mmg': { it: 'Avviso al MMG', en: 'Notice to the MMG' },
  'action.reschedule': { it: 'Riprogrammazione', en: 'Rescheduling' },
  'action.enroll_proposal': { it: 'Proposta di arruolamento', en: 'Enrolment proposal' },
  'action.rule_proposal': { it: 'Proposta di regola', en: 'Rule proposal' },
  'action.pathway_proposal': { it: 'Proposta di percorso', en: 'Pathway proposal' },
  'action.bed_proposal': { it: 'Proposta di posto letto', en: 'Bed proposal' },
  'action.bed_assignment': { it: 'Assegnazione del posto letto', en: 'Bed assignment' },
} satisfies Record<string, Bilingual>

export type Key = keyof typeof STRINGS

export type Translator = (key: Key, vars?: Record<string, string | number>) => string

export function translator(lang: Lang): Translator {
  return (key, vars = {}) =>
    STRINGS[key][lang].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? `{${name}}`))
}

export function isKey(key: string): key is Key {
  return key in STRINGS
}

/** The label of a data value, e.g. label(t, 'action', 'call_task'); the value itself when there is none. */
export function label(t: Translator, prefix: string, value: string): string {
  const key = `${prefix}.${value}`
  return isKey(key) ? t(key) : value
}

/** Agent names are product names and stay the same in both languages (Solution Plan §8). */
export function agentName(agent: string): string {
  return agent
    .split('_')
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(' ')
}

const LOCALE: Record<Lang, string> = { it: 'it-IT', en: 'en-GB' }

export function formatNumber(lang: Lang, value: number, digits = 0): string {
  return new Intl.NumberFormat(LOCALE[lang], { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
}

/** A fraction 0–1 from the data as a percentage (SPEC §2: percentages only in the UI). */
export function formatPercent(lang: Lang, fraction: number, digits = 1): string {
  return `${formatNumber(lang, 100 * fraction, digits)}%`
}

export const LangContext = createContext<Lang>('it')

export function useLang(): { lang: Lang; t: Translator } {
  const lang = useContext(LangContext)
  return { lang, t: translator(lang) }
}
