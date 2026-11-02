# CarePath AI — Technology stack

Every technology, tool and AI model the PoC uses, with versions, licences and the decision behind each choice. Sources: [Delivery Plan](DELIVERY_PLAN.md) §3, §10 and §11 (decision register), [SPEC.md](../spec/SPEC.md), [pyproject.toml](../pyproject.toml), [src/ui/package.json](../src/ui/package.json).

| | |
|---|---|
| Constraint | Zero cost; everything free and open source. Models, data and the LLM cache run on the laptop (Delivery Plan §10, D25) |
| Versions | as installed on the demo machine `BMIJATOVICW` on 29 Oct 2026; `uv.lock` and `package-lock.json` pin the exact builds |
| Last updated | 2 Nov 2026 |

## 1. Architecture at a glance

```
 src/sim  ──events──▶  src/engine  ──views, tools──▶  src/agents  ──▶  action service
 (numpy, pandas)       (DuckDB, XGBoost)              (Python + Ollama)       │
                              │                                               │
                              └────────────▶  src/api (FastAPI, WebSocket) ◀──┘
                                                       │  /api, /api/stream
                                                       ▼
                                              src/ui (React 19 + TypeScript, Vite)
```

- The **simulator** generates synthetic events for 10,000 heart-failure patients, day by day.
- The **engine** keeps the pathway state, the KPI views and the risk score in one DuckDB file per run.
- The **agents** read only through tools (SPEC §6) and call the LLM only through the gateway (SPEC §8).
- The **API** runs the six demo runs, serves REST under `/api`, pushes ticks on `/api/stream` and serves the built console.

Design rule behind the stack: **code computes, the LLM phrases** (Delivery Plan §2). Numbers, rankings and decisions come from rules, SQL and XGBoost; the LLM only writes sentences around them.

## 2. Hardware and operating system

| Item | Value |
|---|---|
| Reference laptop (every team laptop, D12) | Intel i7-1355U (10 cores, 12 threads), 32 GB RAM, Intel Iris Xe |
| GPU | None (D12). All models run on the CPU |
| Operating system | Windows 11 Pro on the demo machine |
| Demo machine | `BMIJATOVICW`, HP EliteBook 840 G10; the backup is a laptop of the same model with the same models and a hash-checked copy of the cache (D12) |

## 3. Backend (Python)

| Technology | Version | Used for | Licence |
|---|---|---|---|
| Python | 3.12 | every backend package | PSF |
| uv | 0.13.5 | Python install, virtual env, dependencies, `uv run` | MIT / Apache 2.0 |
| hatchling | — | builds the `sim`, `engine`, `agents`, `api` packages | MIT |
| numpy | 2.5.4 | vectorised simulator and engine (no per-patient loops, AC2) | BSD |
| pandas | 3.1.0 | event frames, reference data | BSD |
| DuckDB | 2.0.0 | one database file per run in `runs/`; tables and views of SPEC §3 and §5 | MIT |
| XGBoost | 3.4.1 | risk model: 30-day unplanned admission, drivers from TreeSHAP (`pred_contribs`), D37 | Apache 2.0 |
| scikit-learn | 1.9.1 | `roc_auc_score` during training and in notebooks only | BSD |
| Pydantic | 2.14.1 | pathway model and schema, API shapes, LLM output schemas | MIT |
| FastAPI | 0.162.0 | REST API under `/api`, WebSocket `/api/stream`, static console | MIT |
| uvicorn | 0.54.0 | ASGI server (`uv run carepath-api`, port 8000) | BSD |
| httpx | 0.28.1 | HTTP client under the Ollama library; timeouts in the gateway | BSD |
| ollama (Python) | 0.6.3 | client for the local Ollama server, used only in `src/agents/llm.py` | MIT |

