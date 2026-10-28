# CarePath AI

AI agents that check every day whether 10,000 chronic patients in ATS della Val Padana follow their care plan (PAI), explain why they drift and act on it. Workshop PoC on synthetic data; models and data run locally and everything is free.

- What we build and why: [docs/CarePath-AI-Solution-Plan.pdf](docs/CarePath-AI-Solution-Plan.pdf)
- How we deliver it, phase by phase: [docs/DELIVERY_PLAN.md](docs/DELIVERY_PLAN.md)
- Demo screens: [docs/CarePath-AI-UI-demo-srpski.html](docs/CarePath-AI-UI-demo-srpski.html)

## Repository layout

| Path | Contents | Owner |
|---|---|---|
| `brief/` | team charter, problem brief | R5 |
| `spec/` | `SPEC.md` contracts, pathway JSON, PDTA texts | R5 |
| `src/sim/` | simulator, scenarios, Maria | R1 |
| `src/engine/` | state engine, DuckDB views, Risk, what-if, PNE forecast | R2 |
| `src/agents/` | agents, tools, LLM gateway and cache, action service | R3 |
| `src/api/` | FastAPI and the `/stream` WebSocket | R4 |
| `src/ui/` | console: React + TypeScript on Vite; the build is served by the API | R4 |
| `testing/` | tests, benchmark, fixtures, LLM evaluation | all |
| `demo/` | LLM cache, scenario truth, script, runbook | R4, R5 |

## Getting started (Windows)

Takes about 15 minutes plus model downloads. No admin rights needed.

1. **Install uv, Ollama and fnm** (fnm manages Node versions per project)

   ```powershell
   winget install --id astral-sh.uv -e
   winget install --id Ollama.Ollama -e
   winget install --id Schniz.fnm -e
   ```

2. **Open a new terminal.** A terminal opened before step 1 does not see the new PATH. In VS Code, restart the whole app, or refresh the current terminal:

   ```powershell
   $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
   ```

3. **Install Python and the project**

   ```powershell
   uv python install 3.12
   uv sync
   ```

4. **Pull the models** (decision D11 in the delivery plan; about 21 GB, both fit in RAM together):

   ```powershell
   ollama pull qwen3:30b-instruct
   ollama pull qwen3:4b-instruct
   ```

   Use the `-instruct` tags. The plain `qwen3:4b` and `qwen3:30b` tags are thinking models: they reason at length before answering, which is far too slow on a CPU. Large downloads sometimes stall; run `ollama pull` again and it resumes.

   Ollama starts its server on `127.0.0.1:11434` by itself. Do not run `ollama serve` when the tray app is running; the port is already taken.

5. **Install Node 24 and build the console**

   ```powershell
   fnm install 24
   cd src/ui
   fnm exec --using=24 npm install
   fnm exec --using=24 npm run build
   cd ../..
   ```

   `src/ui/.node-version` pins Node 24. The system Node (20.x on our laptops) is too old for Vite 8.

6. **Check that everything works**

   ```powershell
   uv run pytest
   uv run carepath-api
   ```

   Open <http://127.0.0.1:8000>: the console opens on Maria's story; "Avvia la simulazione", then an envelope, leads to Panoramica, where "Giorno N" goes up every 2 seconds from day 23 and "connesso" shows in the top bar. The API needs about 30 s after start-up to prepare the runs; an envelope chosen earlier shows a 503.

## Commands

Everything runs with `uv run` from the repository root.

