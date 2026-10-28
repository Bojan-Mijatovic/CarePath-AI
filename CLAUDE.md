# CLAUDE.md — how Claude works on CarePath AI

Rules for the AI assistant in this repo. They come from the [Solution Plan](docs/CarePath-AI-Solution-Plan.pdf), the [Delivery Plan](docs/DELIVERY_PLAN.md) and [SPEC.md](spec/SPEC.md); this file does not add product decisions of its own. If a rule here ever disagrees with those documents, the documents win and this file gets fixed.

## 1. Sources and precedence

1. **Solution Plan** (22 Oct 2026): what we build and why. It is the source of truth.
2. **Decision register** (Delivery Plan §11, D11 onward): a decision marked *Decided* overrides the Solution Plan on that point. Current overrides: models are `qwen3:30b-instruct` and `qwen3:4b-instruct`, not 7–8B and 14B (D11); the console is React, not Angular or Streamlit (D13); demo LLM output is cache-only (D14); all work goes directly to `main` (D20); Pathway Builder is in option B (D23); the demo may be online (D25); the console is Italian and English, with cached LLM texts written in Italian and translated by the 4B model during the warm-up (D30, D31). *Proposed* decisions are the working assumption, but not yet binding (none open on 28 Oct 2026).
3. **Delivery Plan**: how and when, step by step, with owners and gates.
4. **SPEC.md**: the contracts. Nothing is built against an interface that is not in it.
5. **UI prototype** ([CarePath-AI-UI-demo-srpski.html](docs/CarePath-AI-UI-demo-srpski.html)): screen layout and demo steps 1–10.

When two sources conflict, I say so and point to both places. I do not quietly pick one.

## 2. Before every task

- Find the step in the Delivery Plan (for example `2.7`), its owner role (R1–R5), its acceptance criterion and its "done when".
- Read the SPEC section for every contract I touch. If the contract is missing or unclear, I stop and propose a SPEC change instead of inventing a shape.
- Check the current phase and its gate. I do not start work from a later phase or a gated extension (Verifier, Rule Advisor, Daily Worklist, option B, Bed Finder) before its gate has passed, unless the user asks.
- If the task is outside scope (Solution Plan §4: FSE 2.0 integration, text-to-SQL, BPCO, voice and similar), I say so before writing code.

## 3. Product rules I never break

These come from the design principles and guardrails. Code that breaks one needs a decision-register entry first.

1. **Code computes, the LLM phrases.** Numbers, names, dates, rankings and choices of action come from rules, SQL views or XGBoost. An LLM only writes sentences around values it received from a tool or a template. Every model in the evaluation made at least one factual slip (Delivery Plan §3.1), so this rule carries the most weight.
2. **No diagnosis and no therapy change**, in any code path, prompt or text.
3. **One writer.** Agents only read, through the tools in SPEC §6. Only the action service changes state, after the autonomy and guardrail checks. Every action has a rationale and evidence, goes to the audit log and can be undone.
4. **No free SQL from agents.** The Investigator uses tools only.
5. **`scenario_truth` is unreachable for agents.** Only tests (AC13) and the Rivelazione screen read it. Tools get their database only through `engine.db`: `connect_for_tools` for a finished run (read-only, no file access, locked), and in the simulation process a cursor of the tick's locked connection behind a SELECT-only guard (D29). Agent code never imports `sim`, and `testing/test_truth_isolation.py` enforces both.
6. **Disease is configuration.** No `if pathway == "hf"` in code. Every tool, view and screen takes `pathway_id` (AC17).
7. **Local and zero cost.** Models, data and the cache run on the laptop; no patient data goes to an external API; no telemetry, no paid tier. The network may be used for downloads and during the demo (D25). A new dependency needs a free licence, and I name it in the commit message.
8. **Synthetic data only.** Hospital names are invented, the geography is real. Prompts carry aggregates and the top N patients, never the whole database. Logs contain nothing that could not leave the system if the data were real.
9. **Determinism.** Every random draw comes from a generator seeded by `(run seed, component)`. Same seed, same run, byte for byte (AC14). No wall-clock time or unseeded randomness in the simulator or the engine. Tools, views and the API round every DOUBLE as in SPEC §2, because DuckDB's parallel aggregation of DOUBLE is not bit-stable.
10. **Language.** Code, data, identifiers and docs are in English. Every string a user sees (UI, reports, call scripts, rationales) exists in Italian and English, Italian by default; the demo runs in Italian (D30). The Italian colleague reviews the Italian before rehearsals.

## 4. LLM work

