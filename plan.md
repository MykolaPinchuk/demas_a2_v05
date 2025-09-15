01_Implementation_Plan.md

SWE-bench Agent Evaluation Harness (i1 → i4)

0) Purpose & success criteria

Goal: rapidly deliver a small, reproducible harness that evaluates coding agents on a curated subset of SWE-bench tasks and produces a trustworthy leaderboard—without constraining capable agents.

Success looks like

Harness emits predictions in the official SWE-bench JSONL format and invokes the official evaluator; no custom scoring.

i1 shows a clear spread across 4–6 models on 6–8 easy instances, with the best model ≫ a no-patch baseline and evaluations are reproducible.

i2 adds multi-attempt and more models; i3 adds multi-patch and numpy/pandas tasks; i4 adds token & cost metrics.

We keep iteration velocity high by starting with short timeouts and increasing only when clearly necessary.

1) Iterations overview
i1 — Working slice (fast validation)

Dataset: SWE-bench Lite. Pin 6–8 “easy one-patch” instances (short gold patches, minimal hunks).

Agent modes:

Patch mode (default for i1): the model outputs a unified diff.

Shell mode (enabled but time-budgeted): sandboxed tools (read/write files atomically, git diff/apply, targeted pytest -k, text search/edit, short Python runner). No outbound network.

Models (Chutes only):

Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8

Qwen/Qwen3-Coder-30B-A3B-Instruct

moonshotai/Kimi-K2-Instruct-0905

moonshotai/Kimi-K2-Instruct-75k

zai-org/GLM-4.5-FP8

zai-org/GLM-4.5-Air

Compute policy: may use up to 80% of local CPU (16 threads) ⇒ plan for 12 workers as a safe default.

Concurrency defaults:

Predictions generation: up to 8 parallel model jobs (raise to 12 if provider rate-limits allow).

Evaluator (--max_workers): start at 4 to avoid thrash while containers warm; increase later if stable.

Timeout defaults (aggressive for speed):

Per-attempt wall-time: 90s (raise only if evidence shows it’s too tight).

Attempts per instance (K): 2.

Per command in Shell mode: 20–30s cap.

Exit criteria: best model’s resolution rate clearly above baseline; runs are reproducible; artifacts (predictions, evaluator outputs, logs) are complete.

i2 — Scale models + multi-attempt + leaderboard v1

Enable multi-attempt per instance (keep K=2 by default; allow K=3 where needed).

Add models (Chutes + OpenRouter; see list in §3).

Add triage testing inside Shell mode (run quick, targeted tests before finalizing the patch).

Leaderboard v1: pass@1, pass@K, wall-clock, attempts used, tool-call counts. (Tokens/cost deferred to i4.)

Concurrency: consider Evaluator --max_workers = 6–8 if CPU headroom remains.

i3 — Harder tasks (multi-patch + numpy/pandas)

Expand to 15–20 total instances:

Keep the 6–8 easy one-patch items (from i1).

Add 6–8 medium multi-patch tasks.

Add 3–4 numpy/pandas-heavy tasks with longer timeouts if needed.

Default to Shell mode on multi-patch tasks.

Leaderboard v2 across ~15–20 models; include per-repo breakdown.

i4 — Token & cost accounting (deferred)

Standardize input/output/total tokens and $-cost across providers.

Priority for counts: provider-reported → official tokenizer → documented approximation.

Add latency P50/P90/P99.

Leaderboard v3 = v2 + tokens, cost, latency percentiles. Validate against provider dashboards/logs on a sample.

2) Architecture (high-level, no code)

Provider adapters

Chutes & OpenRouter adapters with a uniform chat interface (model_id, temperature, max_output, seed, messages), retries/backoff, normalized errors.

Capture provider usage metadata when available; store “unknown” otherwise (to be solved in i4).

Agent controllers

Patch-mode controller: enforces “diff-only” output; validates patch shape; emits model_patch.

Shell-mode controller: audited toolbelt; per-command & per-attempt timeouts; exports a final diff (vs. base) as model_patch.

Orchestrator

Drives N models × M instances × K attempts with concurrency controls; ensures idempotent resume and thorough logging.

Produces predictions JSONL and a structured run manifest.

Evaluator wrapper

Invokes the official evaluator with dataset name, run id, optional --instance_ids, --max_workers, cache controls; preserves artifacts immutably.

Selectors

Deterministically pick i1/i3 task sets (seeded); persist exact instance_ids and dataset revision.

Metrics & leaderboard

v1/v2: pass@1, pass@K, wall-time, attempts, tool-calls, run-fail rate.

v3 (i4): + tokens, cost, latency.

3) Model plan (by iteration)

i1 (Chutes only)

Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8

Qwen/Qwen3-Coder-30B-A3B-Instruct

moonshotai/Kimi-K2-Instruct-0905

moonshotai/Kimi-K2-Instruct-75k

unsloth/gemma-3-12b-it

zai-org/GLM-4.5-FP8

zai-org/GLM-4.5-Air

i2 or later (add)

moonshotai/Kimi-Dev-72B

deepseek-ai/DeepSeek-V3.1

deepseek-ai/DeepSeek-V3-0324

deepseek-ai/DeepSeek-R1-0528

moonshotai/Kimi-K2-Instruct-75k

Qwen/Qwen3-Next-80B-A3B-Instruct

chutesai/Mistral-Small-3.2-24B-Instruct-2506

Qwen/Qwen3-235B-A22B-Thinking-2507

OpenRouter:

openai/gpt-5-mini

openai/gpt-oss-120b

openai/gpt-oss-20b

Availability policy: if a model name/endpoint is unavailable or renamed, skip it, record the reason, and continue.

4) Instance selection policy

i1: pick very easy one-patch items (short, single-file, few hunks) to fit the 90s attempt cap.

i3: add multi-patch and numpy/pandas tasks; allow targeted timeout raises only where evidence demands.

Always pin and commit the exact instance IDs (and dataset revision).

5) Compute, reliability, observability

CPU budget: default to 12 workers; may scale up/down to keep ≤80% CPU.

Stability first: increase timeouts or workers only when there’s evidence it improves end-to-end throughput.

Logging: structured per-attempt logs (prompts redacted as needed), tool-calls, durations, exit codes; evaluator versions & dataset revision pinned.

Idempotence: resume-safe; skip completed (model, instance) cells unless force is set.

6) Deliverables by iteration

i1: pinned instance list; predictions per model/mode; evaluator artifacts; short validation memo (baseline vs best).

i2: multi-attempt config; expanded model list; leaderboard v1 (no tokens).

i3: 15–20 tasks including multi-patch & numpy/pandas; leaderboard v2.

i4: token & cost accounting, latency stats; leaderboard v3.