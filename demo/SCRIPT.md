# Demo script v1

| | |
|---|---|
| Step | Delivery plan 2.24 (R5) |
| Version | v1.1, 2 Nov 2026: the demo bar's hotkeys and no envelope (2.20), the PNE forecast (2.6), the monthly report (2.14), Lista chiamate and Rivelazione (2.20). v1.2, 3 Nov 2026: step 9c, Posti letto, optional (D64). v1.3, 3 Nov 2026: the guide bar (D66, proposed). v1.4, 3 Nov 2026: who-made-it labels, "Dietro le quinte", the system slide, the Investigator's stages, the evidence in full (D66, proposed). v2 after Attività agenti (2.29); final timings at the rehearsals (4.6). v3 draft, 13 Nov 2026: three situations (D67, proposed). v3.1 draft, 19 Nov 2026: the console without the guide bar, the operator's own buttons |
| Sources | Solution Plan §11 (steps 1–10, trigger sentences); D21 (pacing), D24 (the opening), D44 (no envelope, scenarios 2, 1, 3), D45 (closed loop), D53 (reschedule after the alarm) |
| Target | 7 minutes, Italian audience. Trigger sentences are said in Italian; the Italian colleague reviews them before the first rehearsal |

Two people run the demo. The **narrator** speaks; the **operator** clicks on the trigger sentences. The app works on its own most of the time, so clicks are few and each has a reason in the story.

## Before the audience comes in (T−10 min)

1. `uv run pytest -m demo` passed today on this laptop (the cache check: every LLM text the demo shows is in `demo/cache/`).
2. No model is loaded: `ollama ps` is empty. The demo starts in `cache_only` (D14) and needs no model.
3. `uv run carepath-api`; open <http://127.0.0.1:8000>. The 9 runs replay to day 23 and pause: **measured 59–64 s**. The top bar says "connesso".
4. The console is on "Storia di Maria", in Italian.

