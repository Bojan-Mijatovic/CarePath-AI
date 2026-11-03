# demo

Owners: R4, R5. Everything needed on the day of the demo.

- `cache/`: pre-generated LLM outputs, keyed by agent, model, prompt version and input hash. `cache/manifest.json` lists every output the demo shows (delivery plan, D17). `testing/test_cache_complete.py` plays the demo in cache-only mode and fails on any miss (spec §8); run it after every change to the simulator, engine, tools or prompts, and before every rehearsal.
- `story/`: Maria's story for demo step 1, recorded from the baseline run (`uv run python -m engine.story`, D35).
- `truth/`: `scenario_truth` per scenario. Agent tools must never read this folder (step 1.18).
- `slides/`: the system on one slide for the presentation, `how-it-works-it.svg` and `-en.svg` (D66); SVG, so PowerPoint and Google Slides take it as it is.
- `SCRIPT.md`: the demo script (step 2.24): trigger sentences, operator hotkeys, timings measured on the API.
- `whatif/`: the what-if grids (D48), full runs computed in advance by `uv run python -m engine.whatif` (about 72 min).
- `SHA256SUMS`: the hashes of `cache/` and `whatif/` (step 4.3). On the backup laptop, after a pull: `uv run python testing/cache_hashes.py --check`, then `uv run pytest -m demo`. After any new warm-up or grid, write it again with `uv run python testing/cache_hashes.py`.
- The runbook and the backup video are added in week 4.
