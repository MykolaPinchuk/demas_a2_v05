02_System_Requirements.md

(for the autonomous coding agent “Codex”)

A) Functional requirements

Predictions generation

For each (model × mode × task set × attempt policy), produce JSONL where each line has:
instance_id (exact), model_name_or_path (human-readable), model_patch (unified diff).

Reject malformed diff or missing fields; do not include non-diff text in model_patch.

Evaluation integration

Use the official SWE-bench evaluator only.

Inputs: dataset name (i1 = Lite), predictions path, run id, pinned instance_ids, --max_workers (start 4), cache controls.

Persist all evaluator outputs under a unique run directory (immutable).

Agent modes

Patch mode (default i1): instruct model to output unified diff only; if malformed and budget remains, request a corrected diff within the same attempt.

Shell mode (enabled i1, default for multi-patch in i3): expose audited tools:

file read/write (atomic), list directory;

git diff, git apply;

pytest (full) and pytest -k <pattern> (targeted);

grep, sed, head, tail, wc, find;

run a short Python snippet.
Enforce per-command timeouts and per-attempt wall-time; log command, duration, exit code, and stdout/stderr sizes. Export final diff.

Multi-attempt (i2+)

K attempts (default 2, allow 3 where justified) with per-attempt 90s cap by default; increase only when evidence shows necessity.

Optional triage tests before finalizing a patch. Only the final patch per instance goes to predictions.

Model providers & catalogs

i1 (Chutes only):
Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8, Qwen/Qwen3-Coder-30B-A3B-Instruct,
moonshotai/Kimi-K2-Instruct-0905, moonshotai/Kimi-K2-Instruct-75k,
zai-org/GLM-4.5-FP8, zai-org/GLM-4.5-Air.

i2+ (add):
moonshotai/Kimi-Dev-72B, deepseek-ai/DeepSeek-V3.1, deepseek-ai/DeepSeek-V3-0324, deepseek-ai/DeepSeek-R1-0528,
unsloth/gemma-3-12b-it, Qwen/Qwen3-Next-80B-A3B-Instruct,
chutesai/Mistral-Small-3.2-24B-Instruct-2506, Qwen/Qwen3-235B-A22B-Thinking-2507,
OpenRouter: openai/gpt-5-mini, openai/gpt-oss-120b, openai/gpt-oss-20b.

Availability policy: if a model is missing/renamed, skip & report (do not fail the run).

Allow per-model overrides (temperature, seeds, max output tokens, context budget). Capture provider usage metadata when available; record “unknown” otherwise (i4 will fix).

Instance selection

i1: 6–8 very easy one-patch tasks from Lite (suited to 90s attempts); pin and commit exact IDs and dataset revision.

i2: reuse the i1 set.

i3: expand to 15–20 total, adding multi-patch & numpy/pandas-leaning tasks; increase timeouts only where evidence shows necessity.

Metrics & leaderboard

i1–i3: pass@1, pass@K (when K>1), total wall-clock per model, attempts used, tool-call counts, run-failure rate.

i4: add input/output/total tokens, USD cost, and latency P50/P90/P99.

B) Non-functional requirements

Compute budget: keep aggregate CPU ≤ 80% of 16 threads. Defaults:

Predictions concurrency: 8 (may raise to 12 if stable and not rate-limited).

Evaluator --max_workers: 4 at first; may raise to 6–8 later.

Security: store provider keys in credentials.txt at repo root; ensure it is gitignored. Minimal is fine.

Format (example, values redacted):

CHUTES_API_KEY=...
OPENROUTER_API_KEY=...


Reliability: partial failures must not abort the batch; mark status per (model, instance, attempt): ok, provider_failed, timeout, eval_error, skipped_unavailable_model.

Idempotence: safe to rerun; skip already completed cells unless force is set.

Portability: Linux + Docker; no cloud dependency; hooks allowed.

Traceability: every leaderboard row traceable to prompts (redacted), logs, predictions, evaluator artifacts, and environment snapshot (evaluator & dataset revisions).

C) Interfaces (descriptive, no code)

Provider adapter

Input: messages (system/user/tool), params (model_id, temperature, max_output, seed).

Output: text completion (+ optional tool directives), usage metadata (if any), latency, normalized errors.

Orchestrator

Input: model catalog, task set, attempt policy, concurrency, timeouts, output directories, secrets.

Output: predictions JSONL, run manifest, structured logs, evaluator artifacts, metrics bundle.

Evaluator wrapper

Input: dataset name, predictions path, run id, instance list, --max_workers, cache controls.

Output: official results JSON & logs (immutable).

D) Token & cost accounting (i4 only)

Counting priority

Provider-reported usage (authoritative).

Official tokenizer for the model (local count).

Documented approximation (last resort; clearly flagged).

Cost

Maintain a per-model price table (prompt/output $/1K tokens).

Compute per-run total and cost-per-resolved-instance.

Validate on a sample vs. provider billing; report % delta.

E) Operational runbook (checklist)

Environment

Install SWE-bench evaluator & Docker.

Record evaluator version and dataset revision.

Secrets

Create credentials.txt (gitignored) with CHUTES_API_KEY and (later) OPENROUTER_API_KEY.

Loader reads this file into env vars at start.

Pin i1 tasks

Select 6–8 very easy one-patch Lite instances (short gold patch, few hunks); record selection seed/filters; commit the IDs & revision.

Configure i1 models

Add the 6 Chutes models above with default generation params (temperature/seed reasonable & consistent); note any unavailable models in a “skipped” list.

Run i1 (fast loop)

Mode: Patch (default) and Shell (time-budgeted) per model.

Attempts: K=2, 90s per attempt; per-command caps 20–30s.

Predictions → official evaluator with pinned instance_ids, --max_workers=4.

Produce baseline (no-patch) for the same instances.

Validate i1

Best model ≫ baseline; evaluations reproducible; artifacts complete.

If not, raise timeouts or tweak the instance set minimally; rerun.

Run i2

Enable multi-attempt; add i2 model list (Chutes + OpenRouter); consider raising evaluator workers (6–8) if CPU remains <80%.

Emit leaderboard v1 (no tokens yet).

Run i3

Expand to 15–20 total (add multi-patch & numpy/pandas); Shell mode default there; raise timeouts only where needed.

Emit leaderboard v2.

Run i4

Implement token & cost accounting; add latency P50/P90/P99; validate sample counts; emit leaderboard v3.

F) Acceptance criteria (by iteration)

i1: valid predictions; evaluator runs cleanly; best model above baseline by a meaningful margin; concurrency/timeouts within CPU budget; artifacts complete & reproducible.

i2: multi-attempt works; unavailable models are skipped & reported; leaderboard v1 includes pass@K, wall-time, attempts, tool-calls.

i3: 15–20 tasks incl. multi-patch & numpy/pandas; leaderboard v2 across ~15–20 models.

i4: token & cost metrics implemented and sample-validated; leaderboard v3 adds tokens, cost, latency percentiles and cost-per-resolved-instance.