| Command | What it does | Step |
|---|---|---|
| `uv run pytest` | all tests (about 3 minutes; the simulation tests run full years) | — |
| `uv run python testing/fixtures/scenario.py` | rewrites the JSON fixtures of every contract (`testing/fixtures/README.md`) | 1.23 |
| `uv run python testing/benchmark/questions.py` | rewrites the benchmark questions and their expected answers from the tools | 1.24 |
| `uv run pytest -m acceptance` | only the acceptance tests AC1–AC19 | 1.7 |
| `uv run carepath-api` | API and built console on <http://127.0.0.1:8000> | 0.7 |
| `uv run carepath-db s2_agents` | empty run database `runs/s2_agents.duckdb` with every SPEC table | 0.9 |
| `uv run carepath-reference-data [--refresh]` | downloads ISTAT and ATS sources, rebuilds `src/sim/data/*.csv` and the map `src/ui/assets/comuni.geojson` | 1.10–1.13 |
| `uv run carepath-sim s2_baseline [--days 365]` | simulates one run into `runs/` and reports the time per day; the scenario comes from the run id | 1.15–1.17 |
| `uv run python -m sim.calibration` | refits the two readmission parameters against the PNE target | 1.16 |
| `uv run python -m engine.risk` | retrains the risk model on seed 7 and rewrites `models/risk_hf_lombardia_v1.json` (about 30 s; same bytes every time) | 2.3 |
| `uv run python -m engine.story` | rewrites Maria's recorded story `demo/story/p_00001_s2_baseline_day62.json` | 2.1 |
| `uv run python -m sim.truth` | rewrites `demo/truth/scenario_<n>.json` from the scenario files | 1.18 |
| `uv run python -m engine.pathway` | regenerates `spec/pathways/pathway.schema.json` from the model | 1.3 |
| `uv run jupyter lab --notebook-dir testing/notebooks` | population, calibration, pattern-proof and risk notebooks | 1.14, 1.16, 1.21, 2.3 |
| `uv run python docs/build_pdf.py` | exports `docs/DELIVERY_PLAN.md` to PDF with Edge | — |

Data sources, licences and every assumption of the simulator: [src/sim/README.md](src/sim/README.md).

## Console development

The console is React 19 + TypeScript on Vite (decision D13). For hot reload, run the API and Vite side by side:

```powershell
uv run carepath-api                      # terminal 1: API on :8000
cd src/ui; fnm exec --using=24 npm run dev   # terminal 2: console on :5173
```

Open <http://127.0.0.1:5173>. Vite forwards `/api`, including the `/api/stream` WebSocket, to the API. Every API path is under `/api` (spec §10). `npm run lint` runs oxlint.

The API runs the demo itself (step 2.1): at start-up it replays the six runs (3 scenarios × 2 arms) to day 23 into `runs/`, which takes about 30 s; until then the data endpoints answer 503. An envelope puts its scenario on screen and starts it at ×1; `POST /api/sim/pause`, `/api/sim/speed`, `/api/sim/jump/{day}` and `/api/sim/reset` control it, and `/api/kpi`, `/api/sankey`, `/api/map`, `/api/worklist`, `/api/patients/{id}` and `/api/actions` read the run on screen (SPEC §10). Maria's story is served from `demo/story/` (D35). Restart `carepath-api` after a change to the API or the engine; it does not reload. Screens so far: `#storia` (Maria's story), `#buste` (envelopes), `#panoramica` (overview with the agent feed); the switch in the top bar changes between Italian and English (D30).

## Measuring models on your machine

Every team laptop runs the same evaluation (delivery plan, step 0.4), with nothing else running:

```powershell
uv run python testing/llm_eval.py qwen3:30b-instruct qwen3:4b-instruct
```

It checks Italian texts for wrong facts, tool calls against the schema, and a multi-step investigation like the Investigator's. Results go to `testing/results/` (not committed). Add `--investigate-only` to rerun just the investigation.

On a laptop without an NVIDIA GPU, models run on the CPU and are too slow for live answers. That is expected: demo answers are generated in advance and replayed from `demo/cache/` (delivery plan, principle 3).

## Working rules

- Every task starts from `spec/SPEC.md`. Do not change a contract without agreeing it at the sync.
- Numbers and facts come from code; the LLM only phrases them.
- Commit directly to `main`, no feature branches (decision D20). Pull and run `uv run pytest` before every push; Bojan approves each step's code before it is committed (D26).
- Done means: reviewed, tests pass, its acceptance criterion is met, it works in the end-to-end flow.