Entry points (`pyproject.toml`): `carepath-api`, `carepath-db`, `carepath-sim`, `carepath-reference-data`. All commands: [README](../README.md#commands).

## 4. Console (frontend)

| Technology | Version | Used for | Licence |
|---|---|---|---|
| React | 19.3 | console screens (D13) | MIT |
| TypeScript | 6.0 | console code | Apache 2.0 |
| Vite | 8.3 | dev server on 5173 with proxy to `/api`, production build to `src/ui/dist` | MIT |
| @vitejs/plugin-react | 6.1 | React support in Vite | MIT |
| oxlint | 1.88 | `npm run lint` (React, TypeScript and oxc rules) | MIT |
| Node.js | 24 LTS | build tooling; pinned in `src/ui/.node-version` (Node 20 is too old for Vite 8) | MIT |
| fnm | 1.38.1 | Node version manager (`fnm exec --using=24 npm.cmd ...`) | GPL-3.0 (tool only, not shipped) |

- **Language:** Italian and English with a switch, Italian by default (D30). Own i18n module (`src/ui/src/lib/i18n`), no library.
- **Map:** ISTAT comune boundaries as local GeoJSON (`src/ui/assets/comuni.geojson`), no basemap and no tile server (D16).
- **Charts and Sankey:** plain SVG in React components, no chart library (D40, proposed). Step and drug names come from `GET /api/pathways/{id}`, not from console code (AC17).
- **Fonts:** system fonts for now; IBM Plex (OFL), bundled locally, is planned (Delivery Plan §10). No font CDN.

## 5. AI and LLM

### 5.1 Runtime and models

| Item | Value |
|---|---|
| LLM runtime | Ollama 0.40.11, tray app on `127.0.0.1:11434` (MIT) |
| Main model | `qwen3:30b-instruct`: Qwen 3 30B-A3B, mixture of experts with 3B active parameters, 18 GB, about 10.8 tok/s on CPU. Writes every cached output: Investigator, Pathway Builder, Rule Advisor, Reporter, Verifier wording (D11) |
| Small model | `qwen3:4b-instruct`: 2.5 GB, about 14.3 tok/s. Short text that code fills from templates, and the Italian-to-English translation of cached texts during warm-up (D11, D31) |
| Licence | Apache 2.0, both |
| Backup | `nemotron-3.5-lightning:30b` (NVIDIA Open Model License). Not kept on disk; pulled again only if both Qwen models fail (D11) |
| Not allowed | the plain `qwen3:4b` and `qwen3:30b` tags: they are thinking models and far too slow on CPU |

Why these models: seven free local models were measured on Italian text, tool calls and a full investigation (Delivery Plan §3.1). The 30B MoE was the only one with every Italian text right and is faster than the dense 7B–14B models. No model is fast enough for a live investigation on these laptops (best: 243 s), so the demo is cache-first.

### 5.2 LLM gateway (`src/agents/llm.py`, SPEC §8)

| Rule | Value |
|---|---|
| Entry point | `complete(agent, prompt_version, messages, *, tools, schema, model)`, the only way agents call a model |
| Sampling | temperature 0, seed 42, `think: false` |
| Output | Pydantic schema → Ollama structured output; validated; 1 retry that tells the model what was wrong |
| Modes | `live` (warm-up, 600 s timeout), `cache_first` (development, rehearsals, 20 s), `cache_only` (demo start, D14) |
| Cache | `demo/cache/<agent>/<key>.json`, key = SHA-256 of agent, model, prompt version, messages, tools, schema. Only what the demo shows, listed in `demo/cache/manifest.json` (D17) |
| Fallback | no valid answer raises `LLMUnavailable`; the agent uses its code template. The Investigator has no template, so the cache completeness check guards it (C10) |
| Log | one JSON line per call in `logs/llm.jsonl` (replaces Langfuse, D15) |

### 5.3 Agents

Plain Python with tool calling; no LangGraph (D15). Agents read only through the tools of SPEC §6 and never run free SQL. Only the action service changes state. Agents never import the simulator and cannot reach `scenario_truth` (tested in `testing/test_truth_isolation.py`).

| Agent | What decides | What the LLM does |
|---|---|---|
| Monitoring | pathway rules and the regional wait alarm (C21) | nothing |
| Risk | XGBoost | nothing |
| Intervention | rules and autonomy levels (SPEC §7) | rationale and call-script wording, from the cache or the template |
| Daily Worklist | SQL view `worklist_today`, ranked by risk | nothing; reasons filled by code |
| Investigator | tools choose the data | plans tool calls and writes the explanation (cached) |
| Verifier | repeats each claim's tool call and checks numbers, comparisons and scope (C33) | nothing; corrections filled by code (D55, proposed) |
| Rule Advisor, Reporter, Pathway Builder | code and rules | wording only (cached); gated extensions or option B |

### 5.4 Model evaluation

| Tool | Used for |
|---|---|
| `testing/llm_eval.py` | Italian text, tool calls and investigation per model and prompt version; results in `testing/results/` |
| `testing/benchmark/` | 10 benchmark questions × 3 scenarios with expected answers from the tools (AC6) |

## 6. Data

| Source | Used for | Licence |
|---|---|---|
| ISTAT list of comuni | territory of ATS della Val Padana | CC BY 4.0 |
| ISTAT population by age and sex, 1 Jan 2025 | synthetic population | CC BY 4.0 |
| ISTAT generalised boundaries, 1 Jan 2026 | console map | CC BY 4.0 |
| ATS Val Padana list of comuni per ASST | comune → ASST | public document, names only |
| Agenas PNE (HF indicators, Italy 2024) | calibration target for 30-day readmissions | public document |

- All patient data is **synthetic**. Hospital names are invented; the geography is real.
- Medical codes (ICD-9-CM, ATC, LOINC) in the pathway files are demo values (D28).
- Full list with URLs: [src/sim/README.md §5](../src/sim/README.md).

Tools for reading the reference data (dev only): **pyshp** 3.1.6 (shapefiles, MIT) and **pyproj** 3.8.0 (UTM 32N → WGS84, MIT).

## 7. Testing and quality

| Tool | Version | Used for |
|---|---|---|
| pytest | 9.1.1 | all tests in `testing/`; marker `acceptance` for AC1–AC19, timers for the performance ACs |
| jsonschema | 4.26.0 | checks the HF pathway file against `spec/pathways/pathway.schema.json` (`testing/test_pathway_model.py`) |
| JupyterLab | 4.6.4 | population, calibration, pattern-proof and risk notebooks (`testing/notebooks/`) |
| matplotlib | 3.11.2 | charts in the notebooks |
| oxlint | 1.88 | console lint |

Determinism (AC14): every random draw comes from a generator seeded by `(run seed, component)`; tools, views and the API round every DOUBLE (SPEC §2), because DuckDB's parallel aggregation of DOUBLE is not bit-stable.

## 8. Development tools and AI assistants

| Tool | Used for |
|---|---|
| Git 2.55, GitHub private repo | source control; every commit goes directly to `main` (D20) |
| Visual Studio Code | editor |
| Claude Code | main AI coding assistant; its rules are in [CLAUDE.md](../CLAUDE.md); useful prompts and AI-assisted decisions go into [PROMPT_LOG.md](PROMPT_LOG.md) |
| GitHub Copilot | used once for a project assessment that Claude Code then checked (PROMPT_LOG, 27 Oct 2026) |
| winget | installs uv, Ollama and fnm on Windows ([README](../README.md#getting-started-windows)) |
| markdown (Python) 3.11.2 + Microsoft Edge | `docs/build_pdf.py` exports the Delivery Plan to PDF |
| OBS Studio | backup video of a full demo run (Delivery Plan step 4.5) |

AI assistants are development tools only. They are not part of the product, and no patient data, real or synthetic, is sent to them as product input.

## 9. Not used, and why

| Not used | Instead | Reason |
|---|---|---|
| Cloud LLM APIs | local Ollama | zero cost, no patient data to external APIs (Solution Plan §14) |
| LangGraph | plain Python agents | fewer dependencies (D15) |
| Langfuse | `logs/llm.jsonl` | needs Docker and several services (D15) |
| Angular, Streamlit | React | prototype ports one-to-one; less boilerplate (D13) |
| Text-to-SQL | tools | out of scope (Solution Plan §4); agents never write SQL |
| Map tiles, live OSM routing | local GeoJSON, precomputed distances | no tile server and no live calls (D16) |
| GPU | CPU and the LLM cache | no GPU in the team (D12) |
| pm4py | — | optional, notebook only; not needed for the demo |
| Voice input | typing and the 10 benchmark questions | dropped (Delivery Plan §10) |
