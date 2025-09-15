# SWE-bench Agent Evaluation Harness

This repository contains the planning docs for an agent harness that evaluates coding models on a curated subset of SWE-bench.

Documents
- `plan.md` — Implementation Plan (i1–i4), architecture, model plan, instance policy, compute/reliability, deliverables.
- `prd_requirements.md` — System Requirements (PRD): functional/non-functional requirements, interfaces, token/cost accounting, runbook, acceptance criteria.
- `codex_agent_instructions.md` — Operating guidelines for the agent within this repo.

Quick Start (i1 baseline)
- Select easy Lite instances: `python3 scripts/select_i1_from_hf.py`
- Generate baseline predictions: `python3 scripts/make_baseline.py --run_id baseline-i1-lite`
- Evaluate (requires SWE-bench evaluator): `scripts/run_evaluator.sh runs/baseline-i1-lite/predictions.jsonl baseline-i1-lite`

Run Predictions (patch-mode)
- Install deps: `python3 -m pip install -r requirements.txt`
- Ensure `credentials.txt` contains your keys (CHUTES_API_KEY, optional OPENROUTER_API_KEY). Optionally set `CHUTES_BASE_URL` if your endpoint differs.
- Run orchestrator (i1 models): `python3 scripts/run_predictions.py --run_id i1-lite-chutes`
- Validate JSONL: `python3 scripts/validate_predictions.py runs/i1-lite-chutes/predictions.jsonl`
- Evaluate: `scripts/run_evaluator.sh runs/i1-lite-chutes/predictions.jsonl i1-lite-chutes`

Quick Notes
- Concurrency: `WORKERS` (default 12) controls prediction workers; `EVAL_WORKERS` (default 4) controls evaluator `--max_workers`.
- Provider usage: prefer Chutes (≈2,000 daily requests, free); use OpenRouter sparingly.
- Secrets: add `credentials.txt` at repo root (gitignored) with `CHUTES_API_KEY` and optionally `OPENROUTER_API_KEY`.
- Seeds: optional `SELECTION_SEED` controls deterministic instance selection (default 42 if unset).
