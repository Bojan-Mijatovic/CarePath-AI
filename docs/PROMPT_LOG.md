# Prompt log

Useful prompts and important decisions made with AI assistants (Definition of done, delivery plan §11). Newest first.

| Date | Who | Tool | Prompt or task | Outcome |
|---|---|---|---|---|
| 27 Oct 2026 | R5 | GitHub Copilot, then Claude Code | Copilot: "assess the project as it stands". Claude Code: "check every claim in that assessment against the documents and the code", then "change what is needed and align the documents" | About 80% of Copilot's claims held. Wrong or overstated: "the critical path has not started" (it was day 2 of week 1), "live agents are a recording" (rules and XGBoost run live; only LLM text is replayed), and "AC1 will almost surely pass" (pattern 3 had no tool). Reproduced: DuckDB `avg(DOUBLE)` over 2,000,000 rows with 8 threads gave 12 different results in 12 runs; rounded or single-threaded gave one. Resulting changes: SPEC C7–C10 (rounding, tool determinism test, `measure` and segments for pattern 3, budgets, cache completeness check); delivery plan D20 (commit to `main`, decided), D21–D24 (pacing, budgets, Pathway Builder to option B, honest opening; proposed), steps 0.12, 1.24, 2.1, 2.5, 2.11, 2.24, 4.1–4.3, 4.9 |
