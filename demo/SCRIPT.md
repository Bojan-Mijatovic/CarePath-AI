# Demo script v1

| | |
|---|---|
| Step | Delivery plan 2.24 (R5) |
| Version | v1.1, 2 Nov 2026: the demo bar's hotkeys and no envelope (2.20), the PNE forecast (2.6), the monthly report (2.14), Lista chiamate and Rivelazione (2.20). v2 after Attività agenti (2.29); final timings at the rehearsals (4.6) |
| Sources | Solution Plan §11 (steps 1–10, trigger sentences); D21 (pacing), D24 (the opening), D44 (no envelope, scenarios 2, 1, 3), D45 (closed loop), D53 (reschedule after the alarm) |
| Target | 7 minutes, Italian audience. Trigger sentences are said in Italian; the Italian colleague reviews them before the first rehearsal |

Two people run the demo. The **narrator** speaks; the **operator** clicks on the trigger sentences. The app works on its own most of the time, so clicks are few and each has a reason in the story.

## Before the audience comes in (T−10 min)

1. `uv run pytest -m demo` passed today on this laptop (the cache check: every LLM text the demo shows is in `demo/cache/`).
2. No model is loaded: `ollama ps` is empty. The demo starts in `cache_only` (D14) and needs no model.
3. `uv run carepath-api`; open <http://127.0.0.1:8000>. The 9 runs replay to day 23 and pause: **measured 59–64 s**. The top bar says "connesso".
4. The console is on "Storia di Maria", in Italian.

The operator's controls are hotkeys of the hidden demo bar (step 2.20). They work while the bar is hidden; the backquote key shows it, with the LLM's cache mode for the team.

