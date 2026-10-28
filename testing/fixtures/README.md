# Fixtures

Delivery plan step 1.23. Data in the shape of every contract in [SPEC](../../spec/SPEC.md), from one scenario, so that tools, API and screens can be built and tested before the code that produces the data exists.

**Scenario:** scenario 2, seed 42, 10,000 patients, days 0–62 (the demo ends near day 62, D21), both arms. In the agents arm, two actions are written the way the action service will write them (step 2.12): the Centro Servizi call to Maria on day 31 (executed, level 3) and an echo reschedule at Ospedale B on day 35 (proposed, level 2). Their rationales are templates filled by code.

```
uv run python testing/fixtures/scenario.py   # rewrite every JSON file here (about 15 s)
```

`testing/test_fixtures.py` rebuilds the scenario and fails if a committed file differs, if a file is missing or extra, or if a shape drifts from the SPEC. After a change to the simulator, the engine or a contract, run the command above and commit the files with the change (SPEC §0).

## Run databases (not committed)

`scenario.build_runs(dir)` writes `s2_baseline.duckdb` and `s2_agents.duckdb`, with every table of SPEC §3, §5 and §7 filled. In pytest, use the session fixture `fixture_scenario` (`testing/conftest.py`): it returns `(runs_dir, files)`. Tools open the runs with `connect_for_tools(run_id, runs_dir=runs_dir)`, as in step 1.24.

## JSON files

| File | Contract | Values |
|---|---|---|
| `api/kpi_ats_<run>.json` | `GET /api/kpi?level=ats`: `kpi_daily` rows, days 0–62 (SPEC §5.2) | real |
| `api/kpi_s2_agents_day62.json` | `kpi_daily`, every level and key on day 62 | real |
| `api/patient_p_00001_<run>.json` | `GET /api/patients/p_00001` (SPEC §10, C15), both arms for the with/without toggle | real |
| `api/actions_s2_agents.json` | `GET /api/actions`: `actions` rows (SPEC §7.1) | written by the builder, not by the action service; the reschedule's numbers and evidence come from the tools; the call's evidence is a shape example, since no tool answers for a single patient |
| `api/sankey_s2_agents.json` | `GET /api/sankey`: `sankey_flows` on day 62 (SPEC §5.2, C15) | real |
| `api/map_s2_agents.json` | `GET /api/map`: `map_comuni` columns on day 62 | **stand-in**: `adherence_pct` is the comune's `on_track_pct`, `risk_mean` and `high_risk_patients` are 0 (Risk, step 2.3), `alarm` is false; the meaning comes in step 2.2 (SPEC Q7) |
| `api/worklist_s2_agents.json` | `GET /api/worklist`: `worklist_today`, 20 rows | **stand-in**: ranked dropped first, then by days late; `risk_score` 0, `script` and `outcome` null; the ranking comes in step 2.4 (SPEC Q7) |
| `stream/tick.json` | `tick` on day 35, `kpi` as in C15 | real |
| `stream/alert_patient.json`, `stream/alert_regional.json` | `alert`, Maria on day 31 and Ospedale B on day 35 | numbers real (the regional one from the tools); when Monitoring raises them is step 2.8 |
| `stream/action.json` | `action`: Maria's call | as `actions` |
| `stream/investigation.json` | `investigation`, two steps | tool calls and numbers real; the wording is a template, not the Investigator (step 2.9) |
| `tools/wait_by_hospital.json`, `tools/free_slots.json`, `tools/error.json` | tool result envelope and error (SPEC §6) | real: `agents.tools` called on the live run on day 35 (`free_slots` sees that day's bookings, so a finished run gives other numbers for day 35) |

Patient alerts name `p_00001`, not "Maria R.": the data has no names.