**The guide bar (D66)** at the bottom of the screen walks this script in 20 stages, which the audience sees: the stage ("Tappa 5 di 20"), its title and one sentence. ▶, → or PageDown (a presenter's clicker) takes the next stage: its scenario, its screen and its clock. At ×1 the server stops the clock on the alarm (D63); at ×4 the guide stops it on the script's day (62, 43 and 49 in scenarios 2, 1 and 3; it lands a day later at most). ▶ waits while the clock runs. The operator still clicks every approval, "Da sola", "Prima / dopo i nuovi posti", the what-if slider, "Senza CarePath" and "Trova il posto letto"; the guide outlines each and scrolls to it, and never clicks one. ◀ goes back a stage without running its clock. `g` hides the bar; a reload keeps its stage; a reset (`r`) and "Ricomincia" take it back to stage 1. Stage 12 is 9c, marked "facoltativa": to cut it, press ▶ again without clicking. Under the sentence, a "Dietro le quinte" line says what the system did at that stage, and on stages 2, 3 and 16 a dashed outline asks the audience to watch Attività agenti. Every value and text in the console carries a label for who made it: "Calcolato" (code), "Scritto dal LLM" (sentences only) or "Decide una persona"; stage 2 explains the three. In Chiedi, "Come lavora l’Investigator" lights its four stages as the steps appear: the tools first, then the model's sentences, then the Verifier's marks. In Attività agenti, a click on "Evidenza" opens the tool calls or rules behind an action. Before step 1, show the slide `demo/slides/how-it-works-it.svg` (English: `-en.svg`).

The hidden demo bar (step 2.20) stays as the fallback. Its hotkeys work while it is hidden; the key left of `1` shows it, with the LLM's cache mode for the team.

| Key | Does |
|---|---|
| `1` `2` `3` | the situation on screen (it stays paused): v3 Normal, A · Closure, B · Investment (scenarios 0, 4, 3); in v2 they were scenarios 1, 2, 3 |
| space | pause, or ×1 when paused |
| `f` | ×4 |
| `j` | jump to a day (type it, Enter); backwards replays from day 0, about 60 s: avoid |
| `c` | cache_only ↔ cache_first |
| `v` | Rivelazione |
| `r` | reset to day 23 (asks first; about a minute) |
| the key left of `1` (`` ` `` on a US layout, `\` on an Italian one) | show or hide the bar; it is matched by its place, so any layout works |
| → or PageDown, ← or PageUp | the guide's next or previous stage |
| `g` | show or hide the guide bar |

## The flow, v3 draft: three situations (D67, proposed)

Not yet rehearsed and not yet agreed: until D67 is agreed at a sync, the v2 flow below is the demo's. Since 13 Nov 2026 the console has the layout of the lead's console mockup and **no guide bar** (the lead asked for it): the presenter walks the stages below with the header (situation, Pausa, ×1, ×4) and the page tabs (Cruscotto, Pazienti, Ospedali, Agenti, Analisi, Impostazioni). `src/ui/src/lib/guide.ts` still lists the 16 stages but is no longer shown; at ×4 nothing stops the clock on the script's day, so pause it by hand. The Operator column below names the console's own buttons (updated 19 Nov 2026); the header's ◀ ▶ look at past days and are not the guide's. Before the audience comes in, v3: the API prepares seven runs (scenarios 0, 4 and 3, both arms, and scenario 3's lever run; start-up time not yet measured) and the console opens on Cruscotto, normal situation, day 23, paused; the green dot in the header means connected. Keys `1` `2` `3` choose the situations in this order; each keeps its own day. The Italian lines need the Italian colleague's review. Days measured on seed 42 (13 Nov 2026); times are targets to time at the rehearsals.

| # | Situation | Trigger (it) | Screen | Operator | The app does |
|---|---|---|---|---|---|
| 1 | Normal (0) | "Vi presento la signora Maria… Ma chi verifica, ogni giorno, che il suo PAI venga eseguito?" | Pazienti | tab Pazienti; "Senza CarePath" on Maria | her story without CarePath, recorded in advance |
| 2 | Normal | "Una giornata normale. Nessun imprevisto: gli agenti seguono ogni paziente, ogni giorno." | Cruscotto | tab Cruscotto | day 23, paused; the agents' work of the day; one MMG notice waits |
| 3 | Normal | "Chi chiamiamo oggi? Prima chi rischia di più." | Pazienti | tab Pazienti | today's list, ranked by risk, with the reasons |
| 4 | Normal | "La stessa regione, senza e con CarePath." | Analisi | tab Analisi; ×4, then Pausa on day 60 | on day 60: on track 80.6% with the agents vs 70.8% without; 57 vs 73 readmissions in 30 days since day 0 |
| 5 | Normal | "Torniamo da Maria." | Pazienti | tab Pazienti; "Senza CarePath" and back | her day 31 call with CarePath; her day 47 admission without |
| 5b | Normal, **optional** | "Il ricovero lo decide il medico; dove, lo trova l'IA in un istante." | Pazienti, below Maria | "Trova il posto letto" | Ospedale A, cardiology, bed 40 |
| 6 | A · Closure (4) | "Ora un imprevisto: l'ambulatorio di cardiologia dell'Ospedale B chiude per un mese, senza preavviso." | Cruscotto | "A · Chiusura non prevista" in the header; ×1 (the clock stops by itself on day 36) | from day 30 Ospedale B's appointments are cancelled; on day 36 the echo wait alarm opens at Ospedale B |
| 7 | A | "Non solo cosa, ma perché." | Ospedali | the line under the header, "Allarme dal giorno 36 · apri", or a suggested question | the investigation of the alarm (**cache to warm**, see below) |
| 8 | A | "L'agente propone di spostare chi aspetta troppo. Decidiamo noi." | Agenti | tab Agenti; "Approva" on the reschedule | 24 patients move from Ospedale B to Ospedale A, waiting 4.3 days; the alarm closes the next day (day 37, against day 50 without the approval) |
| 9 | A | "Senza CarePath i pazienti aspettano la riapertura." | Analisi | tab Analisi; ×4, then Pausa on day 60 | the two arms side by side through the closure |
| 10 | B · Investment (3) | "Un altro caso: all'Ospedale C l'ecocardiografia ha meno posti di quanti ne servono." | Cruscotto | "B · Investimento pianificato" in the header; ×1 (stops by itself on day 29) | the echo wait alarm at Ospedale C |
| 11 | B | "Perché?" | Ospedali | the line under the header, "Allarme dal giorno 29 · apri" | the investigation (cached) |
| 12 | B | "Qui spostare non basta: l'agente propone di comprare capacità. La spesa la decide la direzione." | Agenti | tab Agenti; "Approva" on the capacity proposal | the console turns to the run with the new slots (C34) |
| 13 | B | "Prima e dopo l'acquisto." | Analisi | tab Analisi; ×4, then Pausa on day 60; "Prima / dopo i nuovi posti" | the mean echo wait at Ospedale C over the 6 months from day 30: 56.1 days without the purchase, 7.5 with +1 slot a day (D68) (`demo/whatif/scenario_3.json`) |
| 14 | B | "E se compriamo di più? Misurato con il vostro indicatore PNE." | Analisi, below | the slider | +0 to +4 slots, from the precomputed grid |
| 15 | All three | "Tre situazioni, lo stesso sistema. Ecco cosa è cambiato in ognuna." | Analisi, last panel | — | the three situations on day 60–61: on track with and without CarePath, readmissions, cost avoided, the alarms, the decisions and the echo wait after each alarm (closure 7.9 vs 9.8 days, purchase 5.0 vs 10.4) |

**Rule: approve only what the script approves, on the alarm's day**: the reschedule on day 36 in A, the capacity proposal on day 29 in B. The cache is warmed after exactly these (`demo/cache/manifest.json`, `approve`).

**Before the first rehearsal of v3**, on a laptop with the models: `uv run python testing/cache_warmup.py --live` fills scenario 4's investigation and its two Chiedi questions and scenario 0's day-59 report (about 20–30 minutes), then `uv run python testing/cache_hashes.py` and `uv run pytest -m demo`. Until then step 7 shows no investigation and the report is the template.

Not in v3: Rivelazione (no situation but B hides patterns; the `v` key still opens it for scenario 3).

## The flow, v2 (D44, in force until D67 is agreed)

The console in this working copy no longer has the v2 screens (they are sections of the six pages, D67) nor scenarios 1 and 2 in the demo: v2 runs on the console and engine before D67.


Times are the target per block. **System** is what the app takes, measured on 2 Nov 2026 by driving the real API on the team laptop; everything else is speech and has to be timed with a stopwatch at the rehearsals.

### Scenario 2, the full flow (about 4:55)

| # | Time | Trigger (it) | Screen | Operator | The app does | System |
|---|---|---|---|---|---|---|
| 0 | 0:15 | "Le regole e il modello di rischio decidono; l'IA scrive solo le frasi, preparate in anticipo, perché tutto gira su questo portatile, senza GPU e senza cloud. Gli effetti delle azioni e gli euro sono ipotesi della simulazione: 3.500 euro a riammissione." | Storia di Maria | — | — | — |
| 1 | 0:30 | "Vi presento la signora Maria…" · "Ogni paziente cronico ha un PAI. Ma chi verifica, ogni giorno, che venga eseguito?" | Storia di Maria | "Avvia la simulazione" | Maria's timeline without the system: discharge, day 31 drug not collected, day 47 back in hospital | — |
| 2 | 0:10 | "Tre regioni, lo stesso sistema. Cominciamo dalla seconda." | Panoramica | — (the console opens on scenario 2, paused) | scenario 2 on screen, day 23, "In pausa" | — |
| 3 | 0:25 | "Mentre parlavamo, gli agenti hanno già lavorato. Una proposta aspetta la direzione: la vediamo tra poco." | Panoramica | point at the queue; **do not approve yet** | cards: patients, on track, agent actions, waiting | queue on day 23: one `notify_mmg` (day 7) |
| 4 | 0:35 | "Guardiamo il territorio. Il sistema osserva 10.000 pazienti, ogni giorno." | Mappa | space (×1); the clock stops by itself on the alarm's day (D63) | comuni recolour; the echo alarm at Ospedale B on **day 33** | **19 s** from day 23 to 33 |
| 5 | 0:45 | "Ecco un allarme." · "Non solo cosa, ma perché. E l'IA controlla sé stessa." | Mappa → Chiedi | click the banner | the investigation's 4 steps one by one; the Verifier marks steps 1–2 "verificato" and 3–4 "corretto" with the correction under the claim | from the cache in under 1 s; the steps show at 0.7 s each; optionally one of the suggested questions on top of Chiedi, prepared for day 33 only |
| 5b | 0:20 | "L'agente propone anche una soluzione strutturale. Comprare è una decisione nostra." | Panoramica | "Approva" on "Proposta di capacità", then on the MMG notice | the 30B sentence: Ospedale B 30,4 days, from 1 to 2 slots a day, 57,6 → 19,6 days over 6 months | approve under 0.1 s |
| 6 | 0:55 | "Diamo più autonomia." · "La direzione decide quanta autonomia ha l'IA. L'effetto si vede subito." | Confronto | Riprogrammazione → "Da sola"; mode "Senza / con CarePath"; `f` (×4) for about 15 s; space; mode "Prima / dopo i nuovi posti" | split screen; on day ~62: readmissions 81 → 63, on track 71% → 81%; after the pause Ospedale B 59,8 → 23,1 days with the new slot | ×4 day 33 → 62: **15.6 s** (the pause lands 1–2 days later); the lever run catches up while paused in **8.5 s** |
| 7 | 0:30 | "E se compriamo un ecocardiografo? Una decisione di budget, misurata con il vostro indicatore PNE." | What-if | slider +1, "Simula 6 mesi"; then +2 | 6 months: 56 readmissions avoided (200 → 144, all from the agents), wait at Ospedale B 57,6 → 19,6 days (+2: 3,8); PNE at year end 12,7% without, 10,5% with CarePath, against Italia 11,87% | answer in 21–35 ms (computed in advance, said on screen) |
| 9 | 0:30 | "Torniamo da Maria." | Chiamate, then Pazienti | the call list of today (or `Giorno` 31); then Maria, with CarePath, "Senza CarePath" and back | the list by risk with reasons, ladder and outcome; Maria's record | with CarePath: Centro Servizi call on day 43 (delivery arranged), furosemide collected on day 45, HbA1c on day 52, no readmission; without: admitted on day 47 | under 0.1 s |
| 9c | 0:25, **optional** (D64) | "Senza CarePath, Maria torna al pronto soccorso. Il ricovero lo decide il medico; dove, lo trova l'IA in un istante." | Pazienti → Posti letto | on Maria "Senza CarePath", "Vedi il posto letto" on the day-47 admission; "Trova il posto letto"; optionally "Propone, il medico conferma" and "Trova il posto letto" again to show the doctor's confirmation, then back to "Assegna da solo" | Ospedale A, cardiology, bed 40: free now, the emergency department's own hospital, no transfer; alternatives internal medicine at Ospedale A and cardiology at Ospedale B (61 km); "Annulla" for the doctor; the assignment appears in Attività agenti | **35–60 ms** (shown on screen) |

### Scenarios 1 and 3 in short loops, and the reveal (about 1:50)

| # | Time | Trigger (it) | Screen | Operator | The app does | System |
|---|---|---|---|---|---|---|
| S1 | 0:45 | "Un'altra regione. Stesso sistema, nessuna istruzione." | Chiedi → Panoramica → Confronto | `1` (its alarm was on day 19, before the opening day, so it is already explained); approve its proposal; `f` for about 11 s; space | Ospedale A: the investigation, +2 slots proposed; on day ~44 readmissions 57 → 47, Ospedale A 54,2 → 17,1 days with the slots | ×4 20 days: **10.9 s**; catch-up **3.0 s** |
| S3 | 0:45 | "E la terza." | Mappa → Chiedi → Panoramica → Confronto | `3`; space to the alarm (it stops by itself on day 29); approve; `f` for about 10 s; space | Ospedale C alarm on day 29; +1 slot; on day ~50 readmissions 69 → 56, Ospedale C 27,6 → 15,1 days | ×1 day 23 → 29: **11 s**; ×4 20 days: **10.3 s**; catch-up **5.1 s** |
| 10 | 0:20 | "Gli agenti hanno trovato da soli i problemi nascosti, in tre regioni diverse." | Rivelazione | `v` | the three scenarios: what the agents' alarms found next to the hidden places, each marked "coincide" | under 0.1 s |

**Total: about 6:45** of targets without 9c, about 7:10 with it, with about 1:30 of it system time measured above. It is tight: if a rehearsal runs over, 9c goes first (D64), then the cut order of D45 applies (the short loops of scenarios 1 and 3 first; Rivelazione still shows all three). 9c changes nothing a cached text reads: the bed is assigned in the run without CarePath, and Bed Finder asks no model.

**Rule: approve only what the script approves, on the alarm's day, in its order** (scenario 2: the capacity proposal, the MMG notice, then Riprogrammazione at "Da sola"). The cache was warmed after exactly these actions (D63): another approval, or the same on another day, leaves the day-59 report in the template's words. **And nothing that acts on patients is approved before a scenario's alarm investigation is on screen.** An approved action changes the run from the next day, so the alarm's tools return other numbers and the cached investigation no longer matches: approving the day-23 MMG notice left scenario 2's day-33 alarm without an investigation (checked 2 Nov 2026; the two questions and the proposal still came from the cache). The cache warm-up plays the demo with no approval before the alarms. Approvals after the investigation, the capacity proposal (no effect in the run) and Riprogrammazione at "Da sola" in step 6 are safe: scenario 3 proposes a reschedule only after its own alarm (D53).

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
| Undo of an effect | "Annulla" in Attività agenti marks an action undone in the audit log; since 13 Nov 2026 (D67 work) an undone reschedule takes its patients back to their own hospital and an undone purchase turns the console back to the run without it (SPEC §7.3). A call or a notice is only marked. Not in the script: an undo changes the run, and a later cached text (a report) may then show the template | built, not in the script |
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
| Step 4.2, the same walk with the proposal approved and "Da sola" (commit `c704460`) | start 75 s; lever run catch-up 12.5 s (scenario 2), 7.1 s (1), 9.4 s (3); app at most 2.12 GB, no swap |
| Dry runs (`uv run python testing/demo_dryrun.py 10`, D63) | 10 of 10 without a stop or a fallback, the clock stopping on day 33 every time. Over ten runs in a row the laptop slows as it heats: the reset from 95 to 143 s, scenario 2 at ×4 from 18 to 29 s, the lever run's catch-up from 13 to 20 s; after 15 minutes' rest the first run is fast again, and the API's memory grows only 0.03 GB a run (2.20 to 2.29 GB over four), so it is heat, not a leak |
| Dry runs again after Bed Finder (commit `9ad8d9b`, 3 Nov 2026, step 9c included) | 10 of 10 without a stop or a fallback, the clock on day 33 every time, Maria's bed in 0.1 s each time. Heat as before: the reset from 114 to 157 s, scenario 2 at ×4 from 23 to 37 s, its catch-up from 15 to 23 s; the API at 2.25–2.39 GB, no growth |
| Step 9c, Bed Finder for Maria's day-47 admission (3 Nov 2026) | 35–36 ms in the engine, 60 ms through the API on day 48 (AC18 holds each of its 20 admissions under 3 s) |

**For rehearsals in a row (AC9):** mains power, the best-performance power mode, nothing else running, and a few minutes' pause between runs; step 6 at ×4 then takes about 18 s, up to about 30 s on a hot laptop.