| Key | Does |
|---|---|
| `1` `2` `3` | the scenario on screen (it stays paused) |
| space | pause, or ×1 when paused |
| `f` | ×4 |
| `j` | jump to a day (type it, Enter); backwards replays from day 0, about 60 s: avoid |
| `c` | cache_only ↔ cache_first |
| `v` | Rivelazione |
| `r` | reset to day 23 (asks first; about a minute) |
| `` ` `` | show or hide the bar |

## The flow

Times are the target per block. **System** is what the app takes, measured on 2 Nov 2026 by driving the real API on the team laptop; everything else is speech and has to be timed with a stopwatch at the rehearsals.

### Scenario 2, the full flow (about 4:55)

| # | Time | Trigger (it) | Screen | Operator | The app does | System |
|---|---|---|---|---|---|---|
| 0 | 0:15 | "Le regole e il modello di rischio decidono; l'IA scrive solo le frasi, preparate in anticipo, perché tutto gira su questo portatile, senza GPU e senza cloud." | Storia di Maria | — | — | — |
| 1 | 0:30 | "Vi presento la signora Maria…" · "Ogni paziente cronico ha un PAI. Ma chi verifica, ogni giorno, che venga eseguito?" | Storia di Maria | "Avvia la simulazione" | Maria's timeline without the system: discharge, day 31 drug not collected, day 47 back in hospital | — |
| 2 | 0:10 | "Tre regioni, lo stesso sistema. Cominciamo dalla seconda." | Panoramica | — (the console opens on scenario 2, paused) | scenario 2 on screen, day 23, "In pausa" | — |
| 3 | 0:25 | "Mentre parlavamo, gli agenti hanno già lavorato. Una proposta aspetta la direzione: la vediamo tra poco." | Panoramica | point at the queue; **do not approve yet** | cards: patients, on track, agent actions, waiting | queue on day 23: one `notify_mmg` (day 7) |
| 4 | 0:35 | "Guardiamo il territorio. Il sistema osserva 10.000 pazienti, ogni giorno." | Mappa | space (×1); space again when the alarm banner shows | comuni recolour; the echo alarm at Ospedale B on **day 33** | **19 s** from day 23 to 33 |
| 5 | 0:45 | "Ecco un allarme." · "Non solo cosa, ma perché. E l'IA controlla sé stessa." | Mappa → Chiedi | click the banner | the investigation's 4 steps one by one; the Verifier marks steps 1–2 "verificato" and 3–4 "corretto" with the correction under the claim | from the cache in under 1 s; the steps show at 0.7 s each |
| 5b | 0:20 | "L'agente propone anche una soluzione strutturale. Comprare è una decisione nostra." | Panoramica | "Approva" on "Proposta di capacità", then on the MMG notice | the 30B sentence: Ospedale B 30,4 days, from 1 to 2 slots a day, 57,6 → 19,6 days over 6 months | approve under 0.1 s |
| 6 | 0:55 | "Diamo più autonomia." · "La direzione decide quanta autonomia ha l'IA. L'effetto si vede subito." | Confronto | Riprogrammazione → "Da sola"; mode "Senza / con CarePath"; `f` (×4) for about 15 s; space; mode "Prima / dopo i nuovi posti" | split screen; on day ~62: readmissions 81 → 63, on track 71% → 81%; after the pause Ospedale B 59,8 → 23,1 days with the new slot | ×4 day 33 → 62: **15.6 s** (the pause lands 1–2 days later); the lever run catches up while paused in **8.5 s** |
| 7 | 0:30 | "E se compriamo un ecocardiografo? Una decisione di budget, misurata con il vostro indicatore PNE." | What-if | slider +1, "Simula 6 mesi"; then +2 | 6 months: 56 readmissions avoided (200 → 144, all from the agents), wait at Ospedale B 57,6 → 19,6 days (+2: 3,8); PNE at year end 12,7% without, 10,5% with CarePath, against Italia 11,87% | answer in 21–35 ms (computed in advance, said on screen) |
| 9 | 0:30 | "Torniamo da Maria." | Chiamate, then Pazienti | the call list of today (or `Giorno` 31); then Maria, with CarePath, "Senza CarePath" and back | the list by risk with reasons, ladder and outcome; Maria's record | with CarePath: Centro Servizi call on day 43 (delivery arranged), furosemide collected on day 45, HbA1c on day 52, no readmission; without: admitted on day 47 | under 0.1 s |

### Scenarios 1 and 3 in short loops, and the reveal (about 1:50)

| # | Time | Trigger (it) | Screen | Operator | The app does | System |
|---|---|---|---|---|---|---|
| S1 | 0:45 | "Un'altra regione. Stesso sistema, nessuna istruzione." | Chiedi → Panoramica → Confronto | `1` (its alarm was on day 19, before the opening day, so it is already explained); approve its proposal; `f` for about 11 s; space | Ospedale A: the investigation, +2 slots proposed; on day ~44 readmissions 57 → 47, Ospedale A 54,2 → 17,1 days with the slots | ×4 20 days: **10.9 s**; catch-up **3.0 s** |
| S3 | 0:45 | "E la terza." | Mappa → Chiedi → Panoramica → Confronto | `3`; space to the alarm, space; approve; `f` for about 10 s; space | Ospedale C alarm on day 29; +1 slot; on day ~50 readmissions 69 → 56, Ospedale C 27,6 → 15,1 days | ×1 day 23 → 29: **11 s**; ×4 20 days: **10.3 s**; catch-up **5.1 s** |
| 10 | 0:20 | "Gli agenti hanno trovato da soli i problemi nascosti, in tre regioni diverse." | Rivelazione | `v` | the three scenarios: what the agents' alarms found next to the hidden places, each marked "coincide" | under 0.1 s |

**Total: about 6:45** of targets, with about 1:30 of it system time measured above. It is tight: if a rehearsal runs over, the cut order of D45 applies (the short loops of scenarios 1 and 3 first; Rivelazione still shows all three).

**Rule: nothing that acts on patients is approved before a scenario's alarm investigation is on screen.** An approved action changes the run from the next day, so the alarm's tools return other numbers and the cached investigation no longer matches: approving the day-23 MMG notice left scenario 2's day-33 alarm without an investigation (checked 2 Nov 2026; the two questions and the proposal still came from the cache). The cache warm-up plays the demo with no approval before the alarms. Approvals after the investigation, the capacity proposal (no effect in the run) and Riprogrammazione at "Da sola" in step 6 are safe: scenario 3 proposes a reschedule only after its own alarm (D53).

## If something stops

| What | What the operator does |
|---|---|
| The alarm does not come by day 40 | Pause; jump to day 33 (scenario 2), 29 (scenario 3). Jumping back replays from day 0, about 60 s: the narrator fills it |
| A Chiedi step or the proposal shows the template, or a question gives an error | The cache check was not run today, or the text was typed differently; carry on with the template, it holds the same numbers |
| The screen does not update | Reload the page; the state is on the server |
| The laptop fails | Backup laptop, same scenario, jump to the same day; if both fail, the video (4.5) |

## Not ready yet

| Gap | Effect on the script | Comes with |
|---|---|---|
| Undo of an effect | "Annulla" in Attività agenti marks an action undone in the audit log; it does not move a rescheduled patient back (SPEC §7.3) | not planned |
| Euros | step 7 shows readmissions, waits and the PNE forecast; euros wait for the cost per readmission (Q2) | Q2 |
| A box for free questions in Chiedi | the two cached questions can only be asked through the API (`POST /api/ask`) | 2.10 (in progress) |
| Rule proposal after the investigation (5a) | not in the demo: Rule Advisor did not enter at checkpoint 2.23 | — |
| A call script on the call list | the Daily Worklist (phase 3) did not enter | — |
| Maria's days with CarePath | Solution Plan §11 and the prototype say call on day 31, drug on 33, HbA1c on 40; the agents' own rules call her on day 43 (the weight gain), drug on 45, HbA1c on 52. The script says what the app shows | the lead (R1) decides whether to keep the agents' days |

## Numbers measured for this script

Run on 2 Nov 2026, commit `eba59c0`, team laptop on mains power, no model loaded, by a throwaway script (not in the repo) that drove the API on a second port with the calls above and the console's own reads. Days are those the runs reached after each pause.

| Step | Measured |
|---|---|
| Start, 9 runs to day 23 | 59.2 s and 63.7 s (two starts) |
| Scenario 2, ×1 day 23 → 33 | 18.8 s and 19.3 s |
| Scenario 2, ×4 day 33 → 62 | 15.6 s, stopped on day 64 |
| Lever run catch-up, scenario 2 | 8.5 s |
| Scenario 1, ×4 for 20 days | 10.9 s; catch-up 3.0 s |
| Scenario 3, ×1 day 23 → 29 | 11.0 s; ×4 for 20 days 10.3 s; catch-up 5.1 s |
| Approve, autonomy, what-if, Maria, Chiedi from the cache | under 0.3 s each |
