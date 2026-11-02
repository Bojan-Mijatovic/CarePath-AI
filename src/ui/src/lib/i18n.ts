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
  'top.paused': { it: 'In pausa', en: 'Paused' },
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

  'bar.title': { it: 'Barra demo', en: 'Demo bar' },
  'bar.scenario': { it: 'Scenario {n}', en: 'Scenario {n}' },
  'bar.pause': { it: 'Pausa', en: 'Pause' },
  'bar.jump': { it: 'Vai al giorno', en: 'Jump to day' },
  'bar.go': { it: 'Vai', en: 'Go' },
  'bar.cache': { it: 'LLM: {mode}', en: 'LLM: {mode}' },
  'bar.cacheToggle': { it: 'Cambia', en: 'Switch' },
  'bar.reset': { it: 'Reset', en: 'Reset' },
  'bar.resetConfirm': {
    it: 'Ricostruire tutte le simulazioni al giorno di partenza? Ci vuole circa un minuto.',
    en: 'Rebuild every run to the start day? It takes about a minute.',
  },
  'bar.reveal': { it: 'Rivelazione', en: 'Reveal' },
  'bar.keys': {
    it: 'Tasti: 1 2 3 scenario · spazio pausa/×1 · f ×4 · j giorno · c cache · v rivelazione · r reset · ` barra',
    en: 'Keys: 1 2 3 scenario · space pause/×1 · f ×4 · j day · c cache · v reveal · r reset · ` bar',
  },
  'bar.failed': { it: 'Comando non riuscito: {detail}', en: 'Command failed: {detail}' },

  'calls.lead': {
    it: 'La lista che gli agenti preparano ogni mattina per il Centro Servizi: una chiamata per paziente, con tutti i motivi, ordinata per rischio.',
    en: 'The list the agents prepare every morning for the Centro Servizi: one call per patient, with every reason, ordered by risk.',
  },
  'calls.day': { it: 'Giorno', en: 'Day' },
  'calls.today': { it: 'Oggi', en: 'Today' },
  'calls.count': { it: 'Giorno {day} · primi {n} di {total}', en: 'Day {day} · first {n} of {total}' },
  'calls.rank': { it: '#', en: '#' },
  'calls.patient': { it: 'Paziente', en: 'Patient' },
  'calls.who': { it: '{age} anni · {comune}', en: 'aged {age} · {comune}' },
  'calls.alone': { it: 'vive solo', en: 'lives alone' },
  'calls.risk': { it: 'Rischio', en: 'Risk' },
  'calls.reasons': { it: 'Motivi', en: 'Reasons' },
  'calls.step': { it: 'Scala', en: 'Ladder' },
  'calls.outcome': { it: 'Esito della chiamata', en: 'Call outcome' },
  'calls.empty': { it: 'Nessuna lista per questo giorno.', en: 'No list for this day.' },
  'escalation.0': { it: '–', en: '–' },
  'escalation.1': { it: 'Promemoria', en: 'Reminder' },
  'escalation.2': { it: 'Chiamata', en: 'Call' },
  'escalation.3': { it: 'MMG avvisato', en: 'MMG notified' },
  'outcome.completed': { it: 'Chiamata fatta', en: 'Call made' },
  'outcome.delivery_arranged': { it: 'Consegna a domicilio organizzata', en: 'Home delivery arranged' },

  'reveal.kicker': { it: 'Rivelazione', en: 'Reveal' },
  'reveal.headline': {
    it: 'Tre regioni, problemi nascosti in posti diversi. Gli agenti li hanno trovati da soli.',
    en: 'Three regions, problems hidden in different places. The agents found them on their own.',
  },
  'reveal.scenario': { it: 'Scenario {n}', en: 'Scenario {n}' },
  'reveal.found': { it: 'Trovato dagli agenti', en: 'Found by the agents' },
  'reveal.hidden': { it: 'Nascosto nei dati', en: 'Hidden in the data' },
  'reveal.bottleneck': { it: 'Collo di bottiglia', en: 'Bottleneck' },
  'reveal.mmg': { it: 'Gruppo di MMG', en: 'MMG group' },
  'reveal.comuni': { it: 'Comuni a rischio', en: 'Comuni at risk' },
  'reveal.day': { it: 'giorno {day}', en: 'day {day}' },
  'reveal.notYet': { it: 'non ancora', en: 'not yet' },
  'reveal.match': { it: 'coincide', en: 'matches' },
  'reveal.noMatch': { it: 'non coincide', en: 'does not match' },
  'reveal.named': { it: '{n} di {total} nominati', en: '{n} of {total} named' },
  'reveal.restart': { it: 'Ricomincia', en: 'Start again' },

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
  'approvals.failed': { it: 'La decisione non è stata registrata. Riprovate.', en: 'The decision was not recorded. Try again.' },
  'autonomy.title': { it: 'Autonomia degli agenti', en: 'Agent autonomy' },
  'autonomy.lead': {
    it: 'La direzione decide quanto l’IA può fare da sola. Le decisioni cliniche restano sempre ai medici.',
    en: 'Management decides how much the AI may do alone. Clinical decisions always stay with the doctors.',
  },
  'autonomy.level0': { it: 'Osserva', en: 'Observes' },
  'autonomy.level1': { it: 'Propone', en: 'Proposes' },
  'autonomy.level2': { it: 'Con approvazione', en: 'With approval' },
  'autonomy.level3': { it: 'Da sola', en: 'Alone' },
  'autonomy.failed': { it: 'Il livello non è stato cambiato. Riprovate.', en: 'The level was not changed. Try again.' },
  'compare.lead': {
    it: 'La stessa simulazione, con lo stesso seme e la stessa popolazione, senza e con gli agenti.',
    en: 'The same simulation, same seed and population, without and with the agents.',
  },
  'compare.leadLever': {
    it: 'Gli agenti prima e dopo i nuovi posti approvati dal management: stessa simulazione fino al giorno della leva.',
    en: 'The agents before and after the new slots the management approved: the same simulation up to the lever day.',
  },
  'compare.mode': { it: 'Confronto', en: 'Comparison' },
  'compare.modeArms': { it: 'Senza / con CarePath', en: 'Without / with CarePath' },
  'compare.modeLever': { it: 'Prima / dopo i nuovi posti', en: 'Before / after the new slots' },
  'compare.without': { it: 'Senza agenti', en: 'Without agents' },
  'compare.with': { it: 'Con agenti', en: 'With agents' },
  'compare.before': { it: 'Con agenti, posti di oggi', en: 'With agents, slots of today' },
  'compare.after': { it: 'Con agenti e +{slots} posti al giorno', en: 'With agents and +{slots} slots a day' },
  'compare.afterOne': { it: 'Con agenti e +1 posto al giorno', en: 'With agents and +1 slot a day' },
  'compare.day': { it: 'Giorno {day}', en: 'Day {day}' },
  'compare.catchingUp': {
    it: 'La simulazione con i nuovi posti è al giorno {day} e recupera durante la pausa.',
    en: 'The run with the new slots is at day {day} and catches up during the pause.',
  },
  'compare.readmissions': { it: 'Riammissioni a 30 giorni', en: '30-day readmissions' },
  'compare.onTrack': { it: 'In linea con il PAI', en: 'On track with the PAI' },
  'compare.points': { it: '{points} punti', en: '{points} points' },
  'compare.overdue': { it: 'Passi in ritardo', en: 'Overdue steps' },
  'compare.cost': { it: 'Costo stimato delle riammissioni', en: 'Estimated cost of readmissions' },
  'cost.note': { it: '{eur} a riammissione: {source}', en: '{eur} per readmission: {source}' },
  'whatif.saving': { it: 'Risparmio stimato in {months} mesi', en: 'Estimated saving in {months} months' },
  'pne.cost': { it: 'Costo stimato: {eur}', en: 'Estimated cost: {eur}' },
  'compare.waits': { it: '{step}: attesa media e posti usati, ultimi 7 giorni', en: '{step}: mean wait and slots used, last 7 days' },
  'compare.facility': { it: 'Struttura', en: 'Facility' },
  'compare.wait': { it: 'Attesa media', en: 'Mean wait' },
  'compare.use': { it: 'Posti usati', en: 'Slots used' },
  'compare.days': { it: '{days} giorni', en: '{days} days' },
  'whatif.title': { it: 'E se…?', en: 'What if…?' },
  'whatif.lead': {
    it: 'Cambiate una leva e guardate i prossimi {months} mesi, senza e con gli agenti.',
    en: 'Change one lever and look at the next {months} months, without and with the agents.',
  },
  'whatif.lever': {
    it: '{step}: posti in più al giorno a {facility}, dal giorno {day}',
    en: '{step}: extra slots a day at {facility}, from day {day}',
  },
  'whatif.leverPlain': { it: 'Posti in più al giorno', en: 'Extra slots a day' },
  'whatif.run': { it: 'Simula {months} mesi', en: 'Simulate {months} months' },
  'whatif.withLever': { it: 'Con agenti e +{slots} posti', en: 'With agents and +{slots} slots' },
  'whatif.withLeverOne': { it: 'Con agenti e +1 posto', en: 'With agents and +1 slot' },
  'whatif.avoided': { it: 'Riammissioni evitate in {months} mesi', en: 'Readmissions avoided in {months} months' },
  'whatif.avoidedSub': { it: 'Con agenti e leva, rispetto a senza agenti', en: 'With agents and the lever, against without agents' },
  'whatif.wait': { it: 'Attesa media a {facility}', en: 'Mean wait at {facility}' },
  'whatif.waitSub': { it: 'Con agenti senza leva: {without}', en: 'With agents, no lever: {without}' },
  'whatif.time': { it: 'Tempo di risposta', en: 'Response time' },
  'whatif.ms': { it: '{ms} ms', en: '{ms} ms' },
  'whatif.precomputed': {
    it: 'Simulazioni complete calcolate in anticipo, con gli stessi agenti',
    en: 'Full simulations computed in advance, with the same agents',
  },
  'pneForecast.title': {
    it: 'Previsione PNE a fine anno · riammissioni a 30 giorni al giorno {day}',
    en: 'PNE forecast to year end · 30-day readmissions on day {day}',
  },
  'pneForecast.sub': {
    it: 'Dal giorno 0 a fine anno, stesse simulazioni complete calcolate in anticipo, con i livelli di autonomia iniziali.',
    en: 'From day 0 to year end, the same full simulations computed in advance, with the starting autonomy levels.',
  },
  'pneForecast.tip': { it: '{rate} · {count} riammissioni', en: '{rate} · {count} readmissions' },
  'pneForecast.reference': { it: 'Linea tratteggiata: {source}, {rate}', en: 'Dashed line: {source}, {rate}' },
  'pneForecast.rate': { it: 'Tasso a fine anno', en: 'Rate at year end' },
  'pneForecast.count': { it: 'Riammissioni nell’anno', en: 'Readmissions in the year' },
  'whatif.table': { it: 'Dal giorno {from} al giorno {to}', en: 'From day {from} to day {to}' },
  'whatif.note': {
    it: 'Stesso seme, stessa popolazione, stesso periodo. L’attesa è la media sulle prenotazioni dei 6 mesi.',
    en: 'Same seed, same population, same period. The wait is the mean over the 6 months’ bookings.',
  },
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

  'map.open': { it: 'Apri l’indagine', en: 'Open the investigation' },
  'ask.kicker': { it: 'Indagine avviata dall’allarme · Investigator', en: 'Investigation started by the alarm · Investigator' },
  'ask.steps': { it: 'Passi dell’indagine', en: 'Investigation steps' },
  'ask.step': { it: 'Passo {step}', en: 'Step {step}' },
  'ask.unverified': { it: 'da verificare', en: 'not yet verified' },
  'ask.kickerQuestion': { it: 'Domanda dell’operatore · Investigator', en: 'Operator’s question · Investigator' },
  'ask.box': { it: 'Chiedete agli agenti', en: 'Ask the agents' },
  'ask.placeholder': { it: 'Una domanda sui dati del percorso…', en: 'A question about the pathway’s data…' },
  'ask.send': { it: 'Chiedi', en: 'Ask' },
  'ask.noAnswer': {
    it: 'Per questa domanda non c’è una risposta preparata oggi: in questa demo le risposte sono generate in anticipo.',
    en: 'There is no answer prepared for this question today: in this demo the answers are generated in advance.',
  },
  'ask.suggestionsDay': { it: 'Risposte preparate per il giorno {day}.', en: 'Answers prepared for day {day}.' },
  'ask.verified': { it: 'verificato', en: 'verified' },
  'ask.corrected': { it: 'corretto', en: 'corrected' },
  'ask.correction': { it: 'Verifier', en: 'Verifier' },
  'ask.conclusion': { it: 'Conclusione', en: 'Conclusion' },
  'ask.empty': {
    it: 'Nessuna indagine finora: l’Investigator parte quando il Monitoring alza un allarme regionale.',
    en: 'No investigation yet: the Investigator starts when Monitoring raises a regional alarm.',
  },
  'ask.day': { it: 'Giorno {day}', en: 'Day {day}' },
  'patient.label': { it: 'Paziente', en: 'Patient' },
  'patient.show': { it: 'Mostra', en: 'Show' },
  'patient.with': { it: 'Con CarePath', en: 'With CarePath' },
  'patient.without': { it: 'Senza CarePath', en: 'Without CarePath' },
  'patient.header': {
    it: '{age} anni · {comune} · {alone}{km} km dall’ospedale · {mmg}',
    en: '{age} · {comune} · {alone}{km} km from the hospital · {mmg}',
  },
  'patient.alone': { it: 'vive da sola · ', en: 'lives alone · ' },
  'patient.aloneM': { it: 'vive da solo · ', en: 'lives alone · ' },
  'patient.state': { it: '{status} · ultimo passo {current} · prossimo {next} entro il giorno {due}', en: '{status} · last step {current} · next {next} by day {due}' },
  'patient.overdue': { it: 'In ritardo: {steps}', en: 'Overdue: {steps}' },
  'patient.risk': { it: 'Rischio di ricovero a 30 giorni: {risk}', en: '30-day admission risk: {risk}' },
  'patient.timeline': { it: 'Linea del tempo', en: 'Timeline' },
  'event.TELEMON_READING.count': { it: '{count} letture del telemonitoraggio', en: '{count} telemonitoring readings' },
  'patient.since': { it: 'Dal giorno 0; la storia precedente non è mostrata.', en: 'From day 0; earlier history is not shown.' },
  'patient.agent': { it: 'agente', en: 'agent' },
  'patient.notFound': { it: 'Paziente non trovato in questa simulazione.', en: 'Patient not found in this run.' },
  'patient.bookedFor': { it: 'per il giorno {day}', en: 'for day {day}' },
  'patient.unplanned': { it: 'non programmato', en: 'unplanned' },
  'event.DISCHARGE': { it: 'Dimissione', en: 'Discharge' },
  'event.ADMISSION': { it: 'Ricovero', en: 'Admission' },
  'event.VISIT': { it: 'Visita', en: 'Visit' },
  'event.IMAGING': { it: 'Esame strumentale', en: 'Imaging' },
  'event.LAB': { it: 'Esame di laboratorio', en: 'Lab test' },
  'event.DISPENSE': { it: 'Ritiro in farmacia', en: 'Pharmacy dispensing' },
  'event.TELEMON_START': { it: 'Telemonitoraggio avviato', en: 'Telemonitoring started' },
  'event.BOOKING': { it: 'Prenotazione', en: 'Booking' },
  'event.CALL': { it: 'Chiamata del Centro Servizi', en: 'Centro Servizi call' },
  'event.REMINDER': { it: 'Promemoria', en: 'Reminder' },

  'feed.title': { it: 'Attività agenti · live', en: 'Agent activity · live' },
  'feed.empty': { it: 'Le azioni degli agenti appariranno qui.', en: 'Agent actions will appear here.' },
  'feed.level': { it: 'livello {level}', en: 'level {level}' },
  'feed.waiting': { it: 'in attesa', en: 'waiting' },
  'feed.alertRegional': { it: 'Allarme regionale', en: 'Regional alarm' },
  'feed.alertPatient': { it: 'Paziente', en: 'Patient' },
  'feed.step': { it: 'passo {step}', en: 'step {step}' },
  'feed.status.proposed': { it: 'in attesa di approvazione', en: 'waiting for approval' },
  'feed.status.approved': { it: 'approvata', en: 'approved' },
  'feed.status.rejected': { it: 'rifiutata', en: 'rejected' },
  'feed.status.undone': { it: 'annullata', en: 'undone' },
  'feed.evidence': { it: 'Evidenza: {list}', en: 'Evidence: {list}' },
  'feed.whatif': { it: 'simulazione what-if', en: 'what-if simulation' },
  'feed.rule': { it: 'regola {id}', en: 'rule {id}' },
  'feed.deadline': { it: 'scadenza {id}', en: 'deadline {id}' },
  'feed.openDays': { it: 'aperto da {days} giorni', en: 'open for {days} days' },
  'feed.undo': { it: 'Annulla', en: 'Undo' },
  'feed.undoFailed': { it: 'Non annullata', en: 'Not undone' },
  'feed.report': {
    it: 'Rapporto mensile in stile PNE pronto, giorni {from}–{to}: in Panoramica.',
    en: 'Monthly PNE-style report ready, days {from}–{to}: on Panoramica.',
  },
  'report.title': { it: 'Rapporto del mese {month} · Reporter', en: 'Report for month {month} · Reporter' },
  'report.sub': { it: 'Giorni {from}–{to} · numeri dagli indicatori del percorso', en: 'Days {from}–{to} · numbers from the pathway indicators' },
  'feed.day': { it: 'Giorno {day}', en: 'Day {day}' },

  'action.reminder': { it: 'Promemoria', en: 'Reminder' },
  'action.call_task': { it: 'Chiamata del Centro Servizi', en: 'Centro Servizi call' },
  'action.notify_mmg': { it: 'Avviso al MMG', en: 'Notice to the MMG' },
  'action.reschedule': { it: 'Riprogrammazione', en: 'Rescheduling' },
  'action.enroll_proposal': { it: 'Proposta di arruolamento', en: 'Enrolment proposal' },
  'action.rule_proposal': { it: 'Proposta di regola', en: 'Rule proposal' },
  'action.capacity_proposal': { it: 'Proposta di capacità', en: 'Capacity proposal' },
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

/** Euros, whole (C39: the pathway's assumed cost per readmission times readmissions). */
export function formatEuro(lang: Lang, value: number): string {
  return new Intl.NumberFormat(LOCALE[lang], { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value)
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
