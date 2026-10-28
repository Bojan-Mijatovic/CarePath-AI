# CarePath AI

AI agents that check every day whether 10,000 chronic patients in ATS della Val Padana follow their care plan (PAI), explain why they drift and act on it. Workshop PoC on synthetic data; everything runs locally, offline and free.

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

   Open <http://127.0.0.1:8000>: the console shows "Giorno N" going up every 2 seconds and "connesso" in the top bar.

## Console development

The console is React 19 + TypeScript on Vite (decision D13). For hot reload, run the API and Vite side by side:

```powershell
uv run carepath-api                      # terminal 1: API on :8000
cd src/ui; fnm exec --using=24 npm run dev   # terminal 2: console on :5173
```

Open <http://127.0.0.1:5173>. Vite forwards `/api`, including the `/api/stream` WebSocket, to the API. Every API path is under `/api` (spec §10). No CDN and no external URLs in the console: it must work offline. `npm run lint` runs oxlint.

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
- Commit directly to `main`, no feature branches (decision D20). Pull and run `uv run pytest` before every push; another role reviews a step's commits before the step counts as done.
- Done means: reviewed, tests pass, its acceptance criterion is met, it works in the end-to-end flow.