- Every call goes through the gateway (`src/agents/llm.py`, SPEC §8). No direct `ollama` calls in agent code.
- Models are as in D11: `qwen3:30b-instruct` for every cached output (Investigator, Pathway Builder, Rule Advisor, Reporter, Verifier wording) and `qwen3:4b-instruct` only for short text that code fills from templates. Use the `-instruct` tags and always send `think: false`. Other models only after a new D11 decision. I never pull Nemotron again unless both Qwen models fail.
- Sampling: temperature 0, fixed seed, JSON schema through structured output, validation, 1 retry.
- A changed prompt means a new `prompt_version`. The old cache stays valid for the old version.
- The demo starts in `cache_only` (D14). Warm-up runs use `live` with the 600 s timeout. A feature that needs a live LLM call in the demo flow is a design error.
- The cache holds only what the demo shows, listed in `demo/cache/manifest.json` (D17). Every other rationale or call script is the template filled by code, and every LLM-backed text must have that template. The exception is the Investigator, whose only fallback is the cache (Solution Plan §8); the cache completeness check (SPEC §8) guards it after every change to the simulator, engine, tools or prompts.
- AC5 is measured from the cache (D18). I do not optimise for a live Investigator on CPU.
- A prompt counts only if it is measured. Quality claims about prompts or models go through `testing/llm_eval.py` or the benchmark (AC6), with the result stored per prompt version. I do not judge a prompt from one good-looking answer.
- On these CPU laptops one investigation takes about 4 minutes. Long evals and warm-ups run in the background. I note that speed varies by about ±40% with load and power mode.

## 5. Contracts, decisions and documents

- Until `spec-v1` is tagged, I may propose SPEC edits in drafts. After the freeze, a contract change needs agreement at a sync, a decision-register entry, a SPEC version bump and updated fixtures in the same commit. I prepare the change; the team agrees it.
- I mark a decision *Decided* only when the user says it is decided. Otherwise I add it as *Proposed* with the reason and the evidence.
- When one document changes, I check the others for the same fact (Delivery Plan, SPEC, README) and update them together, so there is no contradiction between them.
- Plan and SPEC text is plain English: short sentences, concrete numbers, links to sections, no filler. I keep "Last updated" current.
- Useful prompts and important decisions made with AI go into the prompt log (`docs/PROMPT_LOG.md`, created on first entry), as the Definition of done requires.

## 6. Code and tests

- Repo layout as in the README: `src/{sim,engine,agents,api,ui}`, `testing/`, `demo/`, `spec/`. Each Python package is installed by `uv sync`; `uv run` for everything.
- Python 3.12, numpy, pandas and DuckDB, vectorised. No per-patient Python loops on the hot path (AC2: one day for 10,000 patients in under 1 s).
- Every API path is under `/api`. The WebSocket envelope follows SPEC §10.
- The console is React 19 + TypeScript on Vite with Node 24 through fnm (`fnm exec --using=24 npm ...`). `npm run lint` (oxlint) passes. The prototype is the layout reference.
- Tests are written from the acceptance criteria. Acceptance tests carry `@pytest.mark.acceptance`; performance ACs have timers. Contract work gets fixtures in `testing/fixtures/`, so no role waits on another.
- I match the surrounding code: its naming, comment density and idioms. No speculative abstractions and no LangGraph or Langfuse (D15).

## 7. Done, reporting and git

- **Done** means: tests pass, the AC is met or measured, it works in the end-to-end flow, the prompt log is updated, and the user has approved the code (D26). I can confirm the first three.
- Workflow per step: I name the step, build it, run the tests and show the result; the user approves the code; then I commit, push to `main` and name the next step.
- I report what I ran and what I did not. If a test fails or I skipped a check, I say so with the output.
- Git (D20): all work is committed directly to `main`; no feature branches and no pull requests. Before a push I pull and run `uv run pytest` (plus `npm run lint` for console changes). I commit or push only when asked, never force-push `main` and never skip hooks. Commit messages say what changed.
- Destructive or hard-to-reverse actions (deleting models, cache files, `demo/truth/`, branches) only after confirmation.

## 8. Demo protection

Everything serves the demo running 10 out of 10 times (AC9). In practice:

- I do not change Maria's trajectory (`p_00001`, days 31, 33, 40 and 47) or the scenario patterns without the owner's (R1) agreement, and AC14 must still pass.
- I keep the cut order from Delivery Plan §8 (Solution Plan §4 with D22 and D23): Bed Finder → option B, including the Pathway Builder (manual JSON stays) → optional agents → parallel what-if (precomputed demo lever stays) → map (comune table stays). When time is short I suggest cutting, not stretching.
- Demo pacing and performance budgets are in SPEC §9 (D21, D22). AC2 alone does not prove the demo works.
- From week 4, feature freeze: only bug fixes.

## 9. Environment notes (Windows team laptops)

- A terminal opened before an install does not see the new PATH. Refresh it with `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`.
- Ollama runs from the tray on `127.0.0.1:11434`. Do not start `ollama serve` a second time.
- From a non-interactive shell, `fnm exec` finds npm only as `npm.cmd` (`fnm exec --using=24 npm.cmd run dev`).
- PowerShell is 5.1: no `&&`, no `?:`. Write files with an explicit `-Encoding utf8`.
- No GPU (D12). The demo machine and the backup laptop have identical models and a hash-checked copy of the cache.